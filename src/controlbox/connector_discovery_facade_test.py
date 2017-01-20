from unittest import TestCase
from unittest.mock import Mock

from hamcrest import assert_that, is_, not_none

from controlbox.connector.socketconn import TCPServerEndpoint
from controlbox.connector_discovery_facade import ControllerConnectionManager, ControllerDiscoveryFactory, \
    build_discovered_controller_connections_manager
from mock_matcher import called_once, called_once_with


class ControllerConnectionManagerTest(TestCase):
    def test_constructor(self):
        sut = ControllerConnectionManager()
        assert_that(sut._connected_loop, is_(sut._pump_protocol))

    def test_invokes_protocol_sync_receive(self):
        sut = ControllerConnectionManager()
        maintained_connection = Mock()
        sut._pump_protocol(maintained_connection)
        assert_that(maintained_connection.connector.protocol.read_response, is_(called_once()))


class ControllerDiscoveryFactoryTest(TestCase):
    def setUp(self):
        self.protocol_sniffer = Mock()
        self.sut = ControllerDiscoveryFactory(self.protocol_sniffer)

    def test_saves_sniffer(self):
        assert_that(self.sut.protocol_sniffer, is_(self.protocol_sniffer))

    def test_build_serial_discovery(self):
        # todo - this isn't a sufficient test
        # we have coverage, but not verification (or a spec)
        serial_config = Mock()
        port = "someport"
        discovery = self.sut.build_serial_discovery(serial_config)
        assert_that(discovery._connector_factory, is_(not_none()))
        discovery._connector_factory(port, object())
        assert_that(serial_config, is_(called_once()))
        serial = serial_config.call_args[0][0]
        assert_that(serial.port, is_(port))

    def test_buid_tcp_service_discovery(self):
        discovery = self.sut.build_tcp_server_discovery("test", [])
        discovery._connector_factory("myservice", TCPServerEndpoint("host", "ip", 8080))

    def test_build_process_discovery(self):
        discovery = self.sut.build_process_discovery("somefile", ())
        discovery._connector_factory("somefile")


def test_build_discovered_controller_connections_manager():
    build_discovered_controller_connections_manager([])