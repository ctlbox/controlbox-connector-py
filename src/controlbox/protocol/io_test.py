import unittest
from unittest.mock import Mock

import sys
from hamcrest import is_, assert_that, calling, raises, equal_to

from controlbox.protocol.async import UnknownProtocolError
from controlbox.protocol.io import RWCacheBuffer, determine_line_protocol, CaptureBufferedReader


class RWCacheBufferTest(unittest.TestCase):
    def test_what_is_written_is_read(self):
        sut = RWCacheBuffer()
        sut.writer.write(b"abc")
        sut.writer.flush()
        read = sut.reader.read()
        sut.close()
        assert_that(read, is_(b"abc"))


class DecodeLineProtocolTest(unittest.TestCase):

    def test_no_protocols_recognize(self):
        none = Mock(return_value=None)
        conduit = Mock()
        conduit.readline.return_value = b"hey"
        assert_that(calling(determine_line_protocol).with_args(conduit, (none, none), raises(UnknownProtocolError)))

    def test_exception_ignored_if_recognized(self):
        def sniffer_except(line, conduit):
            raise ValueError("test")

        sniffer = Mock(side_effect=sniffer_except)
        protocol = object()
        accept = Mock(return_value=protocol)
        conduit = Mock()
        conduit.input.readline.return_value = b"hey"

        assert_that(determine_line_protocol(conduit, (sniffer, accept)), is_(protocol))
        sniffer.assert_called_once_with('hey', conduit)
        accept.assert_called_once_with('hey', conduit)

    def test_exception_raised_if_not_recognized(self):
        sniffer = Mock(side_effect=ValueError("test"))
        none = Mock(return_value=None)

        conduit = Mock()
        conduit.input.readline.return_value = b"hey"
        assert_that(calling(determine_line_protocol).with_args(conduit, (sniffer, none)), raises(UnknownProtocolError))
        sniffer.assert_called_once_with('hey', conduit)
        none.assert_called_once_with('hey', conduit)


class CaptureBufferedReaderTest(unittest.TestCase):

    def test_constructor(self):
        mock = Mock()
        sut = CaptureBufferedReader(mock)
        assert_that(sut.stream, is_(mock))

    def test_peek_delegates(self):
        mock = Mock()
        mock.peek = Mock(return_value=[1])
        sut = CaptureBufferedReader(mock)
        assert_that(sut.peek(), is_(equal_to([1])))

    def test_close_is_noop(self):
        mock = Mock()
        sut = CaptureBufferedReader(mock)
        sut.close()
        mock.close.assert_not_called()

    def test_peek_next_byte_end(self):
        mock = Mock()
        mock.peek.return_value = []
        sut = CaptureBufferedReader(mock)
        assert_that(sut.peek_next_byte(), is_(-1))

    def test_peek_next_byte(self):
        mock = Mock()
        mock.peek.return_value = [254]
        sut = CaptureBufferedReader(mock)
        assert_that(sut.peek_next_byte(), is_(254))


def assert_delegates(target, fn, delegate, *args):
    """
    asserts that the given method fn on object target calls the delegate function with the same arguments
    and propagates the result
    :param target:
    :param fn:
    :param delegate:
    :param args:
    :return:
    """
    mock = Mock(return_value=123)
    setattr(target, delegate, mock)
    assert_that(getattr(target, fn)(*args), is_(123))
    mock.assert_called_once_with(*args)


def debug_timeout(value):
    """
    Replaces the timeout value with a very large one if the tests are running under a debugger.
    This prevents the main thread from throwing an exception and exiting when the test timees out
    due to a breakpoint.
    :param value:
    :return:
    """
    return value if sys.gettrace() is None else 100000
