from unittest import TestCase
from unittest.mock import MagicMock, Mock, call, patch

import timeout_decorator
from hamcrest import assert_that, calling, contains, empty, equal_to, instance_of, is_, is_not, not_none, raises

from controlbox.connector.base import ConnectorError
from controlbox.connector_maintainance import ConnectionManager, MaintainedConnection, MaintainedConnectionLoop
from mock_matcher import not_called, called_once_with, called_once, called_with
from controlbox.protocol.io_test import debug_timeout
from controlbox.support.events import EventSource
from controlbox.support.retry_strategy import PeriodRetryStrategy


class MaintainedConnectionTest(TestCase):
    def setUp(self):
        self.connector = Mock()
        self.connector.events = EventSource()
        self.retry = 10
        self.events = Mock()
        self.resource = "water"
        self.retry_strategy = Mock()
        self.logger = Mock()
        self.sut = MaintainedConnection(self.resource, self.connector, self.retry_strategy, self.events, self.logger)

    def test_constructor(self):
        sut = self.sut
        assert_that(sut.retry_strategy, is_(self.retry_strategy))
        assert_that(sut.resource, is_(self.resource))
        assert_that(sut.connector, is_(self.connector))
        assert_that(sut.events, is_(self.events))
        assert_that(sut.connector.events)
        assert_that(sut.connector.events.handlers(), contains(sut._connector_events))

    def test_connector_events_are_propagated(self):
        event = Mock()
        self.connector.events.fire(event)
        self.events.fire.assert_called_once_with(event)

    def test_maintain_no_retry(self):
        self.retry_strategy.return_value = 5
        assert_that(self.sut.maintain(123), is_(False))
        self.retry_strategy.assert_called_with(123)

    def test_maintain_needs_retry(self):
        self.retry_strategy.return_value = 0
        self.sut._open = Mock()
        assert_that(self.sut.maintain(123), is_(True))
        self.retry_strategy.assert_called_with(123)
        assert_that(self.sut._open, called_once())

    def test_open_on_unavailable_connector(self):
        self.connector.available = False
        self.sut._open()
        self.assert_connect_not_tried()

    def test_open_on_already_open(self):
        self.connector.connected = True
        self.sut._open()
        self.assert_connect_not_tried()

    def set_connected(self):
        self.connector.connected = True

    def test_open_success(self):
        self.connector.available = True
        self.connector.connected = False
        self.connector.connect.side_effect = self.set_connected
        self.assert_connect_tried(True)

    def test_open_fail(self):
        self.connector.available = True
        self.connector.connected = False
        self.connector.connect.side_effect = ConnectorError()
        self.assert_connect_tried(True)

    def test_open_fail_not_logged(self):
        self.logger.isEnabledFor.return_value = False
        self.connector.available = True
        self.connector.connected = False
        self.connector.connect.side_effect = ConnectorError()
        self.assert_connect_tried(True)

    def test_close_not_connected(self):
        self.connector.connected = False
        assert_that(self.sut._close(), is_(False))
        assert_that(self.connector.disconnect, called_once())

    def test_close_connected(self):
        self.connector.connected = True
        assert_that(self.sut._close(), is_(True))
        assert_that(self.connector.disconnect, called_once())

    def test_maintain_will_open(self):
        self.retry_strategy.return_value = 0
        self.sut._open = Mock()
        assert_that(self.sut.maintain(0), is_(True))
        assert_that(self.sut._open, is_(called_once()))

    def test_maintain_will_not_open(self):
        self.retry_strategy.return_value = 5
        self.sut._open = Mock()
        assert_that(self.sut.maintain(0), is_(False))
        assert_that(self.sut._open, is_(not_called()))

    def assert_connect_not_tried(self):
        assert_that(self.sut._open(), is_(False))
        assert_that(self.connector.connect, is_(not_called()))

    def assert_connect_tried(self, open):
        assert_that(self.sut._open(), is_(open))
        assert_that(self.connector.connect, is_(called_once()))


class MaintainedConnectionLoopTest(TestCase):
    def setUp(self):
        self.maintained_connection = Mock()
        self.loop = Mock()
        self.sut = MaintainedConnectionLoop(self.maintained_connection, self.loop)
        assert_that(self.sut.start, is_(not_none()))
        assert_that(self.sut.stop, is_(not_none()))

    def test_connected_loop_invokes_loop(self):
        self.sut._connected_loop()
        assert_that(self.loop, is_(called_once_with(self.maintained_connection)))

    def test_connected_loop_not_defined(self):
        self.sut = MaintainedConnectionLoop(self.maintained_connection)
        self.sut._connected_loop()
        # nothing to assert, just that no exception is thrown

    @timeout_decorator.timeout(debug_timeout(2))
    @patch('time.sleep')
    def test_loop_run_only_while_connected(self, time_sleep):
        count = 2

        def disconnect(maintained_connection):
            maintained_connection.connector.connected = (self.loop.call_count < count)

        self.loop.side_effect = disconnect
        self.maintained_connection.retry_strategy.return_value = 0.1
        self.sut.stop_event.wait = Mock()
        # when
        self.sut.loop()
        # then
        assert_that(time_sleep.call_count, is_(count))
        assert_that(self.sut.stop_event.wait, is_(called_with(0.1)))
        assert_that(self.loop.call_count, is_(count))

    @timeout_decorator.timeout(debug_timeout(2))
    def test_runs_connected_loop_propagates_exception_closes_and_waits_for_retry(self):
        self.maintained_connection.connector.connected = True
        self.maintained_connection.retry_strategy.return_value = 0.1
        self.sut.stop_event.wait = Mock()
        self.sut._connected_loop = Mock(side_effect=ConnectorError)

        assert_that(calling(self.sut.loop), raises(ConnectorError))
        assert_that(self.maintained_connection.mock_calls, is_([call._open(), call._close(), call.retry_strategy()]))
        assert_that(self.sut.stop_event.wait, is_(called_once_with(0.1)))


