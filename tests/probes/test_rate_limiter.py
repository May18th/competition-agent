import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from rate_limiter import RateLimiter


class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.limiter = RateLimiter(limit=2, window_seconds=60, clock=lambda: self.now)

    def test_rejects_attempts_after_scope_limit(self):
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertTrue(self.limiter.is_limited("u1", "generate"))

    def test_scopes_have_independent_buckets(self):
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u1", "restyle"))

    def test_users_have_independent_buckets(self):
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u2", "generate"))

    def test_expired_window_is_cleaned_and_allows_new_attempt(self):
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.now += 60
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertEqual(self.limiter.cleanup(), 0)
        self.assertEqual(len(self.limiter._hits[("u1", "generate")]), 1)

    def test_cleanup_removes_expired_buckets(self):
        self.assertFalse(self.limiter.is_limited("u1", "generate"))
        self.assertFalse(self.limiter.is_limited("u2", "restyle"))
        self.assertEqual(self.limiter.cleanup(now=160), 2)
        self.assertEqual(self.limiter._hits, {})

    def test_app_uses_independent_operation_buckets_with_total_guard(self):
        from unittest.mock import patch
        import app as app_module

        old_operation = app_module._rate_limiter
        old_total = app_module._rate_total_limiter
        app_module._rate_limiter = RateLimiter(2, 60, clock=lambda: self.now)
        app_module._rate_total_limiter = RateLimiter(20, 60, clock=lambda: self.now)
        try:
            with app_module.app.test_request_context("/"):
                with patch.object(app_module, "_current_uid", return_value="uid-1"):
                    self.assertFalse(app_module._rate_limited("generate"))
                    self.assertFalse(app_module._rate_limited("generate"))
                    self.assertTrue(app_module._rate_limited("generate"))
                    self.assertFalse(app_module._rate_limited("restyle"))
        finally:
            app_module._rate_limiter = old_operation
            app_module._rate_total_limiter = old_total


if __name__ == "__main__":
    unittest.main()
