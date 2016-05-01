from abc import abstractmethod
from io import IOBase

from controlbox.support.proxy import make_exception_notify_proxy


class Conduit:
    """
    A conduit allows two-way communication. It provides an file-like input endpoint and a file-like output endpoint.
    """

    @property
    @abstractmethod
    def target(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def input(self) -> IOBase:
        """ fetches the I/O stream that provides input.
            Callers can use the usual readXXX() methods. """
        raise NotImplementedError

    @property
    @abstractmethod
    def output(self) -> IOBase:
        """ fetches the I/O stream that provides output.
            Callers can use the usual writeXXX() methods. """
        raise NotImplementedError

    @property
    @abstractmethod
    def open(self) -> bool:
        """ determines if this conduit is open. When open, the streams provided by
            input and output can be read from/written to."""
        raise NotImplementedError

    @abstractmethod
    def close(self):
        """
        Closes both the input and output streams.
        """
        raise NotImplementedError


class ConduitDecorator(Conduit):
    """
    A ConduitDecorator wraps another conduit and delegates to it's methods.
    This allows subclasses to easily override some behaviors while keeping others
    unchanged.
    """

    def __init__(self, decorate: Conduit):
        self.decorate = decorate

    @property
    def target(self):
        return self.decorate.target

    def close(self):
        self.decorate.close()

    @property
    def input(self) -> IOBase:
        return self.decorate.input

    @property
    def output(self) -> IOBase:
        return self.decorate.output

    @property
    def open(self) -> bool:
        return self.decorate.open


class ConduitStreamDecorator(ConduitDecorator):
    """ provides a simple way to wrap the input and output streams from a conduit.
        Subclasses override the _wrap_input and _wrap_output methods.
    """

    def __init__(self, decorate: Conduit):
        super().__init__(decorate)
        self._input = None
        self._output = None

    @property
    def input(self) -> IOBase:
        if self._input is None:
            self._input = self._wrap_input(self.decorate.input)
        return self._input

    @property
    def output(self) -> IOBase:
        if self._output is None:
            self._output = self._wrap_output(self.decorate.output)
        return self._output

    def close(self):
        out = self._output
        if out is not None:
            self._output.close()
        super().close()

    @abstractmethod
    def _wrap_input(self, input):
        return input

    @abstractmethod
    def _wrap_output(self, output):
        return output


# class BufferedConduit(ConduitStreamDecorator):
#     """ buffers the underlying streams from the given conduit."""
#
#     def _wrap_output(self, output):
#         return io.BufferedWriter(output)
#
#     def _wrap_input(self, input):
#         return io.BufferedReader(input)


class DefaultConduit(Conduit):
    """ provides the conduit streams from specific read/write file-like types (which may be the same value) """

    def __init__(self, read=None, write=None):
        self._read = self._write = None
        self.set_streams(read, write)

    def set_streams(self, read, write=None):
        self._read = read
        self._write = write if write is not None else read

    def close(self):
        self._write.close()
        self._read.close()

    @property
    def open(self):
        """ toto - check underlying streams, or catch calls to close(). """
        return True

    @property
    def input(self) -> IOBase:
        return self._read

    @property
    def output(self) -> IOBase:
        return self._write


# class RedirectConduit(ConduitStreamDecorator):
#     """ wraps the original streams with streams that write their data to another chosen stream.
#         This can be used for example to write the input and output streams to stdout and stderr respectively
#         """
#     def __init__(self, decorate, redirectStream):
#         """
#         :param decorate The conduit to decorate
#         :param redirectStream The file-like stream to write
#         """
#         super().__init__(decorate)
#         self.redirect = redirectStream
#
#     def _wrap_output(self, output):
#         out = output.write
#         redirect = self.redirect    # the stream to write to
#
#         def pipe_output(data):
#             data = bytes(data)
#             out(data)
#             redirect.write(data.decode())
#         output.write = pipe_output
#         return output
#
#     def _wrap_input(self, input):
#         read = input.read
#         redirect = self.redirect
#
#         def pipe_input():
#             result = read()
#             redirect.write(bytes(result).decode())
#             return result
#         input.read = pipe_input
#         return input


class ConduitFactory:
    """
    A factory knows how to create a conduit given appropriate construction arguments.
    """
    @abstractmethod
    def __call__(self, *args, **kwargs):
        """
        Constructs the conduit from the given construction arguments.
        Note that no tests are done that the resource is available or not.
        """
        raise NotImplementedError()


class StreamErrorReportingConduit(ConduitStreamDecorator):
    """
    Reports exceptions that occur when reading or writing to the stream
    """
    def __init__(self, decorate: Conduit, handler):
        """
        :param handler a callable that is invoked each time an exception occurs.
        """
        super().__init__(decorate)
        self.handler = handler

    def _wrap_input(self, input):
        return make_exception_notify_proxy(input, self.handler)

    def _wrap_output(self, output):
        return make_exception_notify_proxy(output, self.handler)
