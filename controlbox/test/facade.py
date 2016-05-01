from unittest import TestCase
from unittest.mock import Mock, MagicMock

from hamcrest import assert_that, equal_to, is_not, is_, empty, instance_of

from controlbox.facade import ControllerConnectionManager, ManagedConnection


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
        sut._new_managed_connection = Mock(return_value="mc")
        # when
        sut.connected("res", connector)
        # then
        listener.assert_not_called()
        assert_that(sut.connections.get("res"), is_("mc"))

    def test_new_managed_connection(self):
        sut = ControllerConnectionManager()
        res = MagicMock()
        connector = Mock()
        mc = sut._new_managed_connection(res, connector, sut.retry_period, sut.events)
        assert_that(mc.last_opened, is_(None))
        assert_that(mc.resource, is_(res))
        assert_that(mc.retry_period, is_(30))
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