class ConnectionManagerTest(TestCase):

    def test_construction(self):
        loop = Mock()
        sut = ConnectionManager(loop)
        assert_that(sut._connected_loop, is_(loop))
        assert_that(sut.connections, is_(equal_to(dict())))
        assert_that(sut.events, is_not(None))

    def test_add_listener(self):
        listener = Mock()
        sut = ConnectionManager()
        sut.events += listener
        listener.assert_not_called()

    def test_available(self):
        """ mocks an available resource and validates that the manager creates
        a managed connection"""
        listener = Mock()
        sut = ConnectionManager()
        sut.events += listener
        connector = Mock()
        mc = Mock()
        sut._new_maintained_connection = Mock(return_value=mc)
        mc.connector = connector
        # when
        sut.available("res", connector)
        # then
        listener.assert_not_called()
        mc.loop.start.assert_called_once()
        mc.loop.start.reset_mock()
        assert_that(sut.connections.get("res"), is_(mc))
        # reconnecting to the same doesn't create a new manager
        sut._new_maintained_connection.reset_mock()
        sut.available("res", connector)
        sut._new_maintained_connection.assert_not_called()
        mc.loop.start.assert_not_called()

    def test_available_same_connector(self):
        sut = ConnectionManager()
        mc = Mock()
        mc.connector = connector = Mock()
        sut._new_maintained_connection = Mock(return_value=mc)
        sut.available("res", connector)
        assert_that(mc.loop.start, is_(called_once()))
        assert_that(sut._new_maintained_connection, is_(called_once()))
        sut._new_maintained_connection.reset_mock()
        sut.available("res", connector)
        assert_that(sut._new_maintained_connection, is_(not_called()))
        assert_that(mc.loop.start, is_(not_called()))

    def test_available_new_connector(self):
        sut = ConnectionManager()
        connector, connector2 = Mock(), Mock()
        mc, mc2 = Mock(), Mock()
        mc.connector = connector
        mc2.connector = connector2
        sut._new_maintained_connection = Mock(side_effect=[mc, mc2])
        sut.available("res", connector)
        assert_that(sut._new_maintained_connection, is_(called_once()))
        sut._new_maintained_connection.reset_mock()
        sut.available("res", connector2)
        assert_that(sut._new_maintained_connection, is_(called_once()))
        assert_that(mc.loop.start, is_(called_once()))
        assert_that(mc.loop.stop, is_(called_once()))
        assert_that(mc2.loop.start, is_(called_once()))
        assert_that(mc2.loop.stop, is_(not_called()))

    def test_new_maintained_connection(self):
        loop_fn = Mock()
        sut = ConnectionManager(loop_fn, 20)
        res = MagicMock()
        connector = Mock()
        mc = sut._new_maintained_connection(res, connector, sut.retry_period, sut.events)
        assert_that(mc.retry_strategy, is_(equal_to((PeriodRetryStrategy(sut.retry_period)))))
        assert_that(mc.resource, is_(res))
        assert_that(mc.connector, is_(connector))
        assert_that(mc.events, is_(sut.events))
        # in order to validate the _new_managed_connection contract we need to validate
        # all the methods of the returned object, since in principle any object could be returned
        # here we short-circuit that and instead explicitly test the type, so that
        # we can keep validating the MaintainedConnection instance int the managed connection tests
        assert_that(mc, is_(instance_of(MaintainedConnection)))
        assert_that(mc.loop, is_(instance_of(MaintainedConnectionLoop)))
        assert_that(mc.loop._loop, is_(loop_fn))    # test is indirect - prefer to mock the class/constructor

    def test_unavailable(self):
        listener = Mock()
        sut = ConnectionManager()
        sut.events += listener      # add the event listener
        connection = MagicMock()
        loop = connection.loop
        sut._connections["res"] = connection
        # when
        sut.unavailable("res")
        # then
        assert_that(connection.loop, is_(None))
        listener.assert_not_called()         # listener is not called by the manager - it's invoked by the MaintainedConnection object
        assert_that(sut.connections, is_(empty()))
        loop.stop.assert_called_once()

    def test_unavailable_not_known_resource(self):
        sut = ConnectionManager()
        listener = Mock()
        sut.events += listener
        sut.unavailable("myconn")
        listener.assert_not_called()

    def test_update(self):
        sut = ConnectionManager()
        sut.events.publish = Mock()
        # when
        sut.update()
        sut.events.publish.assert_called_once()

    def test_maintain_empty(self):
        sut = ConnectionManager()
        sut.maintain()

    def test_maintain_connections(self):
        sut = ConnectionManager()
        connection, connection2 = Mock(), Mock()
        sut._connections["res"] = connection
        sut._connections["res2"] = connection2
        time = Mock(side_effect=[10, 11])
        sut.maintain(time)
        assert_that(connection.maintain, is_(called_once_with(10)))
        assert_that(connection2.maintain, is_(called_once_with(11)))

    def test_maintain_connections_exception(self):
        sut = ConnectionManager()
        connection, connection2 = Mock(), Mock()
        connection.maintain = Mock(side_effect=ConnectorError)
        sut._connections["res"] = connection
        sut._connections["res2"] = connection2
        time = Mock(side_effect=[10, 11])
        sut.maintain(time)
        assert_that(connection.maintain, is_(called_once_with(10)))
        assert_that(connection2.maintain, is_(called_once_with(11)))
        assert_that(connection._close, is_(called_once()))

