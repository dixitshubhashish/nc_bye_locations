from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from whitespace_tool import sqlite_cache


class GetDbConnectionRetryTests(unittest.TestCase):
    """Regression tests for a real incident (2026-09-10): a live QA pass
    caught two threads simultaneously wedged inside SQLite's own
    connection-open path under heavy concurrent load, making every endpoint
    that touches this mirror unresponsive for several minutes. A full
    connection-pool rewrite was judged too large a change hours before a
    live demo; this adds a small, bounded retry-with-backoff around
    sqlite3.connect() specifically for sqlite3.OperationalError, the
    concrete symptom observed, without changing anything about the normal
    success path."""

    def test_a_normal_connect_succeeds_on_the_first_attempt_no_retry(self) -> None:
        calls: list[int] = []
        real_connect = sqlite3.connect

        def counting_connect(*args, **kwargs):
            calls.append(1)
            return real_connect(*args, **kwargs)

        with patch.object(sqlite_cache.sqlite3, "connect", side_effect=counting_connect):
            with sqlite_cache.get_db_connection() as conn:
                self.assertIsNotNone(conn)
        self.assertEqual(len(calls), 1, "a healthy connect must not be retried")

    def test_a_transient_operational_error_is_retried_and_then_succeeds(self) -> None:
        real_connect = sqlite3.connect
        attempts: list[int] = []

        def flaky_connect(*args, **kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                raise sqlite3.OperationalError("database is locked")
            return real_connect(*args, **kwargs)

        with patch.object(sqlite_cache.time, "sleep", return_value=None):
            with patch.object(sqlite_cache.sqlite3, "connect", side_effect=flaky_connect):
                with sqlite_cache.get_db_connection() as conn:
                    self.assertIsNotNone(conn)
        self.assertEqual(len(attempts), 2, "one transient failure should be retried exactly once before succeeding")

    def test_persistent_failure_still_raises_not_swallowed(self) -> None:
        def always_fails(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        with patch.object(sqlite_cache.time, "sleep", return_value=None):
            with patch.object(sqlite_cache.sqlite3, "connect", side_effect=always_fails):
                with self.assertRaises(sqlite3.OperationalError):
                    with sqlite_cache.get_db_connection():
                        pass


if __name__ == "__main__":
    unittest.main()
