import unittest
from unittest.mock import Mock

from hamcrest import is_, assert_that, calling, raises

from controlbox.protocol.async import UnknownProtocolError
from controlbox.protocol.io import RWCacheBuffer, determine_line_protocol


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
