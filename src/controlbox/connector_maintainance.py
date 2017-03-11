import logging
import time

from controlbox.connector.base import Connector, ConnectorError
from controlbox.protocol.async import AsyncLoop
from controlbox.support.events import QueuedEventSource
from controlbox.support.retry_strategy import PeriodRetryStrategy, RetryStrategy

logger = logging.getLogger(__name__)


class MaintainedConnection:
    """
    Attempts to maintain a connection to an endpoint by checking if the connector is open, and
    attempting to open it if not.

    The ConnectorEvent instances fired from the connector are propagated to an event listener.

    The connection is managed synchronously by calling maintain() at regular intervals.
    For asynchronous management, use a MaintainedConnectorLoop, which will run the management on a separate
    thread.

    Fires ConnectorConnectedEvent and ConnectorDisconnectedEvent as the connection state changes.

    :param: resource    The resource corresponding to the connector. This is used only
        for logging/information.
    :param: connector   The connector to the endpoint to maintain. If this is closed,
        this managed connection attempts to open it after retry_preiod.
    :param: retry_period    How often to try opening the connection when it's closed
    :param: events          event source to post the resource events when the connection
        opens and closed. Should support the method fire(...)
     """
    # todo add a mixin for connector listener so the connector events
    # are hooked up in a consistent way
    def __init__(self, resource, connector: Connector, retry_strategy: RetryStrategy, events, log=logger):
        super().__init__()
        self.resource = resource        # an identifier for this managed connection
        self.connector = connector      # the connector that can provide a conduit to the endpoint
        connector.events.add(self._connector_events)  # listen to the connector
        self.retry_strategy = retry_strategy
        self.events = events
        self.logger = log

    def _connector_events(self, *args, **kwargs):
        """ propagates connector events to the external events handler """
        self.events.fire(*args, **kwargs)

    def _open(self):
        """
        attempts to establish the connection.

        If the connection raises a connection error, it is logged, but not raised
        :return: True if the the connector was tried - the connector was not connected and available
        """
        connector = self.connector   # type Connector
        try_open = not connector.connected and connector.available
        if try_open:
            try:
                connector.connect()
                self.logger.info("device connected: %s" % self.resource)
            except ConnectorError as e:
                if (self.logger.isEnabledFor(logging.DEBUG)):
                    self.logger.exception(e)
                    self.logger.debug("Unable to connect to device %s: %s" % (self.resource, e))
        return try_open

    def _close(self):
        """
        Closes the connection to the connector.
        :return:
        """
        was_connected = self.connector.connected
        self.connector.disconnect()
        if was_connected:
            self.logger.info("device disconnected: %s" % self.resource)
        return was_connected

    def maintain(self, current_time=time.time):
        """
        Maintains the connection by attempting to open it if not already open.
        :param current_time: the current time. Used to
        determine if the connection was tried or not.
        :return: True if the connection was tried
        """
        delay = self.retry_strategy(current_time)
        will_try = delay <= 0
        if will_try:
            self._open()
        return will_try


class MaintainedConnectionLoop(AsyncLoop):
    """
    maintains the connection as a background thread.

    :param maintained_connection    The connection to maintain on a background thread
    :param loop A function to call while the connection is established
    """

    def __init__(self, maintained_connection, loop=None):
        super().__init__()
        self.maintained_connection = maintained_connection
        self._loop = loop

    def loop(self):
        """
        open the connector, and while connected,
        read responses from the protocol.

        :return:
        """
        maintained_connection = self.maintained_connection
        try:
            maintained_connection._open()
            while maintained_connection.connector.connected:
                success = False
                try:
                    time.sleep(0)
                    self._connected_loop()
                    success = True
                finally:
                    if not success:
                        maintained_connection._close()
        finally:
            self.stop_event.wait(maintained_connection.retry_strategy())

    def _connected_loop(self):
        """called repeatedly while the connection is open"""
        if self._loop:
            self._loop(self.maintained_connection)


class ConnectionManager:
    """
    Keeps track of the resources available for potential controllers, and assocaited
    each resource with a MaintainedConnection.

    A connector is kept in the list of managed connectors for as long as it indicates it is available.

    Connectors are added via the "available()" method and removed via "unavailable()`.
    Events are fired when the update() method is called.

    Fires ConnectorConnectedEvent when a connector is available.
    Fires ConnectorDisconnectedEvent when the connector is disconnected.

    # todo - we have the ResourceDiscovery that indicates when a connection is no longer available
    # and we have the availalbe() method on the Connector.
    # this seems redundant.
    # Typically, the resource discovery may be more efficient (e.g. it can enumerate all serial ports at once)
    # versus each the connector that tests availability by listing all serial ports and checking if it is still a member

    :param connected_loop  a callable that is regularly called while a connection is active.
    """
    # todo - make this class synchronous and factor out the async handling into a subclass
    def __init__(self, connected_loop=None, retry_period=5):
        """
        :param retry_period: how frequently (in seconds) to refresh connections that are not connected
        # todo - use retry strategy?
        """
        self.retry_period = retry_period
        self._connections = dict()   # a map from resource to MaintainedConnection
        self.events = QueuedEventSource()
        self._connected_loop = connected_loop

    def unavailable(self, resource, connector: Connector=None):
        """register the given resource as being unavailable.
        It is removed from the managed connections."""
        if resource in self._connections:
            connection = self._connections[resource]
            connection.loop.stop()
            connection.loop = None  # free cyclic reference
            del self._connections[resource]

    def available(self, resource_key, connector: Connector):
        """ Notifies this manager that the given connector is available as a possible controller connection.
            :param: resource    A key identifying the resource
            :param: connector  A Connector instance that can connect to the resource endpoint
            If the resource is already connected to the given connector,
            the method returns quietly. Otherwise, the existing managed connection
            is stopped before being replaced with a new managed connection
            to the connector.
            """
        previous = self._connections.get(resource_key, None)
        if previous is not None:
            if previous.connector is connector:
                return
            else:
                previous.loop.stop()     # connector has changed
        conn = self._connections[resource_key] = self._new_maintained_connection(resource_key, connector,
                                                                                 self.retry_period, self.events)
        conn.loop.start()

    def _new_maintained_connection(self, resource_key, connector, timeout, events):
        """Creates a new maintained connection and an async loop"""
        mc = MaintainedConnection(resource_key, connector, PeriodRetryStrategy(timeout), events)
        loop = MaintainedConnectionLoop(mc, self._connected_loop)
        mc.loop = loop
        return mc

    @property
    def connections(self):
        """
        retrieves a mapping from the resource key to the MaintainedConnection.
        Note that connections may or may not be connected.
        """
        return dict(self._connections)

    def maintain(self, current_time=time.time):
        """
        Synchronously updates all managed connections on this manager.
        # todo - not sure why this is here since each connection now runs as it's own thread
        """
        for maintained_connection in self._connections.values():
            try:
                maintained_connection.maintain(current_time())
            except Exception as e:
                logger.exception("unexpected exception '%s' on '%s', closing." % (e, maintained_connection))
                maintained_connection._close()

    def update(self):
        """ Notifies of any connections that have changed.

        Since each connection
        is running on it's own thread, the events from each are queued
        and then published when this method is called.
        :return:
        """
        self.events.publish()
