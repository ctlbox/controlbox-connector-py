import unittest
from io import BufferedReader
from io import BytesIO
from unittest.mock import Mock

from hamcrest import assert_that, is_, equal_to, not_, calling, raises, contains, instance_of

from controlbox.conduit.base import DefaultConduit
from controlbox.protocol.controlbox import ControlboxProtocolV1, build_chunked_hexencoded_conduit, ResponseDecoder, \
    ResponseDecoderSupport, CommandResponse, Commands
from controlbox.protocol.io import RWCacheBuffer, CaptureBufferedReader
from controlbox.protocol.io_test import assert_delegates


class ControlboxProtocolV1TestCase(unittest.TestCase):

    def setUp(self):
        self.conduit = Mock()
        self.sut = ControlboxProtocolV1(self.conduit)

    def test_handle_async_response_is_registered(self):
        assert_that(self.sut._unmatched, contains(self.sut.handle_async_response))

    def test_handle_async_response(self):
        response = CommandResponse([0x8A], Mock(), Mock())
        self.sut.async_log_handlers = Mock()
        # when
        self.sut.handle_async_response(response)
        # then
        self.sut.async_log_handlers.fire.assert_called_once_with(response)

    def test_create_unknown_response_decoder(self):
        assert_that(calling(self.sut._create_response_decoder).with_args(123456),
                    raises(ValueError, "no decoder for cmd_id 123456"))

    def test__str__(self):
        assert_that(str(self.sut), is_("v0.3.0"))


class ControlboxProtocolV1SendRequestTestCase(unittest.TestCase):

    def setUp(self):
        self.conduit = DefaultConduit(BytesIO(), BytesIO())
        self.sut = ControlboxProtocolV1(self.conduit)  # pragma no cover - bug? says doesn't jump to exit

    def test_send_read_command_bytes(self):
        self.sut.read_value([1, 2, 3], 0x23, 45)
        self.assert_request_sent(1, 0x81, 0x82, 3, 0x23, 45)

    def test_send_read_command_bytes_optional_length(self):
        self.sut.read_value([1, 2, 3], 0x23)
        self.assert_request_sent(1, 0x81, 0x82, 3, 0x23, 0)

    def test_send_read_command_bytes_optional_type(self):
        self.sut.read_value([1, 2, 3])
        self.assert_request_sent(1, 0x81, 0x82, 3, 0, 0)

    def test_send_write_command_bytes(self):
        self.sut.write_value([1, 2, 3], 0x23, [4, 5])
        self.assert_request_sent(2, 0x81, 0x82, 3, 0x23, 2, 4, 5)

    def test_send_write_masked_command_bytes(self):
        self.sut.write_masked_value([1, 2, 3], 0x23, [4, 5], [14, 15])
        self.assert_request_sent(0x11, 0x81, 0x82, 3, 0x23, 2, 4, 14, 5, 15)

    def test_send_write_masked_buffers_different_size(self):
        assert_that(calling(self.sut.write_masked_value).with_args([1, 2, 3], 0x23, [4, 5], [14, 15, 16]),
                    raises(ValueError, "mask and data buffer must be same length"))

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

    def test_send_reset_command_bytes(self):
        self.sut.reset(25)
        self.assert_request_sent(0x0b, 25)

    def test_send_create_profile_command_bytes(self):
        self.sut.create_profile()
        self.assert_request_sent(0x07)

    def test_send_delete_profile_command_bytes(self):
        self.sut.delete_profile(100)
        self.assert_request_sent(0x08, 100)

    def test_send_activate_profile_command_bytes(self):
        self.sut.activate_profile(100)
        self.assert_request_sent(0x09, 100)

    def test_send_list_profiles_command_bytes(self):
        self.sut.list_profiles()
        self.assert_request_sent(0x0e)

    def test_send_read_system_value_command_bytes(self):
        self.sut.read_system_value([1, 2, 3], 0x23, 45)
        self.assert_request_sent(0x0F, 0x81, 0x82, 3, 0x23, 45)

    def test_send_write_system_value_command_bytes(self):
        self.sut.write_system_value([1, 2, 3], 0x23, [4, 5])
        self.assert_request_sent(0x10, 0x81, 0x82, 3, 0x23, 2, 4, 5)

    def test_send_write_system_masked_command_bytes(self):
        self.sut.write_system_masked_value([1, 2, 3], 0x23, [4, 5], [14, 15])
        self.assert_request_sent(0x12, 0x81, 0x82, 3, 0x23, 2, 4, 14, 5, 15)

    def assert_request_sent(self, *args):
        expected = bytes(args)
        actual = self.conduit.output.getvalue()
        assert_that(actual, equal_to(expected))


