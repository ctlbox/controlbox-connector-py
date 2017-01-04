"""
Provides an implementation of the control box protocol via the class ControllerProtocolV030.
"""

from abc import abstractmethod, ABCMeta
from io import IOBase, BytesIO, BufferedIOBase

from controlbox.conduit.base import Conduit, ConduitStreamDecorator
from controlbox.protocol.async import BaseAsyncProtocolHandler, FutureResponse, Request, Response, ResponseSupport
from controlbox.support.events import EventSource


def unsigned_byte(val):
    """ converts an unsigned byte to a corresponding 2's complement signed value
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
    """ converts an unsigned byte to a corresponding 2's complement signed value
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
    """
    Encodes a sequence of integers to the on-wire binary values (before hex encoding.)

    >>> list(encode_id([1]))
    [1]

    >>> list(encode_id([1,2,3]))
    [129, 130, 3]

    >>> encode_id([])
    bytearray(b'')

    :return:converts a byte array representing an id chain to the comms format.
    :rtype:
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
    """
    :param buf: The id_chain as the on-wire format.
    :return: A list of integers corresponding to the id chain

    >>> decode_id(bytearray([0x81, 0x82, 3]))
    [1, 2, 3]
    """
    return [(x & 0x7F) for x in buf]


class ByteArrayRequest(Request):
    """ represents a request as an array or bytes. The byte array defines the key for the reuqest, since responses
        always repeat the request data verbatim. """

    def __init__(self, data):
        self.data = data

    def to_stream(self, file):
        file.write(self.data)

    @property
    def response_keys(self):
        """ the commands requests and responses are structured such that the entire command request is the unique key
            for the command """
        return [self.data]


def h2b(h):
    """
    :param h: The hex digit to convert to binary, as an int
    :return: A binary value from 0-15

    >>> h2b('0')
    0
    >>> h2b('9')
    9
    >>> h2b('A')
    10
    >>> h2b('f')
    15
    >>> h2b('F')
    15

    """
    b = ord(h)
    if h > '9':
        b -= 7  # // 'A' is 0x41, 'a' is 0x61. -7 =  0x3A, 0x5A
    return b & 0xF


def b2h(b):
    """ Converts a binary nibble (0-15) to a hex digit
    :param b: the binary value to convert to a hex digit
    :return: the corresponding hex digit
    >>> b2h(0)
    '0'
    >>> b2h(9)
    '9'
    >>> b2h(10)
    'A'
    >>> b2h(15)
    'F'
    """
    return chr(b + (ord('0') if b <= 9 else ord('A') - 10))


class HexToBinaryInputStream(IOBase):
    """ converts from hex-encoded bytes (ascii) to byte values.
        The stream automatically closes when a newline is detected, and ensures that the underlying stream
        is not read past the newline. This allows the code constructing the stream to limit clients reading
        from the stream to one logical command.
    """

    def __init__(self, stream, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.char1 = 0
        self.char2 = 0
        self.stream = stream

    def close(self):
        pass

    def has_next(self):
        self._fetch_next_byte()
        return self.char1 != 0

    def _consume_byte(self):
        self.char1 = 0

    def read_next_byte(self):
        if not self.has_next():
            raise StopIteration()
        result = self._decode_next_byte()
        self._consume_byte()
        return result

    def peek_next_byte(self):
        if not self.has_next():
            return -1
        return self._decode_next_byte()

    # noinspection PyUnusedLocal
    def peek(self, *args, **kwargs):
        return bytes([self._decode_next_byte()]) if self.has_next() else bytes()

    # noinspection PyUnusedLocal
    def read(self, *args, **kwargs):
        result = self.peek(1)
        self._consume_byte()
        return result

    def _fetch_next_byte(self):
        if self.char1 != 0:  # already have a character
            return

        b1 = self.stream.read(1)
        b2 = self.stream.read(1)
        if b1 and b2:
            self.char1 = chr(b1[0])
            self.char2 = chr(b2[0])

    def detach(self):
        result = self.stream
        self.stream = None
        return result

    def readable(self, *args, **kwargs):
        return True

    def _decode_next_byte(self):
        return (h2b(self.char1) * 16) | h2b(self.char2)


class BinaryToHexOutputStream(IOBase):
    """ A binary stream that writes data as two hex-encoded digits."""

    def __init__(self, stream):
        super().__init__()
        if not stream.writable():
            raise ValueError()
        self.stream = stream

    def write_annotation(self, annotation):
        self._write_byte(ord('['))
        self.stream.write(annotation)
        self._write_byte(ord(']'))

    def write_byte(self, b):
        self._write_byte(ord(b2h(b >> 4)))
        self._write_byte(ord(b2h(b & 0xF)))
        self._write_byte(ord(' '))

    def write(self, buf):
        for b in buf:
            self.write_byte(b)

    def _write_byte(self, b):
        """write a byte directly to the stream"""
        buf = bytearray(1)
        buf[0] = b
        self.stream.write(buf)

    def newline(self):
        self._write_byte(ord('\n'))
        self.stream.flush()

    def writable(self, *args, **kwargs):
        return True


def is_hex_digit(val):
    return ord('0') <= val <= ord('9') or ord('A') <= val <= ord('F') or ord('a') <= val <= ord('f')


class ChunkedHexTextInputStream(IOBase):
    """ Reads a binary stream that encodes ascii text. non-hex characters are discarded, newlines terminate
        a block - the caller should call reset() to move to the next block. Commants enclosed in [] are ignored. """
    no_data = bytes()

    def __init__(self, stream, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = None
        self.stream = stream
        self.comment_level = 0
        self.next_chunk()

    def read(self, count=-1):
        if not count:
            return ChunkedHexTextInputStream.no_data
        self._fetch_next()
        result = self.data
        self.data = ChunkedHexTextInputStream.no_data
        return result

    def peek(self, count=0):
        if not count:
            return ChunkedHexTextInputStream.no_data
        self._fetch_next()
        return self.data

    def _fetch_next(self):
        while not self.data and self.comment_level >= 0 and self._stream_has_data():
            d = self.stream.read(1)
            if not d:
                break
            if d == b'[':
                self.comment_level += 1
            elif d == b']':
                self.comment_level -= 1
            elif d == b'\n':
                self.comment_level = -1
            elif not self.comment_level and is_hex_digit(d[0]):
                self.data = d

    def _stream_has_data(self):
        if hasattr(self.stream, 'peek'):
            return self.stream.peek(1)
        return True

    def detach(self):
        result = self.stream
        self.stream = None
        return result

    def readable(self, *args, **kwargs):
        return True

    def next_chunk(self):
        """ advances after a newline so that callers can read subsequent data. """
        self.data = ChunkedHexTextInputStream.no_data
        self.comment_level = 0


class CaptureBufferedReader:
    """
    Captures the data read from a stream into a buffer.
    This allows streaming, parsing and looking for a delimiter
    and capturing the data read.

    The captured data is available via as_bytes()
    """
    def __init__(self, stream):
        self.buffer = BytesIO()
        self.stream = stream

    def push(self, data):
        self.buffer.write(data)

    def read(self, count=-1):
        b = self.stream.read(count)
        self.buffer.write(b)
        return b

    def peek(self, count=0):
        return self.stream.peek(count)

    def peek_next_byte(self):
        next = self.stream.peek()
        return next[0] if next else -1

    def as_bytes(self):
        return bytes(self.buffer.getbuffer())

    def close(self):
        pass


class Commands:
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


# A note to maintainers: These ResponseDecoder objects have to be written carefully - the
# _parse and _parse_response methods have to match exactly the command request and command response
# If _parse doesn't consume the right amount of bytes, the response will not be matched up with the
# corresponding request, and the caller will never get a response (and will eventually timeout on the
# FutureRequest.)


class ResponseDecoder(metaclass=ABCMeta):
    """  parses the response data into the data block corresponding to the original request
         and decodes the data block that is the additional response data.
    """

    def parse_request(self, cmd_id: int, stream: BufferedIOBase):
        """ read the portion of the response that corresponds to the original request.
            Delegates the main parsing of the command portion of the response to the
            _parse() method. The command isn't parsed into anything - only that we determine
            how much of the input buffer corresponds to the original command request.
        """
        buf = CaptureBufferedReader(stream)
        buf.push(bytes([cmd_id]))
        structure = self._parse_request(buf)
        return buf.as_bytes(), structure  # return the bytes read from the stream so far.

    @abstractmethod
    def _parse_request(self, buf):
        """
        parse the buffer so that the content is validated, streamd and the semantic parts
        decoded/separated.
        """
        raise NotImplementedError

    def _read_chain(self, buf):
        result = bytearray()
        while self.has_data(buf):
            b = self._read_byte(buf)
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
        """ decodes variable length data from the stream. The first byte is the number of bytes in the data block,
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
        """ reads the next byte from the stream. If there is no more data, an exception is thrown.
            bytes are returned as unsigned. """
        b = stream.read(1)
        if not b:
            raise ValueError("no more data in stream.")
        return b[0]

    def _read_status_code(self, stream):
        """ parses and returns a status-code """
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
        """ reads the remaining bytes in the stream into a list """
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
        """ template method to decode the command response. The value returned
            is the decoded response. """
        raise NotImplementedError()


class ReadValueResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        # read the id of the object to read
        id_chain = self._read_id_chain(buf)
        object_type = self._read_type_chain(buf)
        data_length = self._read_byte(buf)  # length of data expected
        return id_chain, object_type, data_length

    def _parse_response(self, stream):
        """ The read command response is a single variable length buffer. """
        return self._read_vardata(stream),


class WriteValueResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        id_chain = self._read_id_chain(buf)  # id chain
        object_type = self._read_type_chain(buf)  # object object_type
        to_write = self._read_vardata(buf)  # length and body of data to write
        return id_chain, object_type, to_write

    def _parse_response(self, stream):
        """ The write command response is a single variable length buffer indicating the value written. """
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
        """ The create object command response is a status code. """
        return self._read_status_code(stream),


class DeleteObjectResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        id_chain = self._read_id_chain(buf),  # the location of the object to delete
        object_type = self._read_type_chain(buf)
        return id_chain, object_type

    def _parse_response(self, stream):
        """ The delete object command response is a status code. """
        return self._read_status_code(stream),


class ListProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_signed_byte(buf),  # profile id

    def _parse_response(self, stream):
        """ retrieves a tuple, first value is list of tuples (id, object_type, data) """
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
        """ The next free slot command response is a byte indicating the next free slot. """
        return self._read_status_code(stream),


class NextFreeSlotRootResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):  # additional command arguments to read
        return tuple()

    def _parse_response(self, stream):
        """ The next free slot command response is a byte indicating the next free slot. """
        return self._read_status_code(stream),


class CreateProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return tuple()

    def _parse_response(self, stream):
        """ Returns the new profile id or negative on error. """
        return self._read_status_code(stream),


class DeleteProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_byte(buf),  # profile_id

    def _parse_response(self, stream):
        """ Result is a status code. """
        return self._read_status_code(stream),


class ActivateProfileResponseDecoder(ResponseDecoder):
    def _parse_request(self, buf):
        return self._read_byte(buf),  # profile id

    def _parse_response(self, stream):
        """ Returns the active profile id or negative on error. """
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
        """ Returns a status code. """
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
    """ Writing system values has the same format as writing user values. """


class WriteSystemValueResponseDecoder(WriteValueResponseDecoder):
    """ Writing system values has the same format as writing user values. """


class ListSystemValuesResponseDecoder(ListProfileResponseDecoder):
    """ Listing system values and listing user values (a profile) have the same format. """


class AsyncLogValueDecoder(LogValuesResponseDecoder):
    """ Decodes the asynchronous logged values. This is similar to a regular logged value, although the
        flags and id_chain of the logged container are considered part of the response, rather than the request.
        The decided value for the response is a tuple (time, id_chain, values). The values is a list of tuples
         (id_chain, value) for each value logged in the hierarchy. """

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
    """ Builds a binary conduit that converts the binary data to ascii-hex digits.
        Input/Output are chunked via newlines. """
    chunked = ChunkedHexEncodedConduit(conduit)
    return chunked, chunked.next_chunk_input, chunked.next_chunk_output


def nop():
    pass


def interleave(*args):
    """ Interleaves two or more buffers.
    >>> interleave(b'ABC', b'DEF')
    b'ADBECF'
    """
    return bytes([x for z in zip(*args) for x in z])


def separate(buffer, count):
    """ de-interleaves buffers
    >>> separate(b'ADBECF')
    (b'ABC', b'DEF')
    """
    return zip(*[buffer[i::count] for i in range(count)])


class ControlboxProtocolV1AsyncResponseHandler:
    # todo - on review, this seems a bit round the houses - any reason why a simple instance method
    # couldn't do the job?
    def __init__(self, controller):
        self.controller = controller

    def __call__(self, *args, **kwargs):
        for x in args:
            self.controller.handle_async_response(x)


class CommandResponse(ResponseSupport):
    """
    Describes a response to a controlbox command.
    :param: request_key used to pair this response with the original request
    :param: parsed_response The parsed response data. The format depends upon the command.
        See _parse_request() of the corresponding command :class:`ResponseDecoder` subclass.
    :param:parsed_request
        See _parse_response() of the corresponding command ResponseDecoder subclass.
    """

    def __init__(self, request_key, parsed_response, parsed_request):
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
    """ Implements the controlbox hex-encoded binary protocol.
    """

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
        """ The conduit is assumed to read/write binary data. This class doesn't concern itself with the
            low-level encoding, such as hex-coded bytes. """
        super().__init__(conduit)
        self.input = conduit.input
        self.output = conduit.output
        self.next_chunk_input = next_chunk_input
        self.next_chunk_output = next_chunk_output
        self.add_unmatched_response_handler(ControlboxProtocolV1AsyncResponseHandler(self))
        self.async_log_handlers = EventSource()

    @staticmethod
    def command_id_from_response(response: Response):
        """ The resposne key is the original request data. The first byte is the command id. """
        return response.response_key[0]

    def handle_async_response(self, response: Response):
        """
        invoked when an unsolicited response is received.
        """
        cmd_id = self.command_id_from_response(response)
        if cmd_id == Commands.async_log_values:
            self.async_log_handlers.fire(response)

    def read_value(self, id_chain, object_type=0, expected_len=0) -> FutureResponse:
        """ requests the value of the given object id is read. """
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
        """
        constructs a byte array from position arguments.
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
        """
        Sends a command. the command is made up of all the arguments.
        Either an argument is a simple object_type, which is
        converted to a byte or it is a list object_type whose elements are converted to bytes.
        The command is sent synchronously and the result is returned. The command may timeout.
        """
        cmd_bytes = bytes(self.build_bytearray(*args))
        request = ByteArrayRequest(cmd_bytes)
        return self.async_request(request)

    def _stream_request_sent(self, request):
        """ notification that a request has been sent. move the output onto the next chunk. """
        self.next_chunk_output()

    def _decode_response(self) -> Response:
        """ reads the next response from the conduit. Blocks until data is available.
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
