"""
a library of classes for potential reuse in different controlbox applications.
"""

from controlbox.controller import ReadWriteSystemObject, mask, LongDecoder, ShortDecoder, ShortEncoder, LongEncoder


class ElapsedTime(ReadWriteSystemObject):
    """
    A class that represents an elapsed time period, optionally scaled by a given value.
    As a controller object proxy, the object state is not stored here.
    """

    def encoded_len(self):
        return 6

    def set(self, time=None, scale=None):
        """ Sets the time and/or scale. If either value is None the existing value is used.
            Returns a tuple of (time,scale) for the current time and scale. (Same as read() method.)
        """
        return self.controller.write_masked_value(self, (time, scale))

    def _encode_mask(self, value, buf_value, buf_mask):
        time, scale = value
        buf_value = self._encode(value, buf_value)
        mask_value = (mask(value[0], 4), mask(value[1], 2))
        buf_mask = self._encode(mask_value, buf_mask)
        return buf_value, buf_mask

    def _decode(self, buf):
        time = LongDecoder()._decode(buf[0:4])
        scale = ShortDecoder()._decode(buf[4:6])
        return time, scale

    def _encode(self, value, buf):
        time, scale = value
        if time is not None:
            buf[0:4] = LongEncoder().encode(time)
        if scale is not None:
            buf[4:6] = ShortEncoder().encode(scale)
        return buf
