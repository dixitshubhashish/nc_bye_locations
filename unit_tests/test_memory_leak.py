from __future__ import annotations

import gc
import tempfile
import threading
import tracemalloc
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import whitespace_tool.sqlite_cache as sqlite_cache
import whitespace_tool.workflow_server as workflow_server


class FakeQueryJob:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []
        self.num_dml_affected_rows = len(self._rows)

    def result(self) -> list[dict[str, Any]]:
        return self._rows


class FakeBigQueryClient:
    def __init__(self) -> None:
        self.query_calls: list[tuple[str, Any]] = []

    def query(self, query: str, job_config: Any = None) -> FakeQueryJob:
        self.query_calls.append((query, job_config))
        if "COUNT(*)" in query:
            return FakeQueryJob([{"total": 0}])
        return FakeQueryJob([])


class MemoryLeakAndResourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_single_client_reused_across_repair_worker(self) -> None:
        """Verify that start_auto_repair creates at most ONE BigQuery client
        across the entire repair run, reusing it across all batch iterations."""
        client_creation_count = 0
        fake_client = FakeBigQueryClient()

        def fake_create_client(*args: Any, **kwargs: Any) -> FakeBigQueryClient:
            nonlocal client_creation_count
            client_creation_count += 1
            return fake_client

        # Simulate 3 batches of 10 items (30 items total)
        batch_counter = 0

        def fake_batch(limit: int = 10, offset: int = 0, *, client: Any = None) -> dict[str, int]:
            nonlocal batch_counter
            self.assertIs(client, fake_client, "Client must be passed and reused in every batch")
            batch_counter += 1
            if batch_counter <= 3:
                return {"attempted": 10, "resolved": 5, "remaining": max(30 - batch_counter * 10, 0)}
            return {"attempted": 0, "resolved": 0, "remaining": 0}

        with patch.object(workflow_server, "_warehouse_settings", return_value=("test-proj", "test-dataset", None)), \
             patch.object(workflow_server, "_bigquery_client", side_effect=fake_create_client), \
             patch.object(workflow_server, "_count_error_listings_live", return_value=30), \
             patch.object(workflow_server, "auto_repair_error_batch", side_effect=fake_batch), \
             patch.object(workflow_server, "AUTO_REPAIR_BATCH_PAUSE_SECONDS", 0.0), \
             patch.object(workflow_server, "_schedule_quality_fix_metrics_refresh"), \
             patch.object(workflow_server, "refresh_error_count"), \
             patch.object(workflow_server, "invalidate_cache"), \
             patch.object(workflow_server, "_refresh_silver_background"):

            # Run the worker in test
            workflow_server.AUTO_REPAIR_THREAD = None
            res = workflow_server.start_auto_repair()
            self.assertEqual(res.get("status"), "started")

            for thread in list(threading.enumerate()):
                if thread.name == "automatic-review-repair":
                    thread.join(timeout=5)

            # Assert exactly 1 client was created for the entire run
            self.assertEqual(client_creation_count, 1, "Expected exactly 1 BigQuery client creation, found leak")
            self.assertEqual(batch_counter, 3, "Expected 3 batch invocations (30 items in batches of 10)")

    def test_no_unbounded_50k_fetches_during_auto_repair(self) -> None:
        """Verify list_rejected is never called with 50,000 limit during auto repair."""
        requested_limits: list[int] = []

        def spy_list_rejected(*args: Any, **kwargs: Any) -> dict[str, Any]:
            limit = kwargs.get("limit", args[2] if len(args) > 2 else 50)
            requested_limits.append(limit)
            return {"records": []}

        fake_client = FakeBigQueryClient()

        with patch.object(workflow_server, "list_rejected", side_effect=spy_list_rejected):
            workflow_server.auto_repair_error_batch(10, client=fake_client)

        for limit in requested_limits:
            self.assertLessEqual(limit, 10, f"Detected large unbounded fetch of limit={limit} in auto_repair_error_batch")

    def test_memory_allocation_remains_flat_across_repair_iterations(self) -> None:
        """Verify memory allocations do not leak or grow monotonically across repeated batch cycles."""
        fake_client = FakeBigQueryClient()
        claimed = ["event_test:1", "event_test:2"]

        with patch.object(workflow_server, "_warehouse_settings", return_value=("test-proj", "test-dataset", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=fake_client), \
             patch.object(workflow_server, "list_rejected", return_value={"records": []}):

            # Warmup to initialize static caches and sqlite schemas
            workflow_server.auto_repair_error_batch(10, client=fake_client)
            workflow_server._fetch_rejected_by_keys(claimed, client=fake_client)
            gc.collect()

            tracemalloc.start()
            snapshot_start = tracemalloc.take_snapshot()

            # Execute 25 continuous batch cycles
            for _ in range(25):
                workflow_server.auto_repair_error_batch(10, client=fake_client)
                workflow_server._fetch_rejected_by_keys(claimed, client=fake_client)

            gc.collect()
            snapshot_end = tracemalloc.take_snapshot()
            tracemalloc.stop()

            top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
            total_growth_bytes = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)

            # Ensure total heap growth across 25 iterations is strictly bounded under 500KB (well below MB-level leaks)
            self.assertLess(total_growth_bytes, 500 * 1024, f"Memory growth too high: {total_growth_bytes} bytes")


