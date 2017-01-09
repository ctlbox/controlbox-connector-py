"""
Provides an implementation of the controlbox protocol via the class ControlboxProtocolV1.
"""

from abc import abstractmethod
from io import BufferedIOBase

from controlbox.conduit.base import Conduit, ConduitStreamDecorator
from controlbox.protocol.async import BaseAsyncProtocolHandler, FutureResponse, Request, Response, ResponseSupport
from controlbox.protocol.hexstream import BinaryToHexOutputStream, ChunkedHexTextInputStream, HexToBinaryInputStream
from controlbox.protocol.io import CaptureBufferedReader
from controlbox.support.events import EventSource


def unsigned_byte(val):
    """Convert an unsigned byte to a corresponding 2's complement signed value.

    >>> unsigned_byte(0)
    0
    >>> unsigned_byte(-1)
    255
    >>> unsigned_byte(127)
    127
    >>> unsigned_byte(-128)
    128
    """
    return val if val >= 0 else val + 256


def signed_byte(b):
    """Convert an unsigned byte to a corresponding 2's complement signed value.

    >>> signed_byte(0)
    0
    >>> signed_byte(255)
    -1
    >>> signed_byte(127)
    127
    >>> signed_byte(128)
    -128
    """
    return b if b < 128 else b - 256


def encode_id(idchain) -> bytearray:
    """Encode a chain of integers to the on-wire binary values.

    >>> list(encode_id([1]))
    [1]

    >>> list(encode_id([1,2,3]))
    [129, 130, 3]

    >>> encode_id([])
    bytearray(b'')

    :return:a byte array representing an id chain to the comms format.
    :rtype:bytearray
    """
    l = len(idchain)
    result = bytearray(l)
    for x in range(0, l - 1):
        result[x] = idchain[x] | 0x80
    if l > 0:
        result[l - 1] = idchain[l - 1]
    return result


def encode_type_id(type):
    return type,


def decode_id(buf) -> list():
    """Decode a chain-id of known size.

    :param buf: The id_chain as the on-wire format.
    :return: A list of integers corresponding to the id chain

    >>> decode_id(bytearray([0x81, 0x82, 3]))
    [1, 2, 3]
    """
    return [(x & 0x7F) for x in buf]


class ByteArrayRequest(Request):
    """Represents a request as an array or bytes.

    The byte array defines the key for the request, since responses
    always repeat the request data verbatim.
    """
    def __init__(self, data: bytes):
        self.data = data

    def to_stream(self, file):
        file.write(self.data)

    @property
    def response_keys(self):
        """Return the key that unites the request and the response.

        Requests and responses are structured such that the entire command request is the unique key
        for the command.
        """
        return [self.data]


class Commands(object):
    """Describes the command name and the corresponding ID"""

    no_cmd = 0
    read_value = 1
    write_value = 2
    create_object = 3
    delete_object = 4
    list_profile = 5
    next_free_slot = 6
    create_profile = 7
    delete_profile = 8
    activate_profile = 9
    log_values = 0xA
    reset = 0xB
    next_free_slot_root = 0xC
    list_profiles = 0xE
    read_system_value = 0xF
    write_system_value = 0x10
    write_masked_value = 0x11
    write_system_masked_value = 0x12
    async_flag = 0x80
    async_log_values = async_flag | log_values


class CommandErrors:
    no_error = 0
    unknown_error = -1
    stream_error = -2
    profile_not_active = -3

    insufficient_persistent_storage = -16
    insufficient_heap = -17

    object_not_writable = -32
    object_not_readable = -33
    object_not_creatable = -34
    object_not_deletable = -35
    object_not_container = -36
    object_not_open_container = -37
    container_full = -38

    invalid_parameter = -64
    invalid_object_id = -65
    invalid_type = -66
    invalid_size = -67
    invalid_profile = -68
    invalid_id = -69


