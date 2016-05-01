import unittest
from unittest.mock import Mock, call

from hamcrest import assert_that, is_

from controlbox.support.events import EventSource


class EventsTest(unittest.TestCase):

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
