from unittest import TestCase
from unittest.mock import Mock

from hamcrest import assert_that, is_

from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent
from controlbox.discovery import ConnectorDiscovery, ManagedConnectorDiscoveries
from controlbox.protocol.io_test import assert_delegates
from mock_matcher import called_once_with, called_once, not_called


class ConnectorDiscoveryTest(TestCase):
    def setUp(self):
        self.discovery = Mock()
        self.factory = Mock()
        self.manager = Mock()
        self.sut = ConnectorDiscovery(self.discovery, self.factory, self.manager)

    def test_constructor(self):
        assert_that(self.discovery.listeners.add, called_once_with(self.sut.resource_event))

    def test_dispose(self):
        self.sut.dispose()
        assert_that(self.discovery.listeners.remove, called_once_with(self.sut.resource_event))

    def test_create_connector(self):
        assert_delegates(self.sut, '_create_connector', '_connector_factory', Mock(), Mock())

    def test_update(self):
        self.sut.update()
        assert_that(self.discovery.update, called_once())

    def test_resource_event_no_manager(self):
        self.sut.manager = None
        self.sut._create_connector = Mock()
        event = ResourceAvailableEvent(Mock(), Mock(), Mock())
        self.sut.resource_event(event)
        assert_that(self.sut._create_connector, not_called())

    def test_resource_event_available(self):
        event = ResourceAvailableEvent(Mock(), Mock(), Mock())
        connector = Mock()
        self.sut._create_connector = Mock(return_value=connector)

        assert_that(self.sut.resource_event(event), is_(None))

        assert_that(self.sut._create_connector, is_(called_once_with(event.key, event.resource)))
        assert_that(self.manager.available, is_(called_once_with(event.key, connector)))

    def test_resource_event_available_no_connector(self):
        event = ResourceAvailableEvent(Mock(), Mock(), Mock())
        connector = Mock()
        self.sut._create_connector = Mock(return_value=None)
        assert_that(self.sut.resource_event(event), is_(None))
        assert_that(self.sut._create_connector, is_(called_once_with(event.key, event.resource)))
        assert_that(self.manager.available, is_(not_called()))

    def test_resource_event_unavailable(self):
        event = ResourceUnavailableEvent(Mock(), Mock(), Mock())
        assert_that(self.sut.resource_event(event), is_(None))

        assert_that(self.factory, is_(not_called()))
        assert_that(self.manager.unavailable, is_(called_once_with(event.key)))

    def test_resource_event_unknown_type(self):
        event = []
        assert_that(self.sut.resource_event(event), is_(None))
        assert_that(self.factory, is_(not_called()))


class ManagedConnectorDiscoveriesTest(TestCase):
    def setUp(self):
        self.discoveries = [Mock(), Mock()]
        self.manager = Mock()
        self.sut = ManagedConnectorDiscoveries(self.discoveries, self.manager)

    def test_sets_manager(self):
        assert_that(self.discoveries[0].manager, is_(self.manager))
        assert_that(self.discoveries[1].manager, is_(self.manager))

    def test_update_on_manager_and_discoveries(self):
        self.sut.update()
        assert_that(self.discoveries[0].update, called_once())
        assert_that(self.discoveries[1].update, called_once())
        assert_that(self.manager.update, called_once())
