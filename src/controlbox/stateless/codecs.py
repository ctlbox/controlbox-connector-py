from abc import abstractmethod

from controlbox.protocol.controlbox import longDecode, signed_byte, unsigned_byte
from controlbox.support.mixins import CommonEqualityMixin, StringerMixin


def is_mask_complete(mask):
    """
    >>> is_mask_complete(bytes([0xFF, 0xFF]))
    True

    >>> is_mask_complete(bytes([0xFF, 0]))
    False

    >>> is_mask_complete(bytes())
    True

    """
    for b in mask:
        if b != 0xFF:
            return False
    return True


class Decoder:
    @abstractmethod
    def decode(self, data, mask=None):
        """
        decodes an object state representation.
        realm: either constructor or state
        :param type: the type ID of the data to decode
        :param data: a buffer of binary data to decode
        :param mask: a mask of binary data used to describe which perts are not included in the data
        :returns a value representing the decoded data
        """
        raise NotImplementedError


class Encoder:
    @abstractmethod
    def encode(self, value):
        """Encode a given value as a data buffer and a mask.
        returns (data, mask) for the encoded value
         """
        raise NotImplementedError


class ValueDecoder(Decoder):
    """Decodes a single value. The value will be None if the mask is given and is not 0xFF for all
        bytes corresponding to the length of the encoded data."""
    @abstractmethod
    def encoded_len(self)->int:
        """Determine the number of bytes in the encoded data for this value"""

    @abstractmethod
    def _decode(self, data)->object:
        """decode the data buffer into a value"""

    def decode(self, data, mask=None):
        return self._decode(data) if not mask or is_mask_complete(mask) else None


class ValueEncoder(Encoder):
    """Encodes a single value. The value has a mask of 0xFF if the value is not None, otherwise the mask is [0]*"""
    @abstractmethod
    def encoded_len(self)->int:
        """Determine the number of bytes in the encoded data for this value"""

    @abstractmethod
    def _encode(self, value)->bytes:
        """encode the value to a data buffer"""

    def encode(self, value):
        if value is None:
            empty = bytes(self.encoded_len())
            return empty, empty
        else:
            data = self._encode(value)
            mask = bytes([0xFF] * len(data))
            return data, mask


class Codec(Decoder, Encoder):
    """
    Knows how to convert object state to/from the on-wire data format.
    """


class CompositeCodec(Codec):
    """
    Creates a codec from separate encoder/decoder instances.
    This allows runtime composition.
    """
    def __init__(self, encoder: Encoder, decoder: Decoder):
        self.encoder = encoder
        self.decoder = decoder

    def encoded_len(self):
        return self.encoder.encoded_len()

    def decode(self, buf):
        return self.decoder.decode(buf)

    def encode(self, value):
        raise self.encoder.encode(value)


class IdentityCodec(Codec):
    """
    An identity codec - the input is returned as the result regardless of type
    """

    def encode(self, value):
        return value

    def decode(self, data, mask=None):
        return data


class TypeMappingCodec:
    def __init__(self, codecs: callable):
        self.codecs = codecs

    def encode(self, type, value):
        delegate = self.fetch(type)
        return delegate.encode(value)

    def decode(self, type, data, mask=None):
        delegate = self.fetch(type)
        return delegate.decode(data, mask)

    def fetch(self, type):
        delegate = self.codecs(type)
        if not delegate:
            raise KeyError()
        return delegate


class DictionaryMappingCodec(TypeMappingCodec):
    def __init__(self, codecs: dict):
        super().__init__(self.lookup)
        self.codecs_dict = codecs

    def lookup(self, type):
        return self.codecs_dict.get(type)


class BaseState(CommonEqualityMixin, StringerMixin):
    """
    A value type that supports equality checking and to string conversion.
    """
    pass


class ByteDecoder(ValueDecoder):

    def _decode(self, buf):
        return signed_byte(buf[0])

    def encoded_len(self, value=None):
        return 1


class UnsignedByteDecoder(ValueDecoder):

    def _decode(self, buf):
        return buf[0]

    def encoded_len(self, value=None):
        return 1


class ByteEncoder(ValueEncoder):

    def _encode(self, value):
        buf = bytearray(1)
        buf[0] = unsigned_byte(value)
        return buf

    def encoded_len(self):
        return 1


class UnsignedByteEncoder(ByteEncoder):
    pass


class ByteCodec(Codec, ByteDecoder, ByteEncoder):
    pass


class UnsignedByteCodec(Codec, UnsignedByteDecoder, UnsignedByteEncoder):
    pass


class ShortDecoder(ValueDecoder):
    def _decode(self, buf):
        return (signed_byte(buf[1]) * 256) + buf[0]

    def encoded_len(self, value=None):
        return 2


class UnsignedShortDecoder(ValueDecoder):
    def _decode(self, buf):
        return ((buf[1]) * 256) + buf[0]

    def encoded_len(self):
        return 2


class ShortEncoder(ValueEncoder):
    """Encodes signed or unsigned short values to 2 bytes."""
    def _encode(self, value):
        buf = bytearray(2)
        if value < 0:
            value += 64 * 1024
        buf[1] = unsigned_byte(int(value / 256))
        buf[0] = value % 256
        return buf

    def encoded_len(self):
        return 2


class UnsignedShortEncoder(ShortEncoder):
    pass


class ShortCodec(Codec, ShortEncoder, ShortDecoder):
    """encodes a 16-bit signed value"""


class UnsignedShortCodec(Codec, UnsignedShortDecoder, UnsignedShortEncoder):
    """encodes a 16-bit unsigned value"""


class LongEncoder(ValueEncoder):

    def _encode(self, value):
        if value < 0:
            value += 1 << 32
        value = int(value)
        buf = bytearray(4)
        for x in range(0, 4):
            buf[x] = value % 256
            value = int(value / 256)
        return buf

    def encoded_len(self):
        return 4


class UnsignedLongEncoder(LongEncoder):
    pass


class LongDecoder(ValueDecoder):

    def _decode(self, buf):
        return longDecode(buf)

    def encoded_len(self):
        return 4


class UnsignedLongDecoder(ValueDecoder):

    def _decode(self, buf):
        return ((((buf[3] * 256) + buf[2]) * 256) + buf[1]) * 256 + buf[0]

    def encoded_len(self):
        return 2


class LongCodec(Codec, LongEncoder, LongDecoder):
    pass


class UnsignedLongCodec(Codec, UnsignedLongEncoder, UnsignedLongDecoder):
    pass


class EmptyCodec(Codec):

    msg = "unepxected data"

    def decode(self, data, mask=None):
        raise ValueError(self.msg)

    def encode(self, value):
        if value is not None:
            raise ValueError(self.msg)


class AnyBlockCodec(Codec):

    def decode(self, data, mask=None):
        return data

    def encode(self, value):
        return value if value is not None else b''


class BufferDecoder(Decoder):

    def decode(self, buf, mask=None):
        return buf


class BufferEncoder(Encoder):

    def encode(self, value):
        return bytes(value)
