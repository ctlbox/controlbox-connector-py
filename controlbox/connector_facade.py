
"""
Discovery fires available/unavailable events for resources

Serial Resource connector turns the resource into a Serial instance, and then into a Connector
(sniffer from application). Posts Connector available event (connector not opened.)


"""
import logging
import time

from serial import Serial

from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent, PolledResourceDiscovery
from controlbox.conduit.process_conduit import ProcessDiscovery
from controlbox.conduit.serial_conduit import SerialDiscovery
from controlbox.conduit.server_discovery import TCPServerDiscovery, ZeroconfTCPServerEndpoint
from controlbox.connector.base import Connector, ProtocolConnector, CloseOnErrorConnector, ConnectorError
from controlbox.connector.processconn import ProcessConnector
from controlbox.connector.serialconn import SerialConnector
from controlbox.connector.socketconn import SocketConnector
from controlbox.protocol.async import AsyncLoop
from controlbox.support.events import QueuedEventSource

logger = logging.getLogger(__name__)


class ManagedConnection(AsyncLoop):
    """ maintains an association between a resource and the connector used to access the endpoint, and
     notifies an event source when the connection is opened and closed.
    The connection is managed by calling maintain().

    Fires ConnectorConnectedEvent and ConnectorDisconnectedEvent as the connection state changes.

    :param: resource    The resource corresponding to the connector. This is used only
        for logging/information.
    :param: connector   The connector to the endpoint to maintain. If this is closed,
        this managed connection attempts to open it after retry_preiod.
    :param: retry_period    How often to try opening the connection when it's closed
    :param: events          event source to post the resource events when the connection
        opens and closed.
     """
    # todo add a mixin for connector listener so the conenctor events
    # are hooked up in a consistent way
    def __init__(self, resource, connector: Connector, retry_period, events):
        super().__init__()
        self.resource = resource
        self.last_opened = None
        self.connector = connector
        connector.events.add(self._connector_events)
        self.retry_period = retry_period
        self.events = events

    def _connector_events(self, *args, **kwargs):
        """propagate connector events to the manager """
        self.events.fire(*args, **kwargs)
        # events will place events in a queue that are posted by the connector manager

    def _open(self):
        connector = self.connector
        if not connector.connected and connector.available:
            try:
                connector.connect()
                logger.info("device connected: %s" % self.resource)
            except ConnectorError as e:
                if (logger.isEnabledFor(logging.DEBUG)):
                    logger.exception(e)
                    logger.debug("Unable to connect to device %s: %s" % (self.resource, e))

    def _close(self):
        was_connected = self.connector.connected
        self.connector.disconnect()
        if was_connected:
            logger.info("device disconnected: %s" % self.resource)

    def loop(self):
        self._open()
        while self.connector.connected:
            self.connector.protocol.read_response_async()
        self.stop_event.wait(self.retry_period)

    def maintain(self, current_time):
        if self._needs_retry(current_time):
            self.last_opened = current_time
            self._open()

    def _needs_retry(self, current_time):
        return self.last_opened is None or ((current_time - self.last_opened) >= self.retry_period)


class ControllerConnectionManager:
    """
    Keeps track of the resources available for potential controllers, and attempts to open them
    at regular intervals.

    A connector is kept in the list of managed connectors for as long as the underlying resource is available. This is
    because resource detection may not be 100% reliable (e.g. a serial port being quickly disconnected/connected), so
    the resource is tried so long as it's presence is known.

    Resources are added via the "connected()" method and removed via "disconnected()`.

    Fires ConnectorConnectedEvent when a connector is available.
    Fires ConnectorDisconnectedEvent when the connector is disconencted.

    """

    def __init__(self, retry_period=5):
        self.retry_period = retry_period
        self._connections = dict()
        self.events = QueuedEventSource()

    def disconnected(self, resource):
        """ registers the given source as being disconnected.
        It is removed from the known connections. """
        if resource in self._connections:
            connection = self._connections[resource]
            connection.stop()
            del self._connections[resource]

    def connected(self, resource, connector):
        """ Notifies this manager that the given connector is available as a possible controller connection.
            :param: resource    A key identifying the resource
            :param: connector  A Connector instance.
            """
        previous = self._connections.get(resource, None)
        if previous is not None:
            if previous.connector is connector:
                return
        conn = self._connections[resource] = self._new_managed_connection(resource, connector,
                                                                          self.retry_period, self.events)
        conn.start()

    def _new_managed_connection(self, resource, connector, timeout, events):
        return ManagedConnection(resource, connector, timeout, events)

    @property
    def connections(self):
        """
        retrieves a mapping from the resource key to the ManagedConnection.
        Note that connections may not be connected.
        """
        return dict(self._connections)

    def maintain(self, current_time=time.time):
        """
        updates all managed connections on this manager.
        """
        for managed_connection in self.connections.values():
            try:
                managed_connection.maintain(current_time())
            except Exception as e:
                logger.exception("unexpected exception '%s' on '%s', closing." % (e, managed_connection))
                managed_connection.close()

    def update(self):
        self.events.publish()


