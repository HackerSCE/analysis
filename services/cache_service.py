import logging
import threading
import time


logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self, ttl_seconds, name="cache"):
        self.ttl_seconds = ttl_seconds
        self.name = name
        self._values = {}
        self._lock = threading.Lock()

    def get(self, key):
        now = time.time()
        with self._lock:
            item = self._values.get(key)
            if not item:
                return None
            if now - item["stored_at"] > self.ttl_seconds:
                self._values.pop(key, None)
                logger.info("%s expired key=%s", self.name, key)
                return None
            return item["value"]

    def set(self, key, value):
        with self._lock:
            self._values[key] = {
                "stored_at": time.time(),
                "value": value,
            }

    def clear_expired(self):
        now = time.time()
        with self._lock:
            expired_keys = [
                key
                for key, item in self._values.items()
                if now - item["stored_at"] > self.ttl_seconds
            ]
            for key in expired_keys:
                self._values.pop(key, None)
        return len(expired_keys)

    def size(self):
        self.clear_expired()
        with self._lock:
            return len(self._values)


class RateLimiter:
    def __init__(self, min_interval_seconds, name="rate_limiter"):
        self.min_interval_seconds = min_interval_seconds
        self.name = name
        self._lock = threading.Lock()
        self._next_allowed_at = 0

    def wait(self):
        with self._lock:
            now = time.time()
            sleep_for = max(0, self._next_allowed_at - now)
            if sleep_for:
                logger.info("%s sleeping %.2fs", self.name, sleep_for)
                time.sleep(sleep_for)
            self._next_allowed_at = time.time() + self.min_interval_seconds
