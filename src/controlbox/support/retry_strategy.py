import time

from controlbox.support.mixins import CommonEqualityMixin


class RetryStrategy:
    def __call__(self):
        return 0


class PeriodRetryStrategy(RetryStrategy, CommonEqualityMixin):

    def __init__(self, retry_period, last_tried=None):
        """
        :param retry_period: The retry period in seconds.
        """
        self.last_tried = last_tried         # the time last tried
        self.retry_period = retry_period

    def __call__(self, current_time=time.time, dryRun=False):
        """return the length of time until an operation should be retried
            :param dryRun: when True, the last tried time is not updated
        """
        result = self._time_to_retry(current_time)
        if not dryRun and result <= 0:
            self.last_tried = current_time
        return result

    def _time_to_retry(self, current_time):
        """
        Determines how long until the next try
        :param current_time: The current time.
        :return: True if it is time to retry opening the connector.
        """
        return 0 if self.last_tried is None else self.retry_period - (current_time - self.last_tried)
