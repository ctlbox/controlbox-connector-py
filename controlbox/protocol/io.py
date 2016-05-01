"""
some useful stream classes.
"""

import io
from collections import deque
from io import BufferedReader, BufferedWriter

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

    def readable(self):
        return True

    def read(self, count=-1):
        self._checkClosed()
        if not count or not self.q:
            return bytes()
        return bytes([self.q.popleft()])


class DequeWriter(DequeStream):

    def writable(self):
        return True

    def write(self, buf):
        self._checkClosed()
        for x in buf:
            self.q.append(x)
        return len(buf)


class RWCacheBuffer():
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
