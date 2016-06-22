import logging
import unittest
from unittest.mock import Mock, patch, DEFAULT

from hamcrest import is_not, assert_that, is_, instance_of
from zeroconf import ServiceInfo

from controlbox.conduit import server_discovery
from controlbox.conduit.discovery import ResourceUnavailableEvent, ResourceAvailableEvent
from controlbox.conduit.server_discovery import TCPServerDiscovery, ZeroconfTCPServerEndpoint, logger


class TCPServerDiscoveryTest(unittest.TestCase):

    def test_constructor(self):
        sut = TCPServerDiscovery("mysvc", False)
        assert_that(sut.event_queue, is_not(None))

    def test_constructor_zeroconf(self):
        with patch.multiple(server_discovery, Zeroconf=DEFAULT, ServiceBrowser=DEFAULT) as patches:
            Zeroconf = patches['Zeroconf']
            ServiceBrowser = patches['ServiceBrowser']
            Zeroconf.return_value = object()
            ServiceBrowser.return_Value = object()
            sut = TCPServerDiscovery("mysvc")
            assert_that(sut.zeroconf, is_(Zeroconf.return_value))
            assert_that(sut.browser, is_(ServiceBrowser.return_value))
            Zeroconf.assert_called_once()
            ServiceBrowser.assert_called_once_with(Zeroconf.return_value, "_mysvc._tcp.local.", sut)

    def test_resource_for_unknown_service(self):
        sut = TCPServerDiscovery("mysvc", False)
        sut.zeroconf = Mock()
        sut.zeroconf.get_service_info = Mock(return_value=None)
        res = sut.resource_for_service(sut.zeroconf, "mysvc", "name")
        assert_that(res, is_(None))

    def test_resource_for_known_service(self):
        sut = TCPServerDiscovery("mysvc", False)
        info = ServiceInfo("type", "name.type")
        info.port = 1234
        info.address = "address"
        info.name = "abcd"
        info.server = "server"
        sut.zeroconf = Mock()
        sut.zeroconf.get_service_info = Mock(return_value=info)
        res = sut.resource_for_service(sut.zeroconf, "mysvc", "name")
        assert_that(res, is_(instance_of(ZeroconfTCPServerEndpoint)))
        assert_that(res.port, is_(1234))
        assert_that(res.ip_address, is_("address"))
        assert_that(res.hostname, is_("server"))

    def test_publish_has_info(self):
        sut = TCPServerDiscovery("mysvc", False)
        event = Mock()
        callable = Mock(return_value=event)
        zeroconf = Mock()
        info = Mock()
        sut.event_queue = Mock()
        sut.event_queue.put = Mock()
        sut.resource_for_service = Mock(return_value=info)
        sut._publish_service(callable, zeroconf, "type", "name")
        sut.resource_for_service.assert_called_once_with(zeroconf, "type", "name")
        callable.assert_called_once_with(sut, "name", info)
        sut.event_queue.put.assert_called_once_with(event)

    def test_publish_no_info(self):
        sut = TCPServerDiscovery("mysvc", False)
        event = Mock()
        callable = Mock(return_value=event)
        zeroconf = Mock()

        sut.event_queue = Mock()
        sut.event_queue.put = Mock()
        sut.resource_for_service = Mock(return_value=None)
        sut._publish_service(callable, zeroconf, "type", "name")
        sut.resource_for_service.assert_called_once_with(zeroconf, "type", "name")
        callable.assert_not_called()
        sut.event_queue.put.assert_not_called()

    def test_add_service(self):
        zeroconf = Mock()
        sut = TCPServerDiscovery("mysvc", False)
        sut._publish_service = Mock()
        sut.add_service(zeroconf, "type", "name")
        sut._publish_service.assert_called_once_with(ResourceAvailableEvent, zeroconf, "type", "name")

    def test_remove_service(self):
        zeroconf = Mock()
        sut = TCPServerDiscovery("mysvc", False)
        sut._publish_service = Mock()
        sut.remove_service(zeroconf, "type", "name")
        sut._publish_service.assert_called_once_with(ResourceUnavailableEvent, zeroconf, "type", "name", False)

    def test_update(self):
        sut = TCPServerDiscovery("mysvc", False)
        sut.event_queue.put("item1")
        sut.event_queue.put("item2")
        sut._fire_events = Mock()
        sut.update()
        assert_that(sut.event_queue.empty(), is_(True))
        sut._fire_events.assert_called_once_with(["item1", "item2"])

    def test_update_empty(self):
        sut = TCPServerDiscovery("mysvc", False)
        assert_that(sut.event_queue.empty(), is_(True))
        sut._fire_events = Mock()
        sut.update()
        assert_that(sut.event_queue.empty(), is_(True))
        sut._fire_events.assert_not_called()


def log_connection_events(event):
    if isinstance(event, ResourceAvailableEvent):
        logger.info("Connected device on %s using protocol %s" %
                    (event.source, event.resource))
    elif isinstance(event, ResourceUnavailableEvent):
        logger.info("Disconnected device on %s" % event.source)
    else:
        logger.warn("Unknown event %s " % event)


def monitor():
    """ A helper function to monitor serial ports for manual testing. """
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())

    w = TCPServerDiscovery("brewpi")
    w.listeners += log_connection_events
    while True:
        w.update()

if __name__ == '__main__':
    monitor()
