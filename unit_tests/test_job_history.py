from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache


class JobHistoryTests(unittest.TestCase):
    """save_events: one row per save_mapper() call, read back by the Job
    History panel. Status is derived once in record_save_event() so every
    reader agrees on what OK/FAILED/NEEDS_REVIEW means."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test_jobs.db")
        self._db_path_patch.start()
        sqlite_cache.init_sqlite_cache()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_clean_save_is_ok(self) -> None:
        sqlite_cache.record_save_event("evt-1", "Acme", total_rows=10, mapped_rows=10, error_listings=0, duplicate_listings_skipped=0)
        jobs = sqlite_cache.get_recent_save_events()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["status"], "OK")
        self.assertEqual(jobs[0]["event_id"], "evt-1")
        self.assertEqual(jobs[0]["brand"], "Acme")

    def test_save_with_some_invalid_rows_needs_review(self) -> None:
        sqlite_cache.record_save_event("evt-2", "Acme", total_rows=10, mapped_rows=7, error_listings=3, duplicate_listings_skipped=0)
        jobs = sqlite_cache.get_recent_save_events()
        self.assertEqual(jobs[0]["status"], "NEEDS_REVIEW")

    def test_nothing_mapped_from_a_nonempty_batch_is_failed(self) -> None:
        sqlite_cache.record_save_event("evt-3", "Acme", total_rows=5, mapped_rows=0, error_listings=5, duplicate_listings_skipped=0)
        jobs = sqlite_cache.get_recent_save_events()
        self.assertEqual(jobs[0]["status"], "FAILED")

    def test_empty_batch_is_not_reported_as_failed(self) -> None:
        # total_rows == 0 (nothing submitted) is not the same failure mode
        # as "submitted rows but none were valid" - don't conflate them.
        sqlite_cache.record_save_event("evt-4", "Acme", total_rows=0, mapped_rows=0, error_listings=0, duplicate_listings_skipped=0)
        jobs = sqlite_cache.get_recent_save_events()
        self.assertEqual(jobs[0]["status"], "OK")

    def test_most_recent_job_is_returned_first(self) -> None:
        sqlite_cache.record_save_event("evt-a", "Acme", total_rows=1, mapped_rows=1, error_listings=0, duplicate_listings_skipped=0)
        sqlite_cache.record_save_event("evt-b", "Acme", total_rows=1, mapped_rows=1, error_listings=0, duplicate_listings_skipped=0)
        jobs = sqlite_cache.get_recent_save_events()
        self.assertEqual(jobs[0]["event_id"], "evt-b")
        self.assertEqual(jobs[1]["event_id"], "evt-a")

    def test_row_count_is_capped_so_the_table_cannot_grow_unbounded(self) -> None:
        for i in range(sqlite_cache.MAX_SAVE_EVENT_ROWS + 25):
            sqlite_cache.record_save_event(f"evt-{i}", "Acme", total_rows=1, mapped_rows=1, error_listings=0, duplicate_listings_skipped=0)
        with sqlite_cache.get_db_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM save_events").fetchone()["c"]
        self.assertEqual(total, sqlite_cache.MAX_SAVE_EVENT_ROWS)


class JobHistoryPaginationTests(unittest.TestCase):
    """The Job History "Show More" popup pages through every saved job
    rather than the panel's fixed top-10, via get_recent_save_events()'s
    offset param and count_save_events()."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test_jobs_page.db")
        self._db_path_patch.start()
        sqlite_cache.init_sqlite_cache()
        for i in range(35):
            sqlite_cache.record_save_event(f"evt-{i:02d}", "Acme", total_rows=1, mapped_rows=1, error_listings=0, duplicate_listings_skipped=0)

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_count_matches_total_rows_inserted(self) -> None:
        self.assertEqual(sqlite_cache.count_save_events(), 35)

    def test_offset_pages_do_not_overlap_and_cover_everything(self) -> None:
        page_size = 20
        page1 = sqlite_cache.get_recent_save_events(limit=page_size, offset=0)
        page2 = sqlite_cache.get_recent_save_events(limit=page_size, offset=page_size)
        self.assertEqual(len(page1), 20)
        self.assertEqual(len(page2), 15)
        ids1 = {job["event_id"] for job in page1}
        ids2 = {job["event_id"] for job in page2}
        self.assertEqual(ids1.isdisjoint(ids2), True)
        self.assertEqual(len(ids1 | ids2), 35)

    def test_most_recent_job_is_still_first_page_first_row(self) -> None:
        page1 = sqlite_cache.get_recent_save_events(limit=5, offset=0)
        self.assertEqual(page1[0]["event_id"], "evt-34")


if __name__ == "__main__":
    unittest.main()
