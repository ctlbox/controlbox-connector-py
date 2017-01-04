import io
import unittest
from io import BufferedReader

from hamcrest import assert_that, is_, equal_to, calling, raises
from unittest.mock import Mock
from controlbox.protocol.hexstream import HexToBinaryInputStream, ChunkedHexTextInputStream, BinaryToHexOutputStream


def h2bstream(content):
    base = io.BytesIO(content.encode("utf-8"))
    base = BufferedReader(base)
    result = HexToBinaryInputStream(base)
    return result


class HexToBinaryStreamTestCase(unittest.TestCase):

    def test_read_from_hex_stream(self):
        hex = h2bstream("FF00")
        assert_that(hex.has_next(), is_(True), "stream should have more data")
        assert_that(hex.peek(1), is_(equal_to(bytes([0xFF]))))
        assert_that(hex.read(1), is_(equal_to(bytes([0xFF]))))
        assert_that(hex.has_next(), is_(True), "stream should have more data")
        assert_that(hex.peek(1), is_(equal_to(bytes([0x00]))))
        assert_that(hex.read(1), is_(equal_to(bytes([0x00]))))
        assert_that(hex.has_next(), is_(False),
                    "stream should have no more data")
        assert_that(hex.peek(1), is_(equal_to(bytes())))
        assert_that(hex.read(1), is_(equal_to(bytes())))

    def test_flags(self):
        s = h2bstream("")
        assert_that(s.writable(), is_(False))
        assert_that(s.readable(), is_(True))


def collect_stream(stream):
    collect = bytearray()
    d = stream.read()
    while d:
        collect += d
        d = stream.read()
    return bytes(collect)


class ChunkedHexTextInputStreamTestCase(unittest.TestCase):

    def test_zero_length_read_returns_empty_array(self):
        base = BufferedReader(io.BytesIO(b"20 00 [[12] comment] AF cd "))
        text = ChunkedHexTextInputStream(base)
        assert_that(text.peek(1), is_(equal_to(b'2')))
        assert_that(text.read(0), is_(equal_to(bytes())))

    def test_example1(self):
        assert_that(self.stream_read(
            b"20 00 [[12] comment] AF cd "), equal_to(b"2000AFcd"))

    def test_ignores_comments(self):
        assert_that(self.stream_read(b"20 00 [comment]"), equal_to(b"2000"))

    def test_ignores_nested_comments(self):
        assert_that(self.stream_read(
            b"20 00 [ nested [comment] here ] FF"), equal_to(b"2000FF"))

    def test_newline_end_of_stream(self):
        assert_that(self.stream_read(
            b"20 00 [ nested [comment] here ]\n FF"), equal_to(b"2000"))

    def test_ignores_non_hex_chars(self):
        assert_that(self.stream_read(b"FfZfF"), equal_to(b"FffF"))

    def test_handles_empty_stream(self):
        assert_that(self.stream_read(b""), equal_to(b""))

    def test_flags(self):
        s = ChunkedHexTextInputStream(None)
        assert_that(s.writable(), is_(False))
        assert_that(s.readable(), is_(True))

    def test_read_or_peek_on_empty_stream_returns_empty(self):
        s = ChunkedHexTextInputStream(BufferedReader(io.BytesIO(b'a')))
        assert_that(s.peek(0), is_(equal_to(b'')))
        assert_that(s.peek(1), is_(equal_to(b'a')))
        assert_that(s.read(20), is_(equal_to(b'a')))
        assert_that(s.peek(1), is_(equal_to(b'')))
        assert_that(s.read(1), is_(equal_to(b'')))

    def stream_read(self, content):
        base = BufferedReader(io.BytesIO(content))
        text = ChunkedHexTextInputStream(base)
        return collect_stream(text)

    def test_stream_no_peek(self):
        stream = Mock()
        stream.read = Mock(return_value=[])
        sut = ChunkedHexTextInputStream(stream)
        assert_that(sut.read(), is_(equal_to(b'')))

    def test_empty_read_does_not_delegate(self):
        stream = Mock()
        stream.read = Mock(return_value=[])
        sut = ChunkedHexTextInputStream(stream)
        assert_that(sut.read(0), is_(equal_to(b'')))
        stream.read.assert_not_called()

    def test_stream_close(self):
        stream = Mock()
        stream.close = Mock(return_value=[])
        sut = ChunkedHexTextInputStream(stream)
        sut.close()
        stream.close.assert_not_called()


