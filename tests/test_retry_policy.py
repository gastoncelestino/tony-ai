import unittest

from kernel.retry_policy import can_retry


class TestRetryPolicy(unittest.TestCase):
    def test_first_attempt_is_allowed(self):
        self.assertTrue(can_retry(0))

    def test_retry_is_allowed_before_limit(self):
        self.assertTrue(can_retry(2))

    def test_retry_is_blocked_at_limit(self):
        self.assertFalse(can_retry(3))


if __name__ == "__main__":
    unittest.main()
