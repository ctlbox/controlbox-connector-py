import threading
import unittest
from unittest.mock import Mock

from hamcrest import assert_that, equal_to, is_, calling, raises, is_not

from controlbox.protocol.async import FutureValue, FutureResponse, Request, Response, ResponseSupport, AsyncLoop, \
    BaseAsyncProtocolHandler


class RequestTest(unittest.TestCase):
    def test_to_stream_is_abstract(self):
        assert_that(calling(Request().to_stream).with_args('abcd'), raises(NotImplementedError))

    def test_request_is_abstract(self):
        assert_that(calling(lambda: Request().response_keys), raises(NotImplementedError))


class ResponseTest(unittest.TestCase):
    def assign(self):
        Response().value = 5

    def test_abstract(self):
        assert_that(calling(Response().from_stream).with_args('abcd'), raises(NotImplementedError))
        assert_that(calling(lambda: Response().response_key), raises(NotImplementedError))
        assert_that(calling(lambda: Response().value), raises(NotImplementedError))
        assert_that(calling(self.assign), raises(NotImplementedError))


class NastyException(Exception):
    """ really nasty """


class FutureValueTestCase(unittest.TestCase):

    def test_default_value_extractor_returns_value(self):
        f = FutureValue()
        f.set_result(123)
        assert_that(f.value(), equal_to(123))

    def test_can_set_value_extractor(self):
        f = FutureValue()
        f.set_result([1, 2, 3])
        f._value_extractor = lambda x: " ".join(map(lambda x: str(x), x))
        assert_that(f.value(), equal_to("1 2 3"))

    def test_exception_value_is_raised(self):
        f = FutureValue()
        result = NastyException('the eggs are off')
        f.set_result(result)
        assert_that(calling(f.value), raises(NastyException))


class FutureResponseTestCase(unittest.TestCase):

    def setUp(self):
        self.request = Request()
        self.future = FutureResponse(self.request)

    def test_future_response_set_and_get(self):
        response = Response()
        self.future.response = response
        assert_that(self.future.response, is_(response))

    def test_future_response_set_result_and_get(self):
        response = Response()
        self.future.set_result(response)
        assert_that(self.future.response, is_(response))

    def test_request(self):
        self.assertEqual(self.future.request, self.request)

    def test_future_response_value_from_request(self):
        response = ResponseSupport()
        response.value = 123
        self.future.response = response
        assert_that(self.future.value(1), is_(123))

    def test_request_key(self):
        response = ResponseSupport(123)
        assert_that(response.response_key, is_(123))


class ResponseSupportTest(unittest.TestCase):
    def test_from_stream_returns_self(self):
        sut = ResponseSupport()
        assert_that(sut.from_stream('abcd'), is_(sut))


class AsyncLoopTest(unittest.TestCase):
    def test_thread_start(self):
        thread = None
        sut = None
        loopThread = None

        def fn():
            nonlocal thread, loopThread
            thread = threading.current_thread()
            loopThread = sut.background_thread

        sut = AsyncLoop(fn)
        sut.shutdown = Mock()
        sut.start()
        running = sut.running()
        sut.stop()
        stopped = not sut.running()
        assert_that(thread, is_not(None))
        assert_that(thread, is_(loopThread))
        assert_that(running, is_(True))
        assert_that(stopped, is_(True))
        assert_that(sut.background_thread, is_(None))
        sut.shutdown.assert_called_once()

    def test_thread_exception(self):
        expected = NastyException()
        exception = None

        def fn():
            raise expected

        def capture_exception(e):
            nonlocal exception
            exception = e

        sut = AsyncLoop(fn)
        sut.exception_handler = capture_exception
        sut.start()
        # todo - we may need to wait on the function having executed (e.g. a condition variable/event) to avoid a race
        sut.stop()
        assert_that(exception, is_(expected))

    def test_default_exception_handler_logs_exception(self):
        sut = AsyncLoop(None)
        sut.logger = Mock()
        e = NastyException()
        sut.exception_handler(e)
        sut.logger.exception.assert_called_once_with(e)

    def test_calling_stop_on_loop(self):
        sut = None

        def stop():
            nonlocal sut
            sut.stop()

        sut = AsyncLoop(stop)
        sut.start()
        while (sut.background_thread):
            pass
        sut.stop()


class BaseAsyncProtocolHandlerTest(unittest.TestCase):
    def setUp(self):
        self.conduit = Mock()
        self.sut = BaseAsyncProtocolHandler(self.conduit)

    def test_start_background_thread(self):
        sut = self.sut
        sut.async_thread = Mock()
        sut.start_background_thread()
        sut.async_thread.start.assert_called_once()

    def test_stop_background_thread(self):
        sut = self.sut
        sut.async_thread = Mock()
        sut.stop_background_thread()
        sut.async_thread.stop.assert_called_once()

    def test__stream_request(self):
        sut = self.sut
        response = Mock()
        sut._stream_request_sent = Mock(side_effect=sut._stream_request_sent)
        sut._stream_request(response)
        response.to_stream.assert_called_with(self.conduit.output)
        sut._stream_request_sent.assert_called_once_with(response)

    def test__decode_response_is_abstract(self):
        assert_that(calling(self.sut._decode_response), raises(NotImplementedError))


if __name__ == '__main__':  # pragma no cover
    unittest.main()
