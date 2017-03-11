
"""
Discovery fires available/unavailable events for resources

Serial Resource connector turns the resource into a Serial instance, and then into a Connector
(sniffer from application). Posts Connector available event (connector not opened.)


"""
import logging

from serial import Serial

from controlbox.conduit.process_conduit import ProcessDiscovery
from controlbox.conduit.serial_conduit import SerialDiscovery
from controlbox.conduit.server_discovery import TCPServerDiscovery
from controlbox.connector.base import CloseOnErrorConnector, ProtocolConnector
from controlbox.connector.processconn import ProcessConnector
from controlbox.connector.serialconn import SerialConnector
from controlbox.connector.socketconn import SocketConnector, TCPServerEndpoint
from controlbox.connector_maintainance import ConnectionManager
from controlbox.discovery import ConnectorDiscovery, ManagedConnectorDiscoveries

logger = logging.getLogger(__name__)


class ControllerConnectionManager(ConnectionManager):
    """
    runs the controller protocol as part of the background thread loop
    # todo - this is probably better as a factory function rather than a subclass
    """
    def __init__(self, retry_period=5):
        super().__init__(self._pump_protocol, retry_period)

    def _pump_protocol(self, maintained_connection):
        maintained_connection.connector.protocol.read_response()


class ControllerDiscoveryFactory:
    """
    A factory for controlbox controller discovery based on resource
    discovery of various types.

    When a resource is discovered,
    """

    def __init__(self, protocol_sniffer):
        """
        :param protocol_sniffer: a callable that takes a Conduit and returns a protocol if recognised,
            or None if not.
        """
        self.protocol_sniffer = protocol_sniffer

    def make_protocol_connector(self, connector):
        # todo - is the CloseOnError conenctor needed? the managed connections also close
        # the connection on error
        connector = CloseOnErrorConnector(connector)
        return ProtocolConnector(connector, self.protocol_sniffer)

    def build_serial_discovery(self, setup_serial) -> ConnectorDiscovery:
        """
        Constructs a ControllerDiscovery instance suited to discovering serial controllers.
         :param setup_serial    A callable that is passed a non-open Serial instance and allowed to modify the
            serial protocol (baud rate, stop bits, parity etc..)  The result from the callable is ignored.
        """
        discovery = SerialDiscovery()

        def connector_factory(key, resource):
            serial = Serial()
            serial.port = key
            setup_serial(serial)
            connector = SerialConnector(serial)
            return self.make_protocol_connector(connector)

        return ConnectorDiscovery(discovery, connector_factory)

    def build_tcp_server_discovery(self, service_type, known_addresses):
        """
        Creates a ControllerDiscovery instance suited to discovering local server controllers.
        :param protocol_sniffer A callable that takes a Conduit and is responsible for decoding the
            protocol, or raise a UnknownProtocolError. See AbstractConnector
        :param service_type A string that identifies the specific type of TCP service. This is an application
            defined name.
        """
        discovery = TCPServerDiscovery(service_type, known_addresses=known_addresses)

        def connector_factory(key, resource: TCPServerEndpoint):
            connector = SocketConnector(sock_args=(), connect_args=(resource.hostname, resource.port),
                                        report_errors=False)
            return self.make_protocol_connector(connector)

        return ConnectorDiscovery(discovery, connector_factory)

    def build_process_discovery(self, file, args, cwd=None):
        """
        Creates a ControllerDiscovery instance suited to discovering local executable controllers.
        :param protocol_sniffer A callable that takes a Conduit and is responsible for decoding the
            protocol, or raise a UnknownProtocolError. See AbstractConnector
        :param file The filename of the process file to open.
        """
        discovery = ProcessDiscovery(file)

        def connector_factory(resource):
            connector = ProcessConnector(resource, args, cwd=cwd)
            return self.make_protocol_connector(connector)

        return ConnectorDiscovery(discovery, connector_factory)


def build_discovered_controller_connections_manager(discoveries):
    """
    builds a
    :return: a ConnectionManager that manages the connections to
    discovered controllers.
    """
    manager = ControllerConnectionManager()
    ManagedConnectorDiscoveries(discoveries, manager)
    return manager