# A note to maintainers: These ResponseDecoder objects have to be written carefully - the
# _parse and _parse_response methods have to match exactly the command request and command response
# from the controlbox protocol.
# If _parse doesn't consume the right amount of bytes, the response will not be matched up with the
# corresponding request, and the caller will never get a response (and will eventually timeout on the
# FutureRequest.)

class ResponseDecoder(object,metaclass=ABCMeta):
    """Parses and decodes the response data from a stream, into
    logical components. For example, chain-ids are turned into a python list,
    and the individual fields of the response as defined in the protocol spec are
    decoded from the continuous stream as separate values.

    The stream includes the request data,
    which is parsed into the corresponding objects matching the original request
    and decodes the data block that is the additional response data.
    """

    def parse_request(self, cmd_id: int, stream: BufferedIOBase):
        """Read the portion of the response that corresponds to the original request.

        This delegates the main parsing of the command portion of the response to the
        _parse_request() method. The command isn't parsed into anything - only that we determine
        how much of the input buffer corresponds to the original command request.
        """
        capture = CaptureBufferedReader(stream)
        capture.push(bytes([cmd_id]))
        structure = self._parse_request(capture)
        return capture.as_bytes(), structure  # return the bytes read from the stream so far.

    @abstractmethod
    def _parse_request(self, buf):
        """Parse the buffer so that the content is validated, streamed and the semantic parts decoded/separated."""
        raise NotImplementedError

    def _read_chain(self, stream):
        """Read an id-chain from the stream.

        If the stream has no data, the result is an empty bytearray. Otherwise the result is one or more bytes.
        :param stream: A stream containing an optional byte < 128, prefixed by
            one or more bytes >= 128.
        :return: a bytearray containing the id-chain
        """
        result = bytearray()
        while self.has_data(stream):
            b = self._read_byte(stream)
            result.append(b & 0x7F)
            if b < 0x80:
                break
        return result

    def _read_id_chain(self, buf):
        return self._read_chain(buf)

    def _read_type_chain(self, buf):
        # a type is a large integer value encoded as one or more bytes
        # for now we assume values < 255 (1 byte length)
        # future schemes mwill use valus >= 128 as an escape code for larger values.
        return self._read_chain(buf)[0]

    def _read_block(self, size, stream):
        buf = bytearray(size)
        idx = 0
        while idx < size:
            buf[idx] = self._read_byte(stream)
            idx += 1
        return bytes(buf)

    def _read_vardata(self, stream, scale=1):
        """Decode variable length data from the stream.

        The first byte is the number of bytes in the data block,
        followed by N bytes that make up the data block.
            :param: scale the factor that the length in the stream is multiplied by.
                This is used when the unit of the scale isn't single bytes, such as with
                masked write values, where each byte is represented twice.
        """
        size = self._read_byte(stream) * scale
        return self._read_block(size, stream)

    @staticmethod
    def _read_signed_byte(stream):
        b = ResponseDecoder._read_byte(stream)
        return signed_byte(b)

    @staticmethod
    def _read_byte(stream):
        """Read the next byte from the stream.

        If there is no more data, an exception is thrown.
        bytes are returned as unsigned.
        """
        b = stream.read(1)
        if not b:
            raise ValueError("no more data in stream.")
        return b[0]

    def _read_status_code(self, stream):
        """Parse and return a status-code."""
        return self._read_signed_byte(stream)

    def _read_object_defn(self, buf):
        # the location to create the object
        id_chain = self._read_id_chain(buf)
        obj_type = self._read_byte(buf)  # the object_type of the object
        # the object constructor data block
        ctor_params = self._read_vardata(buf)
        return id_chain, obj_type, ctor_params

    def _read_object_value(self, buf):
        # the location to create the object
        id_chain = self._read_id_chain(buf)
        # the object constructor data block
        ctor_params = self._read_vardata(buf)
        return id_chain, ctor_params

    def _read_remainder(self, stream):
        """Read the remaining bytes in the stream into a list."""
        values = []
        while self.has_data(stream):
            value = self._read_byte(stream)
            values.append(value)
        return values

    def has_data(self, stream):
        return stream.peek_next_byte() >= 0

    def _must_have_next(self, stream, expected):
        next = stream.read_next_byte()
        if next != expected:
            raise ValueError('expected %d but got %b' % expected, next)

    def parse_response(self, stream):
        return self._parse_response(stream)

    @abstractmethod
    def _parse_response(self, stream):
        """Parse the stream response to an object.

        This is a template method to decode the command response. The value returned
        is the decoded response.
        """
        raise NotImplementedError()


class ReadValueResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        # read the id of the object to read
        id_chain = self._read_id_chain(buf)
        object_type = self._read_type_chain(buf)
        data_length = self._read_byte(buf)  # length of data expected
        return id_chain, object_type, data_length

    def _parse_response(self, stream):
        """Return the read command response whch is a single variable length buffer. """
        return self._read_vardata(stream),


class WriteValueResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        id_chain = self._read_id_chain(buf)  # id chain
        object_type = self._read_type_chain(buf)  # object object_type
        to_write = self._read_vardata(buf)  # length and body of data to write
        return id_chain, object_type, to_write

    def _parse_response(self, stream):
        """Return the write command response, which is a single variable length buffer indicating the value written. """
        return self._read_vardata(stream),


class WriteMaskedValueResponseDecoder(WriteValueResponseDecoder):
    def _parse_request(self, buf):
        id_chain = self._read_id_chain(buf)  # id chain
        object_type = self._read_type_chain(buf)  # object object_type
        to_write = self._read_vardata(buf, 2)  # data is 2x longer since the data and the mask are encoded
        return id_chain, object_type, to_write

        # use the superclass to decode the response - the response is the same as for a regular write


class WriteSystemMaskedValueResponseDecoder(WriteMaskedValueResponseDecoder):
    pass


class CreateObjectResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_object_defn(buf)

    def _parse_response(self, stream):
        """Return he create object command response, which is a status code. """
        return self._read_status_code(stream),


class DeleteObjectResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        id_chain = self._read_id_chain(buf),  # the location of the object to delete
        object_type = self._read_type_chain(buf)
        return id_chain, object_type

    def _parse_response(self, stream):
        """Return the delete object command response, which is a status code. """
        return self._read_status_code(stream),


class ListProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_signed_byte(buf),  # profile id

    def _parse_response(self, stream):
        """Retrieve a tuple, first value is list of tuples (id, object_type, data)"""
        # todo - more consistent if this returns a status code and then the object definitions
        # so we can distinguish between an error and an empty profile.
        values = []
        while self.has_data(stream):  # has more data
            self._must_have_next(stream, Commands.create_object)
            obj_defn = self._read_object_defn(stream)
            values.append(obj_defn)
        return values,


class NextFreeSlotResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_id_chain(buf),  # the container to find the next free slot

    def _parse_response(self, stream):
        """Return the next free slot command response is a byte indicating the next free slot."""
        return self._read_status_code(stream),


class NextFreeSlotRootResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):  # additional command arguments to read
        return tuple()

    def _parse_response(self, stream):
        """Return the next free slot command response is a byte indicating the next free slot. """
        return self._read_status_code(stream),


class CreateProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return tuple()

    def _parse_response(self, stream):
        """Return the new profile id or negative on error."""
        return self._read_status_code(stream),


class DeleteProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_byte(buf),  # profile_id

    def _parse_response(self, stream):
        """Parses and returns the command status code."""
        return self._read_status_code(stream),


class ActivateProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_byte(buf),  # profile id

    def _parse_response(self, stream):
        """Return the active profile id or negative on error."""
        return self._read_status_code(stream),


class ListProfilesResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return tuple()  # no additional command arguments

    def _parse_response(self, stream):
        # read active profile followed by available profiles
        r = self._read_remainder(stream)
        active_profile = signed_byte(r[0])  # active profile is signed
        return active_profile, r[1:]


class ResetResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):  # additional command arguments to read
        return self._read_byte(buf),  # flags

    def _parse_response(self, stream):
        """Parse the response from a stream and return a command status code."""
        return self._read_status_code(stream),


class LogValuesResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        id_chain = None
        flag = self._read_byte(buf)  # flag to indicate if an id is needed
        if flag & 1:
            id_chain = self._read_id_chain(buf)  # the id
        return flag, id_chain

    def _parse_response(self, stream):
        status = self._read_status_code(stream)
        values = []
        if status >= 0:
            while self.has_data(stream):  # has more data
                self._must_have_next(stream, Commands.read_value)
                id_chain = self._read_id_chain(stream)
                object_type = self._read_type_chain(stream)
                obj_state = self._read_vardata(stream)
                log = id_chain, object_type, obj_state
                values.append(log)
        return status, values


class ReadSystemValueResponseDecoder(ReadValueResponseDecoder):
    """Writing system values has the same format as writing user values."""


class WriteSystemValueResponseDecoder(WriteValueResponseDecoder):
    """Writing system values has the same format as writing user values."""


class ListSystemValuesResponseDecoder(ListProfileResponseDecoder):
    """Listing system values and listing user values (a profile) have the same format."""


class AsyncLogValueDecoder(LogValuesResponseDecoder):
    """Decodes the asynchronous logged values.

    This is similar to a regular logged value, although the
    flags and id_chain of the logged container are considered part of the response, rather than the request.
    The decided value for the response is a tuple (time, id_chain, values). The values is a list of tuples
    (id_chain, value) for each value logged in the hierarchy.
    """

    def _parse_request(self, buf):
        return tuple()  # command byte already parsed. That's all there is.

    def _parse_response(self, stream):
        id_chain = []
        time = self._read_block(4, stream)
        # flags - indicate if there is a id chain
        flags = self._read_byte(stream)
        if flags:
            id_chain = self._read_id_chain(stream)  # the id of the container
        # following this is a sequence of id_chain, len, data[] until the end
        # of stream
        values = []
        while self.has_data(stream):
            log_id_chain = self._read_id_chain(stream)
            log_obj_type = self._read_type_chain(stream)
            log_data = self._read_vardata(stream)
            values.append((log_id_chain, log_obj_type, log_data))
        return time, id_chain, values


class ChunkedHexEncodedConduit(ConduitStreamDecorator):
    chunker = None

    def _wrap_input(self, input):
        self.chunker = ChunkedHexTextInputStream(input)
        return HexToBinaryInputStream(self.chunker)

    def _wrap_output(self, output):
        return BinaryToHexOutputStream(output)

    def next_chunk_input(self):
        self.chunker.next_chunk()

    def next_chunk_output(self):
        self.output.newline()


def build_chunked_hexencoded_conduit(conduit):
    """Build a binary conduit that converts the binary data to ascii-hex digits and chunks data at newlines."""
    chunked = ChunkedHexEncodedConduit(conduit)
    return chunked, chunked.next_chunk_input, chunked.next_chunk_output


def nop():
    pass


def interleave(*args):
    """Interleave two or more buffers into a single buffer.

    >>> interleave(b'ABC', b'DEF')
    b'ADBECF'
    """
    return bytes([x for z in zip(*args) for x in z])


# def separate(buffer, count):
#     """De-interleave one buffer into two or more buffers.
#
#     >>> separate(b'ADBECF', 2)
#     (b'ABC', b'DEF')
#     """
#     return zip(*[buffer[i::count] for i in range(count)])


