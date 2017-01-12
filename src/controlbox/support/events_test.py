import unittest
from unittest.mock import Mock, call

from hamcrest import assert_that, is_, empty, equal_to

from controlbox.support.events import EventSource, QueuedEventSource


class EventsTest(unittest.TestCase):

    def test_handlers_empty(self):
        sut = EventSource()
        assert_that(sut.handlers(),is_(empty()))

    def test_handlers_not_empty(self):
        sut = EventSource()
        handler = Mock()
        sut.add(handler)
        assert_that(list(sut.handlers()),is_([handler]))

    def test_no_listeners(self):
        sut = EventSource()
        sut.fire(1)

    def test_manage_handlers(self):
        sut = EventSource()
        m1 = Mock()
        sut.add(m1)
        assert_that(sut._handlers, is_([m1]))

        sut.remove(m1)
        assert_that(sut._handlers, is_([]))

        sut.remove(m1)
        assert_that(sut._handlers, is_([]))

        sut += m1
        assert_that(sut._handlers, is_([m1]))

        sut -= m1
        assert_that(sut._handlers, is_([]))

    def test_fire_all_with_empty_events(self):
        sut = EventSource()
        m1 = Mock()
        sut.add(m1)
        sut.fire_all([])
        m1.assert_not_called()

    def test_listeners(self):
        sut = EventSource()
        l1 = Mock()
        l2 = Mock()
        sut += l1
        sut += l2
        sut.fire(1, v="hey")
        l1.assert_called_once_with(1, v="hey")
        l2.assert_called_once_with(1, v="hey")

        l1.reset_mock()
        l2.reset_mock()

        sut.fire_all([1, 2, 3])
        l1.has_calls([call(1), call(2), call(3)])


class QueuedEventSourceTest(unittest.TestCase):
    def test_constructor(self):
        sut = QueuedEventSource()
        assert_that(sut.event_queue.empty(), True)

    def test_fire_events(self):
        sut = QueuedEventSource()
        sut._fire_all = Mock()
        sut.event_queue.put(1)
        sut.event_queue.put(2)
        sut.publish()
        sut._fire_all.assert_called_once_with([1, 2])

    def test_fire_events_empty(self):
        sut = QueuedEventSource()
        sut._fire_all = Mock()
        sut.publish()
        sut._fire_all.assert_not_called()