class ConnectionDiscovery:
    """
    Listens for events from a ResourceDiscovery instance and uses the connector_factory to create a connector
    corresponding to the resource type discovered. The connector is left unopened, and used to notify
    a ConnectorManager about the resource availability.
    """
    def __init__(self, discovery: PolledResourceDiscovery, connector_factory, connector_manager=None):
        """
        :param discovery A ResourceDiscovery instance that publishes events as resources become available.
        :param connector_factory A callable. Given the (key,target) info from the ResourceDiscovery,
            the factory is responsible for creating a connector.
        :param connector_manager The manager that is notified of connections changing availability
        """
        self.discovery = discovery
        self.connector_factory = connector_factory
        self.manager = connector_manager
        listeners = discovery.listeners
        listeners += self.resource_event

    def dispose(self):
        self.discovery.listenrs.remove(self.resource_event)

    def _create_connector(self, resource):
        return self.connector_factory(resource)

    def resource_event(self, event):
        """ receives resource notifications from the ResourceDiscovery.
            When a resource is available, the connector factory is invoked to create a connector for the resource.
            When a resource is unavailable, the connection manager is notified.
        """
        if not self.manager:
            return
        if type(event) is ResourceAvailableEvent:
            connector = self._create_connector(event.resource)
            self.manager.connected(event.key, connector)
        elif type(event) is ResourceUnavailableEvent:
            self.manager.disconnected(event.key)

    def update(self):
        """
        Updates discovered resources.
        """
        self.discovery.update()


class ControllerDiscoveryFacade:
    """
    A facade for listening to different types of connectible resources, such as serial ports, TCP servers, local
    program images.

    """
    default_serial_baudrate = 57600

    def __init__(self, controller_discoveries):
        """
        :param controller_discoveries  ControllerDiscovery instances used to detect endpoints.
            See build_serial_discovery and build_tcp_server_discovery
        """
        self.manager = ControllerConnectionManager()
        self.discoveries = controller_discoveries
        for d in self.discoveries:
            d.manager = self.manager

    def update(self):
        """
        updates all the discovery objects added to the facade.
        """
        for d in self.discoveries:
            d.update()
        self.manager.update()

    @staticmethod
    def default_serial_setup(serial: Serial):
        """ Applies the default serial setup for a serial connection to a controller. """
        serial.baudrate = ControllerDiscoveryFacade.default_serial_baudrate

    @staticmethod
    def build_serial_discovery(protocol_sniffer, setup_serial=None) ->ConnectionDiscovery:
        """
        Constructs a ControllerDiscovery instance suited to discovering serial controllers.
         :param protocol_sniffer:   A callable that takes a Conduit and is responsible for decoding the Protocol to use,
            or raise a UnknownProtocolError. See AbstractConnector.
         :param setup_serial    A callable that is passed a non-open Serial instance and allowed to modify the
            serial protocol (baud rate, stop bits, parity etc..)  The result from the callable is ignored.
        """
        discovery = SerialDiscovery()
        if setup_serial is None:
            setup_serial = ControllerDiscoveryFacade.default_serial_setup

        def connector_factory(resource):
            key = resource[0]
            serial = Serial()
            serial.port = key
            setup_serial(serial)
            connector = SerialConnector(serial)
            connector = CloseOnErrorConnector(connector)
            return ProtocolConnector(connector, protocol_sniffer)

        return ConnectionDiscovery(discovery, connector_factory)

    @staticmethod
    def build_tcp_server_discovery(protocol_sniffer, service_type):
        """
        Creates a ControllerDiscovery instance suited to discovering local server controllers.
        :param protocol_sniffer A callable that takes a Conduit and is responsible for decoding the
            protocol, or raise a UnknownProtocolError. See AbstractConnector
        :param service_type A string that identifies the specific type of TCP service. This is an application
            defined name.
        """
        discovery = TCPServerDiscovery(service_type)

        def connector_factory(resource: ZeroconfTCPServerEndpoint):
            connector = SocketConnector(sock_args=(), connect_args=(resource.hostname, resource.port))
            connector = CloseOnErrorConnector(connector)
            return ProtocolConnector(connector, protocol_sniffer)

        return ConnectionDiscovery(discovery, connector_factory)

    @staticmethod
    def build_process_discovery(protocol_sniffer, file, args, cwd=None):
        """
        Creates a ControllerDiscovery instance suited to discovering local executable controllers.
        :param protocol_sniffer A callable that takes a Conduit and is responsible for decoding the
            protocol, or raise a UnknownProtocolError. See AbstractConnector
        :param file The filename of the process file to open.
        """
        discovery = ProcessDiscovery(file)

        def connector_factory(resource):
            connector = ProcessConnector(resource, args, cwd=cwd)
            connector = CloseOnErrorConnector(connector)
            return ProtocolConnector(connector, protocol_sniffer)

        return ConnectionDiscovery(discovery, connector_factory)
