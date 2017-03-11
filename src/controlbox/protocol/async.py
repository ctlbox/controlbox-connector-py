"""
Provides building blocks for implementing asynchronous protocols. They are represented abstractly as two message queues.
"""
import logging
import threading
import time
from abc import abstractmethod
from collections import Callable, defaultdict
from concurrent.futures import Future
from io import IOBase

from controlbox.conduit.base import Conduit
from controlbox.support.events import EventSource

logger = logging.getLogger(__name__)


class UnknownProtocolError(IOError):
    """
    Error raised by a protocol sniffer when it doesn't recognize the stream protocol.
    """


def tobytes(arg):
    """
    Converts a string to bytes
    >>> tobytes("abc")
    b'abc'
    >>> tobytes(b"abc")
    b'abc'
    """
    if isinstance(arg, type("")):
        # noinspection PyArgumentList
        arg = bytes(arg, encoding='ascii')
    return arg


class FutureValue(Future):
    """ describes a value that may have not yet been computed. Callers can check if the value has arrived, or chose to
        wait until the value has arrived.
        If an exception is encountered computing the value, it is set."""

    def __init__(self):
        super().__init__()

    def _value_extractor(self, value):
        """
        The value extractor allows processing of the result to arrive at the
        value returned in `value`.
        :param value:
        :return:
        """
        return value

    def set_result_or_exception(self, value):
        """sets the result,"""
        if isinstance(value, BaseException):
            self.set_exception(value)
        else:
            self.set_result(value)

    def value(self, timeout=None):
        """ allows the provider to set the result value but provide a different (derived) value to callers. """
        # todo - the base future class handles exceptions as results, so this can be factored out
        value = self._value_extractor(self.result(timeout))
        if isinstance(value, BaseException):
            raise value
        return value


class Request:
    """ Encapsulates the request data.  A request is a message sent from the client to the server. """

    @abstractmethod
    def to_stream(self, file: IOBase):
        """ Encodes the request as bytes in a stream.
        :param file: the file-like instance to stream this request to.
        """
        raise NotImplementedError()

    @property
    def response_keys(self) -> list:
        """ retrieves an iterable over keys that are used to correlate requests with corresponding responses. """
        raise NotImplementedError()
        # todo - maybe just use simple iteration looking for a matching response?


class Response:
    """Represents a response, which can be decoded from a stream and has a value.

    A response is a message sent from the server to the client.
    Some responses may be unsolicited - have no originating request from a known client.
    """
    @abstractmethod
    def from_stream(self, file):
        """
        :return: returns the response decoded from the stream. This may be a distinct instance in cases
            where this response is being used as a factory.
        :rtype:Response
        """
        raise NotImplementedError()

    @property
    def response_key(self):
        """
        :return: a key that can be used to pair this response with a previously sent request.
        Will be None if this response is unsolicited.
        """
        raise NotImplementedError()

    @property
    def value(self):
        """
        The decoded representation of the response value.
        :return:
        """
        raise NotImplementedError()

    @value.setter
    def value(self, value):
        raise NotImplementedError()


class FutureResponse(FutureValue):
    """ Relates a request and it's future response."""

    def __init__(self, request: Request):
        """
        :param request: The request this response is for.
        """
        super().__init__()
        self._request = request

    def _value_extractor(self, r):
        return r.value

    @property
    def request(self):
        return self._request

    @property
    def response(self, timeout=None) -> Response:
        """ blocking fetch of the response. Note that this retrieves
            the entire response instance, and not just the response value. """
        return self.result(timeout)

    @response.setter
    def response(self, result: Response):
        """
        Sets the successful completion of this future result.
        :param value: The response associated with this future's request.
        """
        self.set_result(result)


class ResponseSupport(Response):
    """ A simple implementation of Response that
        stores the value attribute and request_key.
    """

    def __init__(self, request_key=None, value=None):
        """
        :param request_key the unique key that is used to identify the request.
        :param the value of the response.  The value is defined by the protocol.
        """
        self._request_key = request_key
        self._value = value

    def from_stream(self, file):
        return self

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        """
        :param value:   The new value to assign the value of this response.
        """
        self._value = value

    @property
    def response_key(self):
        return self._request_key


class AsyncLoop:
    """ Continually runs a given function on a background thread.
        Exceptions are logged and posted to a given handler
        The background thread is registered as a daemon.
    """

    def __init__(self, fn: Callable=None, args=(), log=logger):
        """
        :param fn the function to run
        :param args arguments to pass to fn
        """
        self.fn = fn
        self.args = args
        self.stop_event = threading.Event()
        self.background_thread = None
        self.logger = log

    def start(self):
        """
        Starts the background thread. It feels like this would suffer a race condition
        with concurrent updates to the unguarded self.background_thread
        """
        if self.background_thread is None:
            t = threading.Thread(target=self._run)
            t.setDaemon(True)
            self.background_thread = t
            t.start()

    def exception_handler(self, e):
        self.logger.exception(e)

    def _run(self):
        """ The processing loop for the background thread.
             Invokes the callable for as long as the stop signal is not received.
        """
        self._do(self.startup)
        while self.running():
            self._do(self.loop)
        self._do(self.shutdown)
        logger.info("background thread exiting")

    def _do(self, callme):
        """ runs a function and captures any exceptions """
        try:
            time.sleep(0)
            callme()
        except Exception as e:
            time.sleep(0)
            self.exception_handler(e)

    def startup(self):
        """ template method called when the thread starts"""
        pass

    def loop(self):
        self.fn(*self.args)

    def shutdown(self):
        """ template method called when the thread exits """
        pass

    def running(self):
        return not self.stop_event.is_set()

    def stop(self):
        event = self.stop_event
        event.set()
        thread = self.background_thread
        self.background_thread = None
        if thread and thread is not threading.current_thread():
            thread.join()


