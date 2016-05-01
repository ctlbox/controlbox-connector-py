import unittest
from unittest.mock import Mock

from hamcrest import assert_that, is_, raises, calling, instance_of

from controlbox.connector.base import ConnectorEvent, ConnectorConnectedEvent, ConnectorDisconnectedEvent, Connector
from controlbox.support.events import EventSource


class ConnectorEventsTest(unittest.TestCase):

    def test_connector_event(self):
        self.assert_event(ConnectorEvent)
        self.assert_event(ConnectorConnectedEvent)
        self.assert_event(ConnectorDisconnectedEvent)

    def assert_event(self, event_class):
        source = Mock()
        event = event_class(source)
        assert_that(event.connector, is_(source))
        source.assert_not_called()


class ConnectorTest(unittest.TestCase):
    def test_abstract_methods(self):
        sut = Connector()
        assert_that(sut.events, is_(instance_of(EventSource)))
        assert_that(calling(sut.disconnect), raises(NotImplementedError))
        assert_that(calling(sut.connect), raises(NotImplementedError))
        # testing properties is a little strange since the property access has to be deffered
        # or it will throw an exception outside the scope of the assert test.
        assert_that(calling(getattr).with_args(sut, 'endpoint'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'connected'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'available'), raises(NotImplementedError))
        assert_that(calling(getattr).with_args(sut, 'conduit'), raises(NotImplementedError))