class AutoRepairYieldsToForegroundActivityTests(unittest.TestCase):
    """Background auto-repair must back off while a real user action (a
    do_POST request other than the worker's own start/stop calls) was
    recent, per the explicit "should be paused if other threads take
    priority" ask - it competes with foreground requests for the same
    BigQuery client / SQLite connections otherwise."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()
        self._original_activity = workflow_server.LAST_FOREGROUND_ACTIVITY_AT

    def tearDown(self) -> None:
        self._db_path_patch.stop()
        workflow_server.LAST_FOREGROUND_ACTIVITY_AT = self._original_activity

    def test_worker_sleeps_out_the_grace_period_when_activity_was_just_seen(self) -> None:
        fake_client = FakeBigQueryClient()
        sleep_calls: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def fake_batch(limit: int = 10, offset: int = 0, *, client: Any = None) -> dict[str, int]:
            return {"attempted": 10, "resolved": 10, "remaining": 0}

        workflow_server.LAST_FOREGROUND_ACTIVITY_AT = workflow_server.wall_clock_time()
        with patch.object(workflow_server, "_warehouse_settings", return_value=("test-proj", "test-dataset", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=fake_client), \
             patch.object(workflow_server, "_count_error_listings_live", return_value=10), \
             patch.object(workflow_server, "auto_repair_error_batch", side_effect=fake_batch), \
             patch.object(workflow_server, "AUTO_REPAIR_BATCH_PAUSE_SECONDS", 0.0), \
             patch.object(workflow_server, "FOREGROUND_IDLE_GRACE_SECONDS", 5.0), \
             patch.object(workflow_server, "sleep", side_effect=fake_sleep), \
             patch.object(workflow_server, "_schedule_quality_fix_metrics_refresh"), \
             patch.object(workflow_server, "refresh_error_count"), \
             patch.object(workflow_server, "invalidate_cache"), \
             patch.object(workflow_server, "_refresh_silver_background"):
            workflow_server.AUTO_REPAIR_THREAD = None
            workflow_server.start_auto_repair()
            for thread in list(threading.enumerate()):
                if thread.name == "automatic-review-repair":
                    thread.join(timeout=5)

        self.assertTrue(sleep_calls, "Expected the worker to sleep out the foreground activity grace period")
        self.assertGreater(sleep_calls[0], 4.0)

    def test_worker_does_not_wait_when_the_app_has_been_idle(self) -> None:
        fake_client = FakeBigQueryClient()
        sleep_calls: list[float] = []

        def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        def fake_batch(limit: int = 10, offset: int = 0, *, client: Any = None) -> dict[str, int]:
            return {"attempted": 10, "resolved": 10, "remaining": 0}

        workflow_server.LAST_FOREGROUND_ACTIVITY_AT = 0.0  # long ago
        with patch.object(workflow_server, "_warehouse_settings", return_value=("test-proj", "test-dataset", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=fake_client), \
             patch.object(workflow_server, "_count_error_listings_live", return_value=10), \
             patch.object(workflow_server, "auto_repair_error_batch", side_effect=fake_batch), \
             patch.object(workflow_server, "AUTO_REPAIR_BATCH_PAUSE_SECONDS", 0.0), \
             patch.object(workflow_server, "FOREGROUND_IDLE_GRACE_SECONDS", 5.0), \
             patch.object(workflow_server, "sleep", side_effect=fake_sleep), \
             patch.object(workflow_server, "_schedule_quality_fix_metrics_refresh"), \
             patch.object(workflow_server, "refresh_error_count"), \
             patch.object(workflow_server, "invalidate_cache"), \
             patch.object(workflow_server, "_refresh_silver_background"):
            workflow_server.AUTO_REPAIR_THREAD = None
            workflow_server.start_auto_repair()
            for thread in list(threading.enumerate()):
                if thread.name == "automatic-review-repair":
                    thread.join(timeout=5)

        # AUTO_REPAIR_BATCH_PAUSE_SECONDS (patched to 0.0) still sleeps once
        # per batch regardless - only the idle-grace wait (>= a few seconds)
        # must be absent when the app was already idle.
        self.assertTrue(all(seconds < 1.0 for seconds in sleep_calls), f"Unexpected idle-grace sleep: {sleep_calls}")


if __name__ == "__main__":
    unittest.main()
