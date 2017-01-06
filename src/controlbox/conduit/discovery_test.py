import unittest
from unittest.mock import Mock

from hamcrest import assert_that, is_, equal_to
from controlbox.conduit.discovery import ResourceAvailableEvent, ResourceUnavailableEvent, PolledResourceDiscovery


class ResourceEventsTest(unittest.TestCase):
    def test_resource_available(self):
        sut = ResourceAvailableEvent(self, "123", "abcd")
        assert_that(sut.source, is_(self))
        assert_that(sut.key, is_("123"))
        assert_that(sut.resource, is_("abcd"))

    def test_resource_unavailable(self):
        sut = ResourceAvailableEvent(self, "123", "abcd")
        assert_that(sut.source, is_(self))
        assert_that(sut.key, is_("123"))
        assert_that(sut.resource, is_("abcd"))

    def test_resource_event_equality_same_instances(self):
        obj = object()
        obj2 = object()
        r1 = ResourceAvailableEvent(self, obj, obj2)
        r2 = ResourceAvailableEvent(self, obj, obj2)
        assert_that(r1, is_(equal_to(r2)))
        assert_that(r2, is_(equal_to(r1)))

    def test_resource_event_equality_distinct_instances(self):
        obj1 = "1" + "23"
        obj2 = "123"
        r1 = ResourceAvailableEvent(self, obj1, None)
        r2 = ResourceAvailableEvent(self, obj2, None)
        assert_that(r1, is_(equal_to(r2)))
        assert_that(r2, is_(equal_to(r1)))


class PolledResourceDiscoveryTest(unittest.TestCase):

    def test_empty_after_construction(self):
        sut = PolledResourceDiscovery()
        assert_that(sut.previous, is_(equal_to({})))

    def test_all_allowed_by_default(self):
        sut = PolledResourceDiscovery()
        assert_that(sut._is_allowed(1, 2), is_(True))

    def test_none_available_by_default(self):
        sut = PolledResourceDiscovery()
        assert_that(sut._fetch_available(), is_({}))

    def test_check_allowed_delegates_to_is_allowed(self):
        sut = PolledResourceDiscovery()
        sut._is_allowed = Mock(return_value=False)
        assert_that(sut._check_allowed(1, 2), is_(False))
        sut._is_allowed.assert_called_with(1, 2)

    def test_attach_template_method(self):
        sut = PolledResourceDiscovery()
        sut.attached = Mock(return_value=123)
        assert_that(sut._attach(1, 2), is_((1, 2)))
        sut.attached.assert_called_with(1, 2)

    def test_detach_template_method(self):
        sut = PolledResourceDiscovery()
        sut.detached = Mock(return_value=123)
        assert_that(sut._detach(1, 2), is_((1, 2)))
        sut.detached.assert_called_with(1, 2)

    def test_resource_added(self):
        """
        Validates that a ResourceUnavailableEvent is produced when a resource is removed.
        when removing a resource one of the comparison values is None so the
        _device_eq method is not called.
        """
        sut = PolledResourceDiscovery()
        sut._device_eq = Mock()
        events = sut._changed_events({1: "1"})
        assert_that(events, is_([ResourceAvailableEvent(sut, 1, "1")]))
        sut._device_eq.assert_not_called()

    def test_resource_removed(self):
        """
        Validates that a ResourceUnavailableEvent is produced when a resource is removed.
        when removing a resource one of the comparison values is None so the
        _device_eq method is not called.
        """
        sut = PolledResourceDiscovery()
        sut.previous = {1: "1"}
        sut._device_eq = Mock()
        events = sut._changed_events({})
        assert_that(events, is_([ResourceUnavailableEvent(sut, 1, "1")]))
        sut._device_eq.assert_not_called()

    def test_resource_changed(self):
        sut = PolledResourceDiscovery()
        sut.previous = {1: "1"}
        events = sut._changed_events({1: "11"})
        assert_that(events, is_([ResourceUnavailableEvent(sut, 1, "1"),
                                 ResourceAvailableEvent(sut, 1, "11")]))

    def test_resource_unchanged(self):
        sut = PolledResourceDiscovery()
        sut.previous = {1: "1"}
        events = sut._changed_events({1: "1"})
        assert_that(events, is_([]))

    def test_resource_is_same(self):
        sut = PolledResourceDiscovery()
        key = 1
        value = "1"
        sut.previous = {key: value}
        events = sut._changed_events({key: value})
        assert_that(events, is_([]))

    def test_device_eq_is_called(self):
        sut = PolledResourceDiscovery()
        sut.previous = {1: "1"}
        sut._device_eq = Mock(return_value=True)
        events = sut._changed_events({1: "2"})
        assert_that(events, is_([]))
        sut._device_eq.assert_called_with("2", "1")

    def test_filter_available_uses_check_allowed(self):
        sut = PolledResourceDiscovery()
        sut._check_allowed = Mock(side_effect=lambda key, device: key == 1)
        available = sut._filter_available({1: "1", 2: "2"})
        sut._check_allowed.assert_any_call(1, "1")
        sut._check_allowed.assert_any_call(2, "2")
        assert_that(available, is_({1: "1"}))

    def test_update(self):
        """
        fetches available
        filters available
        computes changes
        updates previous
        fires events
        """
        sut = PolledResourceDiscovery()
        available = {3: "3", 4: "4"}
        filtered = {3: "5"}
        events = "event"
        sut._fetch_available = Mock(return_value=available)
        sut._filter_available = Mock(return_value=filtered)
        sut._changed_events = Mock(return_value=events)
        sut.listeners.fire_all = Mock()

        sut.update()

        sut._fetch_available.assert_called_once()
        sut._filter_available.assert_called_once_with(available)
        sut._changed_events.assert_called_once_with(filtered)
        assert_that(sut.previous, is_(filtered))
        sut.listeners.fire_all.assert_called_once_with(events)
