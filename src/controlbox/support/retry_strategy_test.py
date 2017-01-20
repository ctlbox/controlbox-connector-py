from unittest import TestCase

from hamcrest import is_, assert_that

from controlbox.support.retry_strategy import PeriodRetryStrategy, RetryStrategy


class RetryStrategyTest(TestCase):
    def test_is_zero(self):
        assert_that(RetryStrategy()(), is_(0))


class PeriodRetryStrategyTest(TestCase):

    def setUp(self):
        self.retry_period = 60

    def test_will_retry_immediately_by_default(self):
        retry = PeriodRetryStrategy(self.retry_period)
        time = 123
        assert_that(retry(time), is_(0))
        assert_that(retry(time), is_(self.retry_period))

    def test_dry_run_does_not_advance(self):
        retry = PeriodRetryStrategy(self.retry_period)
        time = 123
        assert_that(retry(time, dryRun=True), is_(0))
        assert_that(retry(time), is_(0))
        assert_that(retry(time), is_(self.retry_period))

    def test_time_decreases_and_restarts(self):
        retry = PeriodRetryStrategy(self.retry_period)
        assert_that(retry(0), is_(0))       # 0, so period restarts
        assert_that(retry(50), is_(10))
        assert_that(retry(55), is_(5))
        assert_that(retry(65), is_(-5))     # <0, restart, without accumulating the overshoot
        assert_that(retry(65), is_(60))


