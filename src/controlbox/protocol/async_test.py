import threading
import unittest
from unittest.mock import Mock, call, patch

import time
import timeout_decorator
from hamcrest import assert_that, calling, empty, equal_to, has_key, instance_of, is_, is_not, raises

from controlbox.protocol.async import AsyncLoop, BaseAsyncProtocolHandler, FutureResponse, FutureValue, Request, \
    Response, ResponseSupport
from controlbox.protocol.io_test import assert_delegates, debug_timeout
from controlbox.support.mixins import CommonEqualityMixin


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


class NastyException(Exception, CommonEqualityMixin):
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

    def test_set_result_or_exception_with_non_exception_sets_result(self):
        sut = FutureValue()
        sut.set_result_or_exception(1)
        self.assertEqual(sut.result(), 1)

    def test_set_result_or_exception_with_exception_raises_exception(self):
        sut = FutureValue()
        sut.set_result_or_exception(NastyException())
        assert_that(calling(sut.result), raises(NastyException))


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
    @timeout_decorator.timeout(debug_timeout(2))
    def test_real_thread(self):
        thread = None
        sut = None
        loopThread = None

        def fn():
            nonlocal thread, loopThread
            thread = threading.current_thread()
            loopThread = sut.background_thread
        loop = Mock(side_effect=fn)
        sut = AsyncLoop(loop)
        sut.startup = Mock()
        sut.shutdown = Mock()
        sut.start()
        while not loop.call_count:
            time.sleep(0)

        running = sut.running()
        assert_that(thread, is_not(None))
        assert_that(thread, is_(loopThread))
        assert_that(running, is_(True))
        sut.stop()
        stopped = not sut.running()
        assert_that(stopped, is_(True))
        assert_that(sut.background_thread, is_(None))
        sut.shutdown.assert_called_once()
        sut.startup.assert_called_once()

    @timeout_decorator.timeout(debug_timeout(1))
    def test_run_invokes_startup_shutdown_around_loop(self):
        running = Mock(return_value=True)

        def fn():
            if running.call_count > 1:
                running.return_value = False

        loop = Mock(side_effect=fn)
        sut = AsyncLoop(loop)
        sut.shutdown = Mock()
        sut.startup = Mock()
        sut.running = running
        manager = Mock()
        manager.attach_mock(sut.startup, 'startup')
        manager.attach_mock(sut.shutdown, 'shutdown')
        manager.attach_mock(loop, 'loop')
        sut._run()
        self.assertEqual(manager.mock_calls, [call.startup(), call.loop(), call.loop(), call.shutdown()])

    @timeout_decorator.timeout(debug_timeout(1))
    def test_an_exception_does_not_stop_the_loop(self):
        running = Mock(return_value=True)

        def fn():
            if running.call_count == 10:
                running.return_value = False
            raise NastyException()

        loop = Mock(side_effect=fn)
        sut = AsyncLoop(loop)
        sut.running = running
        sut.exception_handler = Mock()
        sut._run()
        self.assertEqual(loop.call_count, 10)
        self.assertEqual(sut.exception_handler.call_count, 10)
        sut.exception_handler.assert_called_with(NastyException())

    @patch('threading.Thread')
    def test_starting_an_already_started_loop(self, thread):
        sut = AsyncLoop([])
        the_thread = Mock()
        thread.return_value = the_thread
        sut.start()
        thread.assert_called_once()
        assert_that(sut.background_thread, is_(the_thread))
        assert_that(sut.stop_event, is_(instance_of(threading.Event)))
        the_thread.setDaemon.assert_called_once_with(True)
        thread.reset_mock()
        sut.start()
        thread.assert_not_called()

    def test_stop_when_not_started_is_harmless(self):
        sut = AsyncLoop()
        sut.stop()

    @timeout_decorator.timeout(2)
    def test_thread_exception(self):
        expected = NastyException()
        exception = None

        def fn():
            raise expected

        def capture_exception(e):
            nonlocal exception
            exception = e

        sut = AsyncLoop(fn)
        sut.exception_handler = Mock(side_effect=capture_exception)
        sut.start()
        while (not sut.exception_handler.call_count):
            time.sleep(0.01)
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
        while (sut.background_thread):  # pragma no cover - non-deterministic
            pass
        sut.stop()


