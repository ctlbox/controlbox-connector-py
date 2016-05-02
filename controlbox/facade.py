
"""
Discovery fires available/unavailable events for resources

Serial Resource connector turns the resource into a Serial instance, and then into a Connector
(sniffer from application). Posts Connector available event (connector not opened.)


"""
import logging
from datetime import time

from serial import Serial

from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent, PolledResourceDiscovery
from controlbox.conduit.serial_conduit import SerialDiscovery
from controlbox.conduit.server_discovery import TCPServerDiscovery, ZeroconfTCPServerEndpoint
from controlbox.connector.base import Connector, ProtocolConnector, CloseOnErrorConnector, ConnectorError, \
    ConnectorConnectedEvent, ConnectorDisconnectedEvent
from controlbox.connector.serialconn import SerialConnector
from controlbox.connector.socketconn import SocketConnector
from controlbox.support.events import EventSource

logger = logging.getLogger(__name__)


class ManagedConnection:
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
    def __init__(self, resource, connector: Connector, retry_period, events):
        self.resource = resource
        self.last_opened = None
        self.connector = connector
        self.retry_period = retry_period
        self.events = events

    def _open(self, current_time):
        connector = self.connector
        self.last_opened = current_time
        if not connector.connected:
            try:
                connector.connect()
                self.events.fire(ConnectorConnectedEvent(self.connector))
            except ConnectorError as e:
                logger.warn("Unable to connect to device %s: %s" % (self.resource, e))

    def close(self):
        was_connected = self.connector.connected
        self.connector.disconnect()
        if was_connected:
            self.events.fire(ConnectorDisconnectedEvent(self.connector))

    def maintain(self, current_time):
        if self._needs_retry(current_time):
            self._open(current_time)

    def _needs_retry(self, current_time):
        return self.last_opened is None or ((current_time - self.last_opened) >= self.retry_period)


class ControllerConnectionManager:
    """
    Keeps track of the resources available for potential controllers, and attempts to open them
    at regular intervals.
    """

    def __init__(self, retry_period=30):
        self.retry_period = retry_period
        self._connections = dict()
        self.events = EventSource()

    def disconnected(self, resource):
        """ registers the given source as being disconnected. """
        if resource in self._connections:
            connection = self._connections[resource]
            connection.close()
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
        self._connections[resource] = self._new_managed_connection(resource, connector, self.retry_period, self.events)

    def _new_managed_connection(self, resource, connector, timeout, events):
        return ManagedConnection(resource, connector, self.retry_period, self.events)

    @property
    def connections(self):
        return dict(self._connections)

    def update(self, current_time=time):
        """
        updates all managed connections on this manager.
        """
        for managed_connection in self.connections.values():
            try:
                managed_connection.maintain(current_time())
            except Exception as e:
                logger.error("unexpected exception %s on %s, closing." % (e, managed_connection))
                managed_connection.close()


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
            self.manager.connected(event.resource, connector)
        elif type(event) is ResourceUnavailableEvent:
            self.manager.disconnected(event.resource)

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
            connector = SocketConnector(sock_args=(), connect_args=(resource.ip_address, resource.port))
            connector = CloseOnErrorConnector(connector)
            return ProtocolConnector(connector, protocol_sniffer)

        return ConnectionDiscovery(discovery, connector_factory)


def monitor():
    builder = ControllerDiscoveryFacade
    # just use the connector as the protocol

    def sniffer(x):
        return x

    discoveries = (builder.build_serial_discovery(sniffer),
                   builder.build_tcp_server_discovery(sniffer, "brewpi"))
    facade = builder(discoveries)
    while True:
        # detect any new
        facade.update()


if __name__ == '__main__':
    monitor()
