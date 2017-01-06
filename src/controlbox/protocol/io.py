"""
some useful stream classes.
"""

import io
from collections import deque
from io import BufferedReader, BufferedWriter, BytesIO

from controlbox.conduit.base import Conduit
from controlbox.protocol.async import UnknownProtocolError


class DequeStream(io.BufferedIOBase):

    def __init__(self, q: deque):
        super().__init__()
        self.q = q

    def close(self):
        self.q = None
        super().close()


class DequeReader(DequeStream):
    """
    A Readable stream that pulls content from a deque.
    """

    def readable(self):
        return True

    def read(self, count=-1):
        self._checkClosed()
        if not count or not self.q:
            return bytes()
        return bytes([self.q.popleft()])


class DequeWriter(DequeStream):
    """
    A writable stream that pushes content to a deque.
    """
    def writable(self):
        return True

    def write(self, buf):
        self._checkClosed()
        for x in buf:
            self.q.append(x)
        return len(buf)


class RWCacheBuffer:
    """ simple implementation of a read and writable buffer. For single-threaded code in test.
        Use the reader and writer attributes to access a reader and writer - the reader reads what has been put
        by the writer.
    """

    def __init__(self):
        self.q = deque()
        self.reader = BufferedReader(DequeReader(self.q))
        self.writer = BufferedWriter(DequeWriter(self.q))

    def close(self):
        self.reader.close()
        self.writer.close()


def determine_line_protocol(conduit: Conduit, all_sniffers):
    """
    Determines a protocol from the first line read.
    """
    # at present all protocols are line based
    l = conduit.input.readline()
    line = l.decode('utf-8')
    error = None
    for sniffer in all_sniffers:
        try:
            p = sniffer(line, conduit)
            if p:
                return p
        except ValueError as e:
            error = e

    # todo - should we suppress the exception and return None?
    # an unknown device is expected in the application
    raise UnknownProtocolError("unable to determine version from '%s'" % l) from error


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