class CommandResponse(ResponseSupport):
    """Describes a response to a controlbox command."""

    def __init__(self, request_key, parsed_response, parsed_request):
        """Construct a CommandResponse from the parsed request and response.

        :param: request_key used to pair this response with the original request
        :param: parsed_response The parsed response data. The format depends upon the command.
        See _parse_request() of the corresponding command :class:`ResponseDecoder` subclass.
        :param:parsed_request
        See _parse_response() of the corresponding command ResponseDecoder subclass.
        """
        super().__init__(request_key, parsed_response)
        self._parsed_request = parsed_request

    @property
    def parsed_request(self):
        return self._parsed_request

    @property
    def parsed_response(self):
        return self._value

    @property
    def command_id(self):
        return self.response_key[0]


class ControlboxProtocolV1(BaseAsyncProtocolHandler):
    """Implements the controlbox hex-encoded binary protocol."""

    decoders = {
        Commands.read_value: ReadValueResponseDecoder,
        Commands.write_value: WriteValueResponseDecoder,
        Commands.create_object: CreateObjectResponseDecoder,
        Commands.delete_object: DeleteObjectResponseDecoder,
        Commands.list_profile: ListProfileResponseDecoder,
        Commands.next_free_slot: NextFreeSlotResponseDecoder,
        Commands.create_profile: CreateProfileResponseDecoder,
        Commands.delete_profile: DeleteProfileResponseDecoder,
        Commands.activate_profile: ActivateProfileResponseDecoder,
        Commands.reset: ResetResponseDecoder,
        Commands.log_values: LogValuesResponseDecoder,
        Commands.next_free_slot_root: NextFreeSlotRootResponseDecoder,
        Commands.list_profiles: ListProfilesResponseDecoder,
        Commands.read_system_value: ReadSystemValueResponseDecoder,
        Commands.write_system_value: WriteSystemValueResponseDecoder,
        Commands.write_masked_value: WriteMaskedValueResponseDecoder,
        Commands.write_system_masked_value: WriteSystemMaskedValueResponseDecoder,
        Commands.async_log_values: AsyncLogValueDecoder
    }

    def __init__(self, conduit: Conduit,
                 next_chunk_input=nop, next_chunk_output=nop):
        """Construct a new protocol over the given conduit.

        The conduit is assumed to read/write binary data. This class doesn't concern itself with the
        low-level encoding, such as hex-coded bytes.
        """
        super().__init__(conduit)
        self.input = conduit.input
        self.output = conduit.output
        self.next_chunk_input = next_chunk_input
        self.next_chunk_output = next_chunk_output
        self.add_unmatched_response_handler(self.handle_async_response)
        self.async_log_handlers = EventSource()

    @staticmethod
    def command_id_from_response(response: Response):
        """Retrieve the command ID from the resposne key is the original request data."""
        return response.response_key[0]

    def handle_async_response(self, response: Response):
        """notify that a response has been received.

        Invoked when an unsolicited response is received.
        """
        cmd_id = self.command_id_from_response(response)
        if cmd_id == Commands.async_log_values:
            self.async_log_handlers.fire(response)

    def read_value(self, id_chain, object_type=0, expected_len=0) -> FutureResponse:
        """request the value of the given object id is read. """
        return self._send_command(Commands.read_value, encode_id(id_chain), object_type, expected_len)

    def write_value(self, id_chain, object_type, buf) -> FutureResponse:
        return self._send_command(Commands.write_value, encode_id(id_chain), object_type, len(buf), buf)

    def write_masked_value(self, id_chain, object_type, buf, mask) -> FutureResponse:
        return self._cmd_write_masked_value(Commands.write_masked_value, id_chain, object_type, buf, mask)

    def create_object(self, id_chain, object_type, data) -> FutureResponse:
        return self._send_command(Commands.create_object, encode_id(id_chain), object_type, len(data), data)

    def delete_object(self, id_chain, object_type=0) -> FutureResponse:
        return self._send_command(Commands.delete_object, encode_id(id_chain), object_type)

    def list_profile(self, profile_id) -> FutureResponse:
        return self._send_command(Commands.list_profile, profile_id)

    def next_slot(self, id_chain) -> FutureResponse:
        return self._send_command(Commands.next_free_slot if len(id_chain) else Commands.next_free_slot_root,
                                  encode_id(id_chain))

    def reset(self, flags) -> FutureResponse:
        return self._send_command(Commands.reset, flags)

    def create_profile(self) -> FutureResponse:
        return self._send_command(Commands.create_profile)

    def delete_profile(self, profile_id) -> FutureResponse:
        return self._send_command(Commands.delete_profile, profile_id)

    def activate_profile(self, profile_id) -> FutureResponse:
        return self._send_command(Commands.activate_profile, profile_id)

    def list_profiles(self) -> FutureResponse:
        return self._send_command(Commands.list_profiles)

    def read_system_value(self, id_chain, object_type=0, expected_len=0):
        return self._send_command(Commands.read_system_value, encode_id(id_chain), encode_type_id(object_type),
                                  expected_len)

    def write_system_value(self, id_chain, object_type, buf) -> FutureResponse:
        return self._send_command(Commands.write_system_value, encode_id(id_chain), encode_type_id(object_type),
                                  len(buf), buf)

    def write_system_masked_value(self, id_chain, object_type, buf, mask) -> FutureResponse:
        return self._cmd_write_masked_value(Commands.write_system_masked_value, id_chain, object_type, buf, mask)

    def _cmd_write_masked_value(self, cmd, id_chain, object_type, buf, mask):
        if len(buf) != len(mask):
            raise ValueError("mask and data buffer must be same length")
        return self._send_command(cmd, encode_id(id_chain), encode_type_id(object_type), len(buf),
                                  interleave(buf, mask))

    @staticmethod
    def build_bytearray(*args):
        """construct a byte array from position arguments.

        >>> ControlboxProtocolV1.build_bytearray(90, b"\x42\x43", 95)
        bytearray(b'ZBC_')
        """
        b = bytearray()
        for arg in args:
            try:
                for val in arg:
                    b.append(unsigned_byte(val))
            except TypeError:
                b.append(unsigned_byte(arg))
        return b

    def _send_command(self, *args):
        """Send a command.

        The command is made up of all the arguments.
        Either an argument is a simple object_type, which is
        converted to a byte or it is a list object_type whose elements are converted to bytes.
        The command is sent synchronously and the result is returned. The command may timeout.
        """
        cmd_bytes = bytes(self.build_bytearray(*args))
        request = ByteArrayRequest(cmd_bytes)
        return self.async_request(request)

    def _stream_request_sent(self, request):
        """notifies that a request has been sent. move the output onto the next chunk."""
        self.next_chunk_output()

    def _decode_response(self) -> Response:
        """Read the next response from the conduit. Blocks until data is available.

        The command response is decoded using the ResponseDecoder class for the specific command.
        The decoded value is set as the value in the Response object.
        """
        self.next_chunk_input()  # move onto next chunk after newline
        stream = self.input
        next_byte = stream.read(1)
        if next_byte:
            cmd_id = next_byte[0]
            try:
                if cmd_id:  # peek command id
                    decoder = self._create_response_decoder(cmd_id)
                    command_block, parsed_command = decoder.parse_request(cmd_id, stream)
                    parsed_response = decoder.parse_response(stream)
                    if parsed_response is None:
                        raise ValueError("request decoder did not return a value")
                    return CommandResponse(command_block, parsed_response, parsed_command)
            finally:
                while not stream.closed and stream.read():  # spool off rest of block if caller didn't read it
                    pass

    @staticmethod
    def _create_response_decoder(cmd_id):
        decoder_type = ControlboxProtocolV1.decoders.get(cmd_id)
        if not decoder_type:
            raise ValueError("no decoder for cmd_id %d" % cmd_id)
        return decoder_type()

    def __str__(self):
        return "v0.3.0"
