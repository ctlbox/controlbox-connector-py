import logging
from time import time
from unittest import TestCase
from unittest.mock import Mock, MagicMock
from hamcrest import assert_that, equal_to, is_not, is_, empty, instance_of
from controlbox.connector.base import Connector, ConnectorError
from controlbox.connector_facade import ControllerConnectionManager, ManagedConnection, ControllerDiscoveryFacade, \
    logger


class ManagedConnectionTest(TestCase):
    def test_constructor(self):
        events = Mock()
        resource = Mock()
        connector = Mock()
        sut = ManagedConnection(resource, connector, 5, events)
        assert_that(sut.resource, is_(resource))
        assert_that(sut.connector, is_(connector))
        assert_that(sut.events, is_(events))
        assert_that(sut.last_opened, is_(None))
        assert_that(sut.retry_period, is_(5))
        connector.events.add.assert_called_with(sut._connector_events)

    def test_retry_connect(self):
        sut = ManagedConnection(object(), Connector(), 5, object())
        assert_that(sut._needs_retry(None), is_(True))
        start = time()
        sut.last_opened = start
        assert_that(sut._needs_retry(start), is_(False))
        assert_that(sut._needs_retry(start+5), is_(True))

    def test_maintain_not_connected(self):
        connector = Mock()
        connector.connected = False
        events = Mock()
        sut = ManagedConnection(object(), connector, 5, events)
        time = 50
        sut.maintain(time)
        assert_that(sut.last_opened, is_(50))
        connector.connect.assert_called_once()

    def test_maintain_not_connected_connect_exception(self):
        connector = Mock()
        connector.connected = False
        connector.connect.side_effect = ConnectorError()
        events = Mock()
        sut = ManagedConnection(object(), connector, 5, events)
        time = 50
        sut.maintain(time)
        assert_that(sut.last_opened, is_(50))
        connector.connect.assert_called_once()
        events.fire.assert_not_called()

    def test_maintain_nconnected(self):
        connector = Mock()
        connector.connected = True
        events = Mock()
        sut = ManagedConnection(object(), connector, 5, events)
        time = 50
        sut.maintain(time)
        assert_that(sut.last_opened, is_(50))
        connector.connect.assert_not_called()
        events.fire.assert_not_called()

    def test_close_connected(self):
        connector = Mock()
        connector.connected = True
        events = Mock()
        sut = ManagedConnection(object(), connector, 5, events)
        sut._close()
        connector.disconnected.assert_called_once()

    def test_close_disconnected(self):
        connector = Mock()
        connector.connected = False
        events = Mock()
        sut = ManagedConnection(object(), connector, 5, events)
        sut._close()
        connector.disconnected.assert_not_called()
        events.fire.assert_not_called()


class ControllerConnectionManagerTest(TestCase):

    def test_construction(self):
        sut = ControllerConnectionManager()
        assert_that(sut.connections, is_(equal_to(dict())))
        assert_that(sut.events, is_not(None))

    def test_add_listener(self):
        listener = Mock()
        sut = ControllerConnectionManager()
        sut.events += listener
        listener.assert_not_called()

    def test_connected(self):
        """ mocks a connected resource and validates that the manager creates
        a managed connection"""
        listener = Mock()
        sut = ControllerConnectionManager()
        sut.events += listener
        connector = Mock()
        mc = Mock()
        sut._new_managed_connection = Mock(return_value=mc)
        mc.connector = connector
        # when
        sut.connected("res", connector)
        # then
        listener.assert_not_called()
        assert_that(sut.connections.get("res"), is_(mc))
        # reconnecting to the same doesn't create a new manager
        sut._new_managed_connection.reset_mock()
        sut.connected("res", connector)
        sut._new_managed_connection.assert_not_called()
        mc.start.assert_called_once()

    def test_new_managed_connection(self):
        sut = ControllerConnectionManager(20)
        res = MagicMock()
        connector = Mock()
        mc = sut._new_managed_connection(res, connector, sut.retry_period, sut.events)
        assert_that(mc.last_opened, is_(None))
        assert_that(mc.resource, is_(res))
        assert_that(mc.retry_period, is_(20))
        assert_that(mc.connector, is_(connector))
        assert_that(mc.events, is_(sut.events))
        # in order to validate the _new_managed_connection contract we need to validate
        # all the methods of the returned object, since in principle any object could be returned
        # here we short-circuit that and instead explicitly test the type, so that
        # we can keep validating the ManagedConnection instance int the managed connection tests
        assert_that(mc, is_(instance_of(ManagedConnection)))

    def test_disconnected(self):
        listener = Mock()
        sut = ControllerConnectionManager()
        sut.events += listener
        connection = Mock()
        connection.close = Mock()
        sut._connections["res"] = connection
        # when
        sut.disconnected("res")
        # then
        # listener is not called by the manager - it's invoked by the ManagedConnection object
        listener.assert_not_called()
        assert_that(sut.connections, is_(empty()))
        connection.close.assert_called_once()

    def test_disconnected_not_known(self):
        sut = ControllerConnectionManager()
        listener = Mock()
        sut.events += listener
        sut.disconnected("myconn")
        listener.assert_not_called()

    def test_update(self):
        sut = ControllerConnectionManager()
        sut.events.publish = Mock()
        # when
        sut.update()
        sut.events.publish.assert_called_once()


def monitor():
    """ logs the connected devices. A dummy protocol sniffer is used. """
    logging.root.setLevel(logging.INFO)
    logging.root.addHandler(logging.StreamHandler())

    builder = ControllerDiscoveryFacade

    # just use the connector as the protocol
    def sniffer(x):
        return x

    def handle_connections(connectors):
        for c in connectors:
            try:
                conduit = c.connector.conduit
                if conduit and conduit.open:
                    conduit.input.read()
                    conduit.output.write(b"[]\n")
                    conduit.output.flush()
            except Exception as e:
                logger.exception(e)
                pass

    discoveries = (builder.build_serial_discovery(sniffer),
                   builder.build_tcp_server_discovery(sniffer, "brewpi"))
    facade = builder(discoveries)
    while True:
        # detect any new
        facade.update()
        handle_connections(facade.manager.connections.values())

if __name__ == '__main__':
    monitor()