def assert_future(future, match):
    assert_that(future.done(), is_(True), "expected future to be complete")
    assert_that(future.value(), match)


class ControlboxProtocolV1DecodeResponseTestCase(unittest.TestCase):

    def setUp(self):
        self.input_buffer = RWCacheBuffer()
        self.output_buffer = RWCacheBuffer()
        self.conduit = DefaultConduit(
            self.input_buffer.reader, self.output_buffer.writer)
        self.sut = ControlboxProtocolV1(self.conduit)

    def test_send_read_command_bytes(self):
        future = self.sut.read_value([1, 2, 3], 0x23)
        # emulate an on-wire response
        self.push_response([Commands.read_value, 0x81, 0x82, 3, 0x23, 0, 0x24, 2, 4, 5])
        assert_future(future, is_(equal_to((0x24, bytes([4, 5])))))

    def test_send_write_command_bytes(self):
        future = self.sut.write_value([1, 2, 3], 0x23, [4, 5, 6])
        # emulate an on-wire response
        self.push_response([Commands.write_value, 0x81, 0x82, 3, 0x23, 3, 4, 5, 6, 0x24, 2, 7, 8])
        assert_future(future, is_(equal_to((0x24, bytes([7, 8])))))

    def test_send_write_mask_command_bytes(self):
        future = self.sut.write_masked_value([1, 2, 3], 0x23, [4, 5, 6], [7, 8, 9])
        # emulate an on-wire response
        self.push_response([Commands.write_masked_value, 0x81, 0x82, 3, 0x23, 3, 4, 7, 5, 8, 6, 9, 0x24, 2, 7, 8])
        assert_future(future, is_(equal_to((0x24, bytes([7, 8])))))

    def test_send_create_object_command_bytes(self):
        future = self.sut.create_object([1, 2, 3], 0x23, [4, 5, 6])
        self.push_response(
            [Commands.create_object, 0x81, 0x82, 3, 0x23, 3, 4, 5, 6, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_send_delete_object_command_bytes(self):
        future = self.sut.delete_object([1, 2, 3], 0x23)
        self.push_response(
            [Commands.delete_object, 0x81, 0x82, 3, 0x23, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_send_list_profile_command_bytes(self):
        future = self.sut.list_profile(1)
        self.push_response(
            [Commands.list_profile, 1, 127,
             3, 1, 0x23, 2, 3, 4,
             3, 0x81, 2, 0x24, 0, 0])
        assert_future(future, is_(equal_to((127, [
            (bytes([1]), 0x23, bytes([3, 4])),
            (bytes([1, 2]), 0x24, bytes())
        ]))))

    def test_send_list_profile_failed_command_bytes(self):
        future = self.sut.list_profile(1)
        self.push_response([Commands.list_profile, 1, 254])
        assert_future(future, is_(equal_to((-2, []))))

    def test_send_next_free_slot_command_bytes(self):
        future = self.sut.next_slot([0x81, 0x82, 3])
        self.push_response([Commands.next_free_slot, 0x81, 0x82, 3, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_send_next_free_slot_root_command_bytes(self):
        future = self.sut.next_slot([])
        self.push_response([Commands.next_free_slot_root, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_create_profile_command_bytes(self):
        future = self.sut.create_profile()
        self.push_response([Commands.create_profile, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_delete_profile_command_bytes(self):
        future = self.sut.delete_profile(3)
        self.push_response([Commands.delete_profile, 3, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_activate_profile_command_bytes(self):
        future = self.sut.activate_profile(2)
        self.push_response([Commands.activate_profile, 2, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_list_profiles_command_bytes(self):
        future = self.sut.list_profiles()
        self.push_response([Commands.list_profiles, 0xFF, 1, 4, 55])
        assert_future(future, is_(equal_to((-1, bytes((1, 4, 55))))))

    def test_reset_response_command_bytes(self):
        future = self.sut.reset(45)
        self.push_response([Commands.reset, 45, 254])
        assert_future(future, is_(equal_to((-2,))))

    def test_log_values_in_root_command_bytes(self):
        status = 2
        future = self.sut.log_values()
        self.push_response([Commands.log_values, 0, status,
                            1, 1, 0x23, 2, 3, 4,
                            1, 0x81, 2, 0x24, 0,
                            0])
        assert_future(future, is_(equal_to((status, [
            (bytes([1]), 0x23, bytes([3, 4])),
            (bytes([1, 2]), 0x24, bytes())
        ]))))

    def test_log_values_chain(self):
        status = 2
        future = self.sut.log_values([1, 2, 3])
        self.push_response([Commands.log_values, 1, 0x81, 0x82, 3, status,
                            1, 1, 0x23, 2, 3, 4,
                            1, 0x81, 2, 0x24, 0,
                            0])
        assert_future(future, is_(equal_to((status, [
            (bytes([1]), 0x23, bytes([3, 4])),
            (bytes([1, 2]), 0x24, bytes())
        ]))))

    def test_log_values_fail(self):
        future = self.sut.log_values()
        self.push_response([Commands.log_values, 0, 254])
        assert_future(future, is_(equal_to((-2, []))))

    def test_send_read_system_command_bytes(self):
        future = self.sut.read_system_value([1, 2, 3], 0x23)
        # emulate an on-wire response
        self.push_response([Commands.read_system_value, 0x81, 0x82, 3, 0x23, 0, 0x24, 2, 4, 5])
        assert_future(future, is_(equal_to((0x24, bytes([4, 5])))))

    def test_send_write_system_command_bytes(self):
        future = self.sut.write_system_value([1, 2, 3], 0x23, [4, 5, 6])
        # emulate an on-wire response
        self.push_response([Commands.write_system_value, 0x81, 0x82, 3, 0x23, 3, 4, 5, 6, 0x24, 2, 7, 8])
        assert_future(future, is_(equal_to((0x24, bytes([7, 8])))))

    def test_send_write_system_mask_command_bytes(self):
        future = self.sut.write_system_masked_value([1, 2, 3], 0x23, [4, 5, 6], [7, 8, 9])
        self.push_response([Commands.write_system_masked_value, 0x81, 0x82, 3, 0x23, 3, 4, 7, 5, 8, 6, 9,
                            0x24, 2, 7, 8])
        assert_future(future, is_(equal_to((0x24, bytes([7, 8])))))

    def test_send_async_log_command_bytes_fail(self):
        flags = 0
        self.push_data(
            [Commands.async_log_values, flags, 254])
        commandResponse = self.sut._decode_response()
        assert_that(commandResponse.parsed_request, is_(tuple()))
        assert_that(commandResponse.command_id, is_(Commands.async_log_values))
        expect_response = (flags, [], -2, 0, [])
        assert_that(commandResponse.parsed_response, is_(expect_response))

    def test_send_async_log_command_bytes_with_id(self):
        flags = 1
        self.push_data([Commands.async_log_values,
                        flags, 0x81, 0x82, 3, 0x00, 0x78, 0x56, 0x34, 0x12,
                        1, 1, 0x23, 2, 3, 4,
                        1, 0x81, 2, 0x24, 0,
                        0])
        commandResponse = self.sut._decode_response()
        assert_that(commandResponse.parsed_request, is_(tuple()))
        assert_that(commandResponse.command_id, is_(Commands.async_log_values))
        expect_response = (flags, bytes([1, 2, 3]), 0, 0x12345678,
                           [(bytes([1]), 0x23, bytes([3, 4])),
                           (bytes([1, 2]), 0x24, bytes())])
        assert_that(commandResponse.parsed_response, is_(expect_response))

    def test_respose_must_match(self):
        """ The command ID is the same but the request data is different. So this doesn't match up with the previous.
            Request. """
        future = self.sut.read_value([1, 2, 3], 23)
        self.push_response([1, 0x81, 0x82, 0, 23, 0, 4, 2, 4, 5])
        assert_that(future.done(), is_(False))

    def test_multiple_outstanding_requests(self):
        """ Tests the requests are matched as the corresponding responses are received."""
        type_id = 23
        future1 = self.sut.read_value([1, 2, 3], type_id)
        future2 = self.sut.read_value([1, 2, 4], type_id)

        # push all the data, to be sure that
        self.push_response([1, 0x81, 0x82, 4, type_id, 0, type_id, 2, 2, 3])         # matches request 2
        assert_future(future2, is_(equal_to((type_id, bytes([2, 3])))))
        assert_that(future1.done(), is_(False))
        self.push_response([1, 0x81, 0x82, 3, type_id, 0, type_id, 3, 4, 5, 6]
                           )      # matches request 1
        assert_future(future1, is_(equal_to((type_id, bytes([4, 5, 6])))))

    def push_data(self, data):
        self.input_buffer.writer.write(bytes(data))
        self.input_buffer.writer.flush()

    def push_response(self, data):
        self.push_data(data)
        self.sut.read_response()

    def test__decode_response_when_empty(self):
        self.sut.next_chunk_input = Mock()
        result = self.sut._decode_response()
        self.sut.next_chunk_input.assert_called_once()
        assert_that(result, is_(None))

    def test__decode_response_zero_command_id(self):
        self.push_data([0])
        self.sut.next_chunk_input = Mock()
        result = self.sut._decode_response()
        self.sut.next_chunk_input.assert_called_once()
        assert_that(result, is_(None))

    def test__decode_response_no_decoded_value(self):
        self.push_data([1, 2, 3])
        decoder = Mock()
        decoder.parse_request.return_value = [2, 3], 23
        decoder.parse_response.return_value = None
        self.sut._create_response_decoder = Mock(return_value=decoder)
        assert_that(calling(self.sut._decode_response), raises(ValueError, "request decoder did not return a value"))

    def test__decode_response(self):
        self.push_data([1, 2, 3, 4, 5])
        decoder = Mock()
        decoder.parse_request = Mock(return_value=(bytes([1, 2, 3]), 23))
        decoder.parse_response = Mock(return_value=45)
        self.sut._create_response_decoder = Mock(return_value=decoder)
        result = self.sut._decode_response()
        decoder.parse_request.assert_called_once_with(1, self.sut.input)
        decoder.parse_response.assert_called_once_with(self.sut.input)
        assert_that(result, is_(instance_of(CommandResponse)))
        assert_that(result.response_key, is_(bytes([1, 2, 3])))
        assert_that(result.parsed_request, is_(23))
        assert_that(result.parsed_response, is_(45))
        assert_that(self.sut.input.read(1), is_(bytes()), "expected stream to be spooled")


class ControlboxProtocolV1HexEncodingTestCase(unittest.TestCase):
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
        self.push_response(b'01 81 82 03 23 00 24 01 aB CD \n')
        assert_future(future, is_(equal_to((0x24, bytes([0xAB])))))

    def push_response(self, data):
        self.input_buffer.writer.write(bytes(data))
        self.input_buffer.writer.flush()
        self.sut.read_response()

    def assert_request_sent(self, expected):
        actual = self.output_buffer.reader.readlines()[0]
        assert_that(actual, equal_to(expected))


class ResponseDecoderTest(unittest.TestCase):

    def setUp(self):
        self.sut = ResponseDecoderSupport()

    def test_is_abstract(self):
        assert_that(calling(ResponseDecoder), raises(TypeError))

    def test_parse_request(self):
        def parse(capture):
            assert_that(capture.read(1), is_(bytes([2])))
            assert_that(capture.read(1), is_(bytes([3])))
            assert_that(capture.read(1), is_(bytes([4])))
            assert_that(capture.read(1), is_(bytes([5])))
            assert_that(capture.read(1), is_(bytes()))
            return 12345

        self.sut._parse_request = Mock(side_effect=parse)
        stream = BytesIO(bytes([2, 3, 4, 5]))  # command ID is already parsed, remainder is the command request
        # when
        result = self.sut.parse_request(1, stream)
        # then
        assert_that(result, is_((bytes([1, 2, 3, 4, 5]), 12345)))

    def test_read_chain_single(self):
        self.assertEqual(bytearray([56]), self.chain_decode(bytes([56])))

    def test_read_chain_multiple(self):
        self.assertEqual(bytearray([0x10, 0x20, 0x30]), self.chain_decode(bytes([0x90, 0xA0, 0x30])))

    def test_read_id_chain(self):
        self.assert_delegates('_read_id_chain', '_read_chain', Mock())

    def assert_delegates(self, fn, delegate, *args):
        assert_delegates(self.sut, fn, delegate, *args)

    def test_read_type(self):
        self.assert_delegates('_read_type', '_read_signed_byte', Mock())

    def test_read_block_exact_size(self):
        stream = BytesIO(bytes([1, 2, 3]))
        result = self.sut._read_block(3, stream)
        assert_that(result, is_(bytes([1, 2, 3])))
        assert_that(stream.read(1), is_(bytes()), 'expected empty stream')

    def test_read_block_more_data_in_stream(self):
        stream = BytesIO(bytes([1, 2, 3]))
        result = self.sut._read_block(2, stream)
        assert_that(result, is_(bytes([1, 2])))
        assert_that(stream.read(1), is_(bytes([3])))

    def test_read_block_insufficient_data(self):
        stream = BytesIO(bytes([1, 2]))
        expected = self.sut._insufficient_data()
        assert_that(calling(self.sut._read_block).with_args(3, stream), raises(type(expected), str(expected)))

    def test_read_vardata_scale(self):
        # first byte is the size (unscaled), here it's 2, which becomes 4
        # because of the scale by 2
        stream = BytesIO(bytes([2, 2, 3, 4, 5, 6]))
        result = self.sut._read_vardata(stream, 2)
        assert_that(stream.read(1), is_(bytes([6])))
        assert_that(result, is_(bytes([2, 3, 4, 5])))

    def test_read_vardata(self):
        stream = BytesIO(bytes([4, 1, 2, 3, 4, 5, 6]))
        result = self.sut._read_vardata(stream)
        assert_that(stream.read(), is_(bytes([5, 6])))
        assert_that(result, is_(bytes([1, 2, 3, 4])))

    def test_read_signed_byte_negative(self):
        stream = BytesIO(bytes([129]))
        result = self.sut._read_signed_byte(stream)
        assert_that(result, is_(-127))

    def test_read_signed_byte(self):
        stream = BytesIO(bytes([125]))
        result = self.sut._read_signed_byte(stream)
        assert_that(result, is_(125))

    def test_read_byte(self):
        stream = BytesIO(bytes([200]))
        assert_that(self.sut._read_byte(stream), is_(200))

    def test_read_byte_no_data(self):
        stream = BytesIO(bytes())
        expected = self.sut._insufficient_data()
        assert_that(calling(self.sut._read_byte).with_args(stream), raises(type(expected), str(expected)))

    def test_read_byte_no_data_optional(self):
        stream = BytesIO(bytes())
        assert_that(self.sut._read_byte(stream, False), is_(bytes()))

    def test_read_status_code(self):
        self.assert_delegates('_read_status_code', '_read_signed_byte', Mock())

    def test_read_object_defn(self):
        stream = BytesIO(bytes([0x81, 2, 3, 3, 4, 5, 6]))
        result = self.sut._read_object_defn(stream)
        assert_that(result, is_((bytes([1, 2]), 3, bytes([4, 5, 6]))))

    def test_read_remainder_zero(self):
        stream = BytesIO(bytes([0, 0, 0]))
        assert_that(self.sut._read_remainder(stream), is_(bytes([0, 0, 0])))

    def test_read_remainder_empty(self):
        stream = BytesIO(bytes([]))
        assert_that(self.sut._read_remainder(stream), is_(bytes()))

    def test_has_next_negative(self):
        stream = Mock()
        stream.peek_next_byte.return_value = -1
        assert_that(self.sut._has_data(stream), is_(False))

    def test_has_next_positive(self):
        stream = Mock()
        stream.peek_next_byte.return_value = 0
        assert_that(self.sut._has_data(stream), is_(True))

    def test_must_have_next_fail(self):
        stream = BytesIO(bytes([1]))
        expected = self.sut._data_mismatch(1, 2)
        assert_that(calling(self.sut._must_have_next).with_args(stream, 2), raises(type(expected), str(expected)))

    def test_must_have_next_success(self):
        stream = BytesIO(bytes([2]))
        assert_that(self.sut._must_have_next(stream, 2), is_(None))
        assert_that(stream.read(), is_(bytes()), 'expected end of stream')

    def test_parse_response(self):
        self.assert_delegates('parse_response', '_parse_response', Mock())

    def chain_decode(self, buffer):
        sut = ResponseDecoderSupport()
        return sut._read_chain(CaptureBufferedReader(BufferedReader(BytesIO(buffer))))


class CommandResponseTest(unittest.TestCase):
    def test_properties(self):
        response = Mock()
        request = Mock()
        key = Mock()
        sut = CommandResponse(key, response, request)
        self.assertEqual(response, sut.parsed_response)
        self.assertEqual(request, sut.parsed_request)

    def test_command_id_is_first_item_in_request_key(self):
        key = [20, 1, 2, 3]
        request = response = Mock()
        sut = CommandResponse(key, response, request)
        self.assertEqual(sut.command_id, 20)


if __name__ == '__main__':  # pragma no cover
    unittest.main()