class BaseAsyncProtocolHandler:
    """
    Wraps a conduit in an asynchronous request/response handler. The format for the requests and responses is not
    defined at this level, but the class takes care of registering requests sent along with a future response and
    associating incoming responses with the originating request.

    The primary method to use is async_request(r:Request) which asynchronously sends the request and fetches the
    response. The returned FutureResponse can be used by the caller to check if the response has arrived or wait
    for the response.

    To handle unsolicited responses (with no originating request), use add_unmatched_response_handler(). Subclasses
    may instead provide their own asynchronous handler methods that conform to the expected protocol.

    To receive all requests/responses transmitted over the channel,
     add a listener to request_handler/response_handler. Request
     handlers receive the future corresponding to the request. Response
     handlers receive the response, and any associated futures.

     :param conduit: The conduit over which the protocol is conducted
    """

    def __init__(self, conduit: Conduit):
        self._conduit = conduit
        self._requests = defaultdict(list)
        self._unmatched = []
        self.async_thread = None
        self.request_handlers = EventSource()
        self.response_handlers = EventSource()
        self.async_thread = AsyncLoop(self.background_loop)
        # if matcher:
        #     self._matching_futures = types.MethodType(
        #         matcher, self, BaseAsyncProtocolHandler)

    def start_background_thread(self):
        self.async_thread.start()

    def stop_background_thread(self):
        self.async_thread.stop()

    def add_unmatched_response_handler(self, fn):
        """add a function that is called with unsolicited responses.

        :param fn: A callable that takes a single argument. This function is called with any responses that did not
                originate from a request (such as logs, events and autonomous actions.)
        """
        if fn not in self._unmatched:
            self._unmatched.append(fn)

    def remove_unmatched_response_handler(self, fn):
        self._unmatched.remove(fn)

    def async_request(self, request: Request) -> FutureResponse:
        """ Asynchronously sends a request to the conduit.
        :param request: The request to send.
        :return: A FutureResponse where the corresponding response to the request can be retrieved when it arrives.
        """
        future = FutureResponse(request)
        self.request_handlers.fire(future)
        self._register_future(future)
        self._stream_request(request)
        return future

    def discard_future(self, future: FutureResponse):
        self._unregister_future(future)

    def _stream_request(self, request):
        """ arranges for the request to be streamed. This implementation is synchronous, but subclasses may choose
            to send the request asynchronously. """
        request.to_stream(self._conduit.output)
        # self._conduit.output.flush()
        self._stream_request_sent(request)

    def _register_future(self, future: FutureResponse):
        """
        registers a FutureResponse so that it can be later retrieved when the corresponding response arrives.
        """
        request = future.request
        if request.response_keys:
            for key in request.response_keys:
                l = self._requests[key]
                l.append(future)
                # todo - handle cancelled/timedout etc.. or otherwise unclaimed FutureResponse objects in
                # would really like weak referencing here so if the caller doesn't care about the future,
                # then neither do we.

    def _unregister_future(self, future: FutureResponse):
        request = future.request
        if request.response_keys:
            for key in request.response_keys:
                l = self._requests.get(key)
                l.remove(future)
                if not len(l):
                    del self._requests[key]

    @abstractmethod
    def _decode_response(self) -> Response:
        """  Template method for subclasses. reads/decodes the next response from the conduit. """
        raise NotImplementedError()

    def background_loop(self):
        """
        the primary function that pumps messages from the conduit.
        Reads responses via read_response() so long as the conduit is open.
        When the conduit is closed, the background thread is terminated.
        """
        return self.read_response_async()

    def read_response_async(self):
        """called on the background thread to process responses from the conduit.
        If the conduit is closed, the background thread is stopped. Otherwise the read_response() method is called. """
        if not self._conduit.open:
            self.async_thread.stop()
            return None
        else:
            return self.read_response()

    def read_response(self):
        """ synchronously reads the next response from the conduit and processes it. """
        response = self._decode_response()
        return self.process_response(response)

    def process_response(self, response: Response) -> Response:
        """
        Handles the response by associating with any previous request or notifying unmatched response
        listeners.

        Also notifies any general response handlers.
        """
        if response is not None:
            futures = self._matching_futures(response)
            if futures:
                for f in futures:
                    self._set_future_response(f, response)
            else:
                for callback in self._unmatched:
                    callback(response)
            self.response_handlers.fire(response, futures)
        return response

    def _set_future_response(self, future: FutureResponse, response):
        """ sets the response on the given future and removes the associated request, now that it has been handled. """
        future.response = response
        self._unregister_future(future)

    def _matching_futures(self, response):
        """ finds matching futures for the given response """
        return self._requests.get(response.response_key)

    def _stream_request_sent(self, request):
        """ template method for subclasses to handle when a request has been sent """
        pass
