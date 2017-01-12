from unittest import TestCase
from unittest.mock import Mock, call, patch, MagicMock, PropertyMock
import time
import timeout_decorator
from hamcrest import assert_that, calling, contains, is_, not_none, raises, empty, instance_of, equal_to, is_not
from hamcrest.core.base_matcher import BaseMatcher

from controlbox.connector.base import ConnectorError
from controlbox.connector_discovery_facade import MaintainedConnection, MaintainedConnectionLoop, ControllerConnectionManager, \
    ConnectionManager
from controlbox.protocol.io_test import debug_timeout
from controlbox.support.events import EventSource
from controlbox.support.retry_strategy import PeriodRetryStrategy


class MockMatcher(BaseMatcher):
    """
    allows hamcrest assertions involving mock methods
    e.g.
    assert_that(mock, not_called())
    this will be eventually factored out to a new package
    """

    def __init__(self, fn, args=()):
        self.fn = fn
        self.args = args

    def matches(self, mock, mismatch_description=None):
        return self._try_match(mock, True, mismatch_description)

    def _try_match(self, mock, capture_assertion_error, mismatch_description):
        method = getattr(mock, self.fn, None)
        matched = False
        try:
            if method:
                method(*self.args)
                matched = True
            else:
                if mismatch_description:
                    mismatch_description.append_text('mock does not have method %s', self.fn)
        except AssertionError as e:
            if not capture_assertion_error:
                raise e
            else:
                if mismatch_description:
                    mismatch_description.append_text('False')
        return matched

    def describe_to(self, description):
        message = "%s(%s) to be true" % (self.fn, ", ".join([str(a) for a in self.args]))
        description.append_text(message)
        return False


def called_with(*args):
    return MockMatcher('assert_called_with', args)


def called_once():
    return MockMatcher('assert_called_once')


def called_once_with(*args):
    return MockMatcher('assert_called_once_with', args)


def not_called():
    return MockMatcher('assert_not_called')


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
        sut = ControllerConnectionManager(20)
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


class ControllerConnectionManagerTest(TestCase):
    def test_invokes_protocol(self):
        sut = ControllerConnectionManager()
        maintained_connection = Mock()
        sut._connected_loop(maintained_connection)
        assert_that(maintained_connection.connector.protocol.read_response_async, is_(called_once())
                        )