class BinaryToHexOutputStreamTestCase(unittest.TestCase):

    def test_write_bytes(self):
        store = io.BytesIO()
        stream = self.create_stream(store)
        stream.write([129, 255])
        assert_that(store.getvalue(), is_(equal_to(b"81 FF ")))

    def test_stream_must_be_writable(self):
        store = Mock()
        store.writable = Mock(return_value=False)
        assert_that(calling(self.create_stream).with_args(store), raises(ValueError))

    def test_write_annotation(self):
        store = io.BytesIO()
        stream = self.create_stream(store)
        stream.write_annotation(b"hello world")
        assert_that(store.getvalue(), is_(equal_to(b"[hello world]")))

    def test_write_bytes_and_annotation(self):
        store = io.BytesIO()
        stream = self.create_stream(store)
        stream.write_byte(129)
        stream.write_annotation(b"hello world")
        stream.write_byte(255)
        assert_that(store.getvalue(), is_(equal_to(b"81 [hello world]FF ")))

    def test_write_newline(self):
        store = io.BytesIO()
        stream = self.create_stream(store)
        stream.write_byte(129)
        stream.write_annotation(b"hello world")
        stream.newline()
        stream.write_byte(255)
        assert_that(store.getvalue(), is_(equal_to(b"81 [hello world]\nFF ")))

    def test_flags(self):
        store = io.BytesIO()
        s = self.create_stream(store)
        assert_that(s.writable(), is_(True))
        assert_that(s.readable(), is_(False))

    def create_stream(self, store):
        return BinaryToHexOutputStream(store)


class TextHexStreamTestCase(unittest.TestCase):

    def test_converts_hex_and_skips_spaces(self):
        assert_that(self.stream_read(b"20 01 40"),
                    is_(equal_to(b"\x20\x01\x40")))

    def test_bytes_must_contain_two_hex_digits(self):
        assert_that(self.stream_read(b"20 01 4"), is_(equal_to(b"\x20\x01")))

    def test_comments_ignored(self):
        assert_that(self.stream_read(
            b"20 [comment 01] 40"), is_(equal_to(b"\x20\x40")))

    def test_no_read_past_newline(self):
        stream = self.build_stream(b"12 34 \n 56")
        assert_that(collect_stream(stream), is_(equal_to(b"\x12\x34")))
        assert_that(collect_stream(stream), is_(equal_to(b"")),
                    "once a newline is received the stream should return no further data")
        # unwrap the hex stream and the text steam back to the binary buffer
        buffer = stream.detach().detach()
        assert_that(collect_stream(buffer), is_(equal_to(b" 56")))

    def test_can_read_past_newline_after_reset(self):
        stream = self.build_stream(b"12 34 \n 56  [12] ")
        assert_that(collect_stream(stream), is_(equal_to(b"\x12\x34")))
        assert_that(collect_stream(stream), is_(equal_to(b"")),
                    "once a newline is received the stream should return no further data")
        stream.stream.next_chunk()
        assert_that(collect_stream(stream), is_(equal_to(b"\x56")))
        buffer = stream.detach().detach()
        assert_that(collect_stream(buffer), is_(equal_to(b"")),
                    "expected base stream to be completely read")

    def test_read_bytes(self):
        stream = self.build_stream(b"12 34 \n 56  [12] ")
        assert_that(stream.read_next_byte(), is_(equal_to(0x12)))
        assert_that(stream.read_next_byte(), is_(equal_to(0x34)))
        assert_that(calling(stream.read_next_byte), raises(StopIteration))
        assert_that(stream.peek_next_byte(), is_(equal_to(-1)))
        stream.stream.next_chunk()
        assert_that(stream.peek_next_byte(), is_(0x56))
        assert_that(stream.read_next_byte(), is_(equal_to(0x56)))
        assert_that(calling(stream.read_next_byte), raises(StopIteration))

    def test_flags(self):
        s = self.build_stream(b"")
        assert_that(s.writable(), is_(False))
        assert_that(s.readable(), is_(True))

    def test_peek_count_zero(self):
        sut = self.build_stream(b"content")
        assert_that(sut.peek())

    def build_stream(self, content):
        base = BufferedReader(io.BytesIO(content))
        text = ChunkedHexTextInputStream(base)
        hexstream = HexToBinaryInputStream(text)
        return hexstream

    def stream_read(self, content):
        hexstream = self.build_stream(content)
        return collect_stream(hexstream)