class BaseAsyncProtocolHandlerTest(unittest.TestCase):
    def setUp(self):
        self.conduit = Mock()
        self.sut = BaseAsyncProtocolHandler(self.conduit)
        self.sut.response_handlers = Mock()

    def test_add_unmatched_request_handler(self):
        handler = Mock()
        sut = self.sut
        sut.add_unmatched_response_handler(handler)
        sut.add_unmatched_response_handler(handler)
        self.assertEqual(len(sut._unmatched), 1, 'expected handler to be added only once')
        handler.assert_not_called()

    def test_remove_unmatched_request_handler(self):
        handler = Mock()
        sut = self.sut
        sut.add_unmatched_response_handler(handler)
        sut.remove_unmatched_response_handler(handler)
        self.assertEqual(len(sut._unmatched), 0)

    def test_async_request(self):
        request = Mock()
        sut = self.sut
        sut.request_handlers = Mock()
        sut._register_future = Mock()
        sut._stream_request = Mock()
        result = sut.async_request(request)
        assert_that(result, is_(instance_of(FutureResponse)))
        assert_that(result.request, is_(request))
        sut.request_handlers.fire.assert_called_once_with(result)
        sut._register_future.assert_called_once_with(result)
        sut._stream_request.assert_called_once_with(request)

    def test_stream_request(self):
        request = Mock()
        self.sut._stream_request_sent = Mock()
        self.sut._stream_request(request)
        request.to_stream.assert_called_once_with(self.conduit.output)
        self.sut._stream_request_sent.assert_called_once_with(request)

    def test_register_future_no_response_keys_is_not_registered(self):
        request = Mock()
        request.response_keys = None
        future = FutureResponse(request)
        self.sut._register_future(future)
        assert_that(len(self.sut._requests), is_(0))

    def test_register_future_multiple_keys_is_registered_with_each_key(self):
        request = Mock()
        request.response_keys = 1, 2
        request2 = Mock()
        request2.response_keys = 1,

        future = FutureResponse(request)
        future2 = FutureResponse(request2)
        self.sut._register_future(future)
        self.sut._register_future(future2)
        assert_that(self.sut._requests[1], is_([future, future2]))
        assert_that(self.sut._requests[2], is_([future]))
        self.sut._unregister_future(future)
        assert_that(self.sut._requests[1], is_([future2]))
        assert_that(self.sut._requests, is_not(has_key(2)))
        self.sut._unregister_future(future2)
        assert_that(self.sut._requests, is_(empty()))

    def test_background_loop(self):
        assert_delegates(self.sut, 'background_loop', 'read_response_async')

    def test_read_response_async_stops_thread_if_conduit_is_closed(self):
        self.conduit.open = False
        self.sut.async_thread = Mock()
        result = self.sut.read_response_async()
        self.sut.async_thread.stop.assert_called_once()
        self.assertIsNone(result)

    def test_read_response_async_calls_read_response(self):
        self.conduit.open = True
        assert_delegates(self.sut, 'read_response_async', 'read_response')

    def test_read_response(self):
        response = ResponseSupport(1, 2)
        self.sut._decode_response = Mock(return_value=response)
        self.sut.process_response = Mock(return_value=Mock())
        result = self.sut.read_response()
        self.assertEqual(result, self.sut.process_response.return_value)

    def test_process_response_empty(self):
        self.assertIsNone(self.sut.process_response(None))

    def test_process_response_unsolicited(self):
        response = ResponseSupport(1, 2)
        handler = Mock()
        self.sut.add_unmatched_response_handler(handler)
        self.assertIs(self.sut.process_response(response), response)
        handler.assert_called_once_with(response)
        self.sut.response_handlers.fire.assert_called_once_with(response, None)

    def test_process_response_matching(self):
        response = ResponseSupport(1, 2)
        handler = Mock()
        future1 = FutureResponse(Mock())
        future2 = FutureResponse(Mock())
        self.sut._matching_futures = Mock(return_value=[future1, future2])
        self.sut._set_future_response = Mock()
        self.sut.add_unmatched_response_handler(handler)
        self.assertIs(self.sut.process_response(response), response)
        self.assertEqual(self.sut._set_future_response.mock_calls, [call(future1, response), call(future2, response)])
        self.sut.response_handlers.fire.assert_called_once_with(response, [future1, future2])
        handler.assert_not_called()

    def test_set_future_response(self):
        future = FutureResponse(Mock())
        response = ResponseSupport(1, 2)
        self.sut._unregister_future = Mock()
        self.sut._set_future_response(future, response)
        self.assertEqual(future.response, response)
        self.sut._unregister_future.assert_called_once_with(future)

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
