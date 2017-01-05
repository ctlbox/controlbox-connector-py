import unittest

from hamcrest import assert_that, equal_to, is_, calling, raises

from controlbox.protocol.async import FutureValue, FutureResponse, Request, Response, ResponseSupport

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


if __name__ == '__main__':
    unittest.main()
