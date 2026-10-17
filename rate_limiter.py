"""Thread-safe sliding-window rate limiting by user and operation scope."""

import threading
import time


class RateLimiter:
    def __init__(self, limit, window_seconds, clock=None):
        if limit < 1:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock or time.time
        self._hits = {}
        self._lock = threading.Lock()
        self._next_cleanup = 0

    def is_limited(self, uid, scope):
        """Record one attempt and return whether it exceeds the configured limit."""
        key = (uid, scope)
        now = self._clock()
        with self._lock:
            if now >= self._next_cleanup:
                self._cleanup_locked(now)
                self._next_cleanup = now + min(self.window_seconds, 60)

            hits = [hit for hit in self._hits.get(key, ())
                    if now - hit < self.window_seconds]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return True

            hits.append(now)
            self._hits[key] = hits
            return False

    def cleanup(self, now=None):
        """Remove expired buckets; an optional time is useful for deterministic tests."""
        with self._lock:
            return self._cleanup_locked(self._clock() if now is None else now)

    def _cleanup_locked(self, now):
        expired = [key for key, hits in self._hits.items()
                   if not any(now - hit < self.window_seconds for hit in hits)]
        for key in expired:
            del self._hits[key]
        return len(expired)
