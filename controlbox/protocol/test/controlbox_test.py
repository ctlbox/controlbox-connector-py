import unittest
from io import BufferedReader
from io import BytesIO

from hamcrest import assert_that, is_, equal_to, not_

from controlbox.conduit.base import DefaultConduit
from controlbox.protocol.controlbox import ControlboxProtocolV1, build_chunked_hexencoded_conduit, ResponseDecoder
from controlbox.protocol.io import RWCacheBuffer, CaptureBufferedReader


class BrewpiV030ProtocolSendRequestTestCase(unittest.TestCase):

    def setUp(self):
        self.conduit = DefaultConduit(BytesIO(), BytesIO())
        self.sut = ControlboxProtocolV1(self.conduit, lambda: None)

    def test_send_read_command_bytes(self):
        self.sut.read_value([1, 2, 3], 0x23)
        self.assert_request_sent(1, 0x81, 0x82, 3, 0x23, 0)

    def test_send_write_command_bytes(self):
        self.sut.write_value([1, 2, 3], 0x23, [4, 5])
        self.assert_request_sent(2, 0x81, 0x82, 3, 0x23, 2, 4, 5)

    def test_send_create_object_command_bytes(self):
        self.sut.create_object([1, 2, 3], 27, [4, 5, 6])
        self.assert_request_sent(3, 0x81, 0x82, 3, 27, 3, 4, 5, 6)

    def test_send_delete_object_command_bytes(self):
        self.sut.delete_object([1, 2], 23)
        self.assert_request_sent(4, 0x81, 2, 23)

    def test_send_list_profile_command_bytes(self):
        self.sut.list_profile(4)
        self.assert_request_sent(5, 4)

    def test_send_next_slot_object_command_bytes(self):
        self.sut.next_slot([1, 4])
        self.assert_request_sent(6, 0x81, 4)

    def assert_request_sent(self, *args):
        expected = bytes(args)
        actual = self.conduit.output.getvalue()
        assert_that(actual, equal_to(expected))


def assert_future(future, match):
    assert_that(future.done(), is_(True), "expected future to be complete")
    assert_that(future.value(), match)


class BrewpiV030ProtocolDecodeResponseTestCase(unittest.TestCase):

    def setUp(self):
        self.input_buffer = RWCacheBuffer()
        self.output_buffer = RWCacheBuffer()
        self.conduit = DefaultConduit(
            self.input_buffer.reader, self.output_buffer.writer)
        self.sut = ControlboxProtocolV1(self.conduit)

    def test_send_read_command_bytes(self):
        future = self.sut.read_value([1, 2, 3], 0x23)
        # emulate a on-wire response
        self.push_response([1, 0x81, 0x82, 3, 0x23, 0, 2, 4, 5])
        assert_future(future, is_(equal_to((bytes([4, 5]),))))

    def test_resposne_must_match(self):
        """ The command ID is the same but the request data is different. So this doesn't match up with the previous.
            Request. """
        future = self.sut.read_value([1, 2, 3], 23)
        self.push_response([1, 0x81, 0x82, 0, 23, 4, 2, 4, 5])
        assert_that(future.done(), is_(False))

    def test_multiple_outstanding_requests(self):
        """ Tests the requests are matched as the corresponding responses are received."""
        type_id = 23
        future1 = self.sut.read_value([1, 2, 3], type_id)
        future2 = self.sut.read_value([1, 2, 4], type_id)

        # push all the data, to be sure that
        self.push_response([1, 0x81, 0x82, 4, type_id, 0, 2, 2, 3])         # matches request 2
        assert_future(future2, is_(equal_to((bytes([2, 3]),))))
        assert_that(future1.done(), is_(False))
        self.push_response([1, 0x81, 0x82, 3, type_id, 0, 3, 4, 5, 6]
                           )      # matches request 1
        assert_future(future1, is_(equal_to((bytes([4, 5, 6]),))))

    def push_response(self, data):
        self.input_buffer.writer.write(bytes(data))
        self.input_buffer.writer.flush()
        self.sut.read_response()


class BrewpiV030ProtocolHexEncodingTestCase(unittest.TestCase):
    """ A more complete test where multiple commands are sent, and the on-wire hex-encoded values are used. """

    def setUp(self):
        self.input_buffer = RWCacheBuffer()
        self.output_buffer = RWCacheBuffer()
        # this represents the far end of the pipe - input/output bytes sent as
        # hex encoded binary
        self.conduit = DefaultConduit(
            self.input_buffer.reader, self.output_buffer.writer)
        text = build_chunked_hexencoded_conduit(self.conduit)
        self.sut = ControlboxProtocolV1(*text)

    def tearDown(self):
        self.input_buffer.close()
        self.output_buffer.close()

    def test_send_read_command_bytes(self):
        future = self.sut.read_value([1, 2, 3], 0x23)
        assert_that(future, is_(not_(None)))
        # NB: this is ascii encoded hex now, not binary data
        self.assert_request_sent(b'01 81 82 03 23 00 \n')

    def test_full_read_command_bytes(self):
        future = self.sut.read_value([1, 2, 3], 0x23)
        # emulate the response
        self.push_response(b'01 81 82 03 23 00 01 aB CD \n')
        assert_future(future, is_(equal_to((bytes([0xAB]),))))

    def push_response(self, data):
        self.input_buffer.writer.write(bytes(data))
        self.input_buffer.writer.flush()
        self.sut.read_response()

    def assert_request_sent(self, expected):
        actual = self.output_buffer.reader.readlines()[0]
        assert_that(actual, equal_to(expected))


class ResponseDecoderTest(unittest.TestCase):

    def test__parse_request_is_abstract(self):
        sut = ResponseDecoder()
        self.assertRaises(NotImplementedError, sut._parse_request, [])

    def test_read_chain_empty(self):
        self.assertEqual(bytearray(), self.chain_decode(bytes()))

    def test_read_chain_single(self):
        self.assertEqual(bytearray([56]), self.chain_decode(bytes([56])))

    def test_read_chain_multiple(self):
        self.assertEqual(bytearray([0x10, 0x20, 0x30]), self.chain_decode(bytes([0x90, 0xA0, 0x30])))

    def chain_decode(self, buffer):
        sut = ResponseDecoder()
        return sut._read_chain(CaptureBufferedReader(BufferedReader(BytesIO(buffer))))




if __name__ == '__main__':
    unittest.main()
