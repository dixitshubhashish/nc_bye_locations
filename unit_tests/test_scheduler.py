from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class SchedulerTests(unittest.TestCase):
    def tearDown(self) -> None:
        workflow_server.REPORTING_REFRESHING = False

    def test_tick_calls_silver_then_gold_and_resets_flag(self) -> None:
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
        with patch.object(workflow_server, "build_silver_layer", side_effect=RuntimeError("bigquery unavailable")):
            ran = workflow_server._run_silver_gold_tick()

        self.assertTrue(ran)
        self.assertFalse(workflow_server.REPORTING_REFRESHING)

    def test_tick_skips_if_a_refresh_is_already_in_flight(self) -> None:
        workflow_server.REPORTING_REFRESHING = True
        with patch.object(workflow_server, "build_silver_layer") as fake_silver:
            ran = workflow_server._run_silver_gold_tick()

        self.assertFalse(ran)
        fake_silver.assert_not_called()

    def test_scheduler_does_not_start_a_thread_at_import_time(self) -> None:
        thread_names = {t.name for t in threading.enumerate()}
        self.assertNotIn("silver-gold-hourly-refresh", thread_names)


if __name__ == "__main__":
    unittest.main()
