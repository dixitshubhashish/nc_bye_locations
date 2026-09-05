from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache
import whitespace_tool.workflow_server as workflow_server


class ErrorCountStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_get_error_count_is_none_before_first_write(self) -> None:
        # None (not 0) means "never cached" - distinct from a real zero count.
        self.assertIsNone(sqlite_cache.get_error_count(""))
        self.assertIsNone(sqlite_cache.get_error_count("biz-1"))

    def test_set_then_get_roundtrips_per_business(self) -> None:
        sqlite_cache.set_error_count("", 7)
        sqlite_cache.set_error_count("biz-1", 3)
        self.assertEqual(sqlite_cache.get_error_count(""), 7)
        self.assertEqual(sqlite_cache.get_error_count("biz-1"), 3)

    def test_set_overwrites_prior_value(self) -> None:
        sqlite_cache.set_error_count("biz-1", 5)
        sqlite_cache.set_error_count("biz-1", 2)
        self.assertEqual(sqlite_cache.get_error_count("biz-1"), 2)


class CountErrorListingsCachingTests(unittest.TestCase):
    """count_error_listings serves SQLite on lazy reads and only hits the
    live BigQuery count when seeding or when refresh=True."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_first_read_seeds_from_live_then_serves_cache(self) -> None:
        with patch.object(workflow_server, "_count_error_listings_live", return_value=11) as live:
            first = workflow_server.count_error_listings("biz-1")
            self.assertEqual(first, 11)
            self.assertEqual(live.call_count, 1)  # seeded once
        # SQLite now has the value; a second lazy read must not touch BigQuery.
        with patch.object(workflow_server, "_count_error_listings_live", side_effect=AssertionError("should not query live")) as live2:
            second = workflow_server.count_error_listings("biz-1")
            self.assertEqual(second, 11)
            self.assertEqual(live2.call_count, 0)

    def test_refresh_true_recounts_live_and_writes_back(self) -> None:
        sqlite_cache.set_error_count("biz-1", 99)  # stale cached value
        with patch.object(workflow_server, "_count_error_listings_live", return_value=4) as live:
            fresh = workflow_server.count_error_listings("biz-1", refresh=True)
            self.assertEqual(fresh, 4)
            self.assertEqual(live.call_count, 1)
        # The fresh live value is now persisted, so a later lazy read sees 4.
        self.assertEqual(sqlite_cache.get_error_count("biz-1"), 4)
        with patch.object(workflow_server, "_count_error_listings_live", side_effect=AssertionError("should not query live")):
            self.assertEqual(workflow_server.count_error_listings("biz-1"), 4)

    def test_refresh_error_count_returns_and_persists(self) -> None:
        with patch.object(workflow_server, "_count_error_listings_live", return_value=6):
            self.assertEqual(workflow_server.refresh_error_count("biz-2"), 6)
        self.assertEqual(sqlite_cache.get_error_count("biz-2"), 6)


if __name__ == "__main__":
    unittest.main()
