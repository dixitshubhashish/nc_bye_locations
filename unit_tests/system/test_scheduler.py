"""Unit tests for background medallion refresh scheduling and concurrency locking.

Tests scheduled ticks, error recovery, in-flight refresh deduplication, and on-demand background refresh triggers.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class SchedulerTests(unittest.TestCase):
    """Test suite for background refresh concurrency control and scheduler execution."""

    def setUp(self) -> None:
        """Ensure background threads finish and reset refreshing state prior to test."""
        for thread in threading.enumerate():
            if thread.name == "reporting-silver-refresh":
                thread.join(timeout=5)
        workflow_server.REPORTING_REFRESHING = False

    def tearDown(self) -> None:
        """Clean up active background threads and reset refreshing state after test."""
        for thread in threading.enumerate():
            if thread.name == "reporting-silver-refresh":
                thread.join(timeout=5)
        workflow_server.REPORTING_REFRESHING = False

    def test_tick_calls_silver_then_gold_and_resets_flag(self) -> None:
        """Verify _run_silver_gold_tick executes silver rebuild followed by gold rebuild."""
        calls: list[str] = []

        def fake_silver():
            calls.append("silver")
            return {"rows": 1, "invalid_rows": 0}

        def fake_gold():
            calls.append("gold")
            return {"views": ["a"]}

        with patch.object(workflow_server, "build_silver_layer", side_effect=fake_silver):
            with patch.object(workflow_server, "build_gold_layer", side_effect=fake_gold):
                ran = workflow_server._run_silver_gold_tick()

        self.assertTrue(ran)
        self.assertEqual(calls, ["silver", "gold"])
        self.assertFalse(workflow_server.REPORTING_REFRESHING)

    def test_tick_swallows_errors_and_still_resets_flag(self) -> None:
        """Verify _run_silver_gold_tick catches exceptions and releases REPORTING_REFRESHING flag."""
        with patch.object(workflow_server, "build_silver_layer", side_effect=RuntimeError("bigquery unavailable")):
            ran = workflow_server._run_silver_gold_tick()

        self.assertTrue(ran)
        self.assertFalse(workflow_server.REPORTING_REFRESHING)

    def test_tick_skips_if_a_refresh_is_already_in_flight(self) -> None:
        """Verify _run_silver_gold_tick skips execution if a refresh is currently running."""
        workflow_server.REPORTING_REFRESHING = True
        with patch.object(workflow_server, "build_silver_layer") as fake_silver:
            ran = workflow_server._run_silver_gold_tick()

        self.assertFalse(ran)
        fake_silver.assert_not_called()

    def test_scheduler_does_not_start_a_thread_at_import_time(self) -> None:
        """Verify background scheduler thread is not spawned on module import."""
        thread_names = {t.name for t in threading.enumerate()}
        self.assertNotIn("silver-gold-hourly-refresh", thread_names)

    def test_on_demand_refresh_rebuilds_gold_after_silver(self) -> None:
        """Verify _refresh_silver_background spawns background thread rebuilding silver and gold."""
        calls: list[str] = []

        def fake_silver():
            calls.append("silver")
            return {"rows": 1, "invalid_rows": 0}

        def fake_gold():
            calls.append("gold")
            return {"views": ["a"]}

        with patch.object(workflow_server, "build_silver_layer", side_effect=fake_silver):
            with patch.object(workflow_server, "build_gold_layer", side_effect=fake_gold):
                with patch.object(workflow_server, "sync_gold_mirror", return_value={"zip_brand_rows": 0, "location_rows": 0, "business_rows": 0}):
                    started = workflow_server._refresh_silver_background()

        self.assertTrue(started)
        for thread in threading.enumerate():
            if thread.name == "reporting-silver-refresh":
                thread.join(timeout=5)
        self.assertEqual(calls, ["silver", "gold"])
        self.assertFalse(workflow_server.REPORTING_REFRESHING)

    def test_save_mapper_triggers_background_refresh_unless_skipped(self) -> None:
        """Verify _maybe_refresh_after_save kicks off background refresh unless skip_cache_invalidation is True."""
        with patch.object(workflow_server, "_refresh_silver_background") as fake_refresh:
            with patch.object(workflow_server, "invalidate_cache"):
                workflow_server._maybe_refresh_after_save(skip_cache_invalidation=False)
        fake_refresh.assert_called_once()

        with patch.object(workflow_server, "_refresh_silver_background") as fake_refresh:
            with patch.object(workflow_server, "invalidate_cache"):
                workflow_server._maybe_refresh_after_save(skip_cache_invalidation=True)
        fake_refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
