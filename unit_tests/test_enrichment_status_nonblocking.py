from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class EnrichmentStatusNonBlockingTests(unittest.TestCase):
    """Regression test for a real incident (2026-09-10): enrichment_status()
    used to block on `with REPORTING_REFRESH_LOCK`, which a silver+gold
    rebuild holds for its ENTIRE duration (measured minutes) - every poll of
    /api/enrichment/status hung for as long as a rebuild was in flight,
    indistinguishable from the server being dead. Fixed to a non-blocking
    acquire; these tests hold the lock exactly like a real rebuild would and
    assert the call still returns almost immediately."""

    def setUp(self) -> None:
        # Isolate from whatever a real rebuild/other test left behind.
        self._quality_patch = patch.object(workflow_server, "_schedule_quality_fix_metrics_refresh", return_value=False)
        self._quality_patch.start()
        self.addCleanup(self._quality_patch.stop)
        self._stats_patch = patch.object(workflow_server, "get_auto_repair_stats", return_value={})
        self._stats_patch.start()
        self.addCleanup(self._stats_patch.stop)

    def test_returns_immediately_while_the_lock_is_held_elsewhere(self) -> None:
        workflow_server.REPORTING_REFRESH_LOCK.acquire()
        workflow_server.REPORTING_REFRESHING = True
        try:
            started = time.monotonic()
            status = workflow_server.enrichment_status()
            elapsed = time.monotonic() - started
        finally:
            workflow_server.REPORTING_REFRESHING = False
            workflow_server.REPORTING_REFRESH_LOCK.release()

        # Generous but meaningful: the old blocking code would have hung
        # until the lock was released, which for a real rebuild is minutes -
        # a bound of even 1 second proves this is not waiting on the lock.
        self.assertLess(elapsed, 1.0, "enrichment_status() blocked on a held lock instead of returning immediately")
        self.assertTrue(status["refreshing"])

    def test_reports_not_refreshing_and_releases_its_own_lock_when_free(self) -> None:
        # Sanity check the un-contended path still works normally and does
        # not leak the lock it successfully acquired.
        status = workflow_server.enrichment_status()
        self.assertFalse(status["refreshing"])
        # If the fix leaked a held lock, a fresh acquire here would hang -
        # bound it the same way so a regression fails fast instead of
        # hanging the whole test run.
        acquired = workflow_server.REPORTING_REFRESH_LOCK.acquire(timeout=1.0)
        self.assertTrue(acquired, "enrichment_status() leaked REPORTING_REFRESH_LOCK")
        workflow_server.REPORTING_REFRESH_LOCK.release()

    def test_concurrent_pollers_all_return_promptly_during_a_simulated_rebuild(self) -> None:
        # Closer to the real shape of the incident: several browser tabs/
        # polls landing while a rebuild thread holds the lock the whole time.
        workflow_server.REPORTING_REFRESH_LOCK.acquire()
        workflow_server.REPORTING_REFRESHING = True
        results: list[float] = []
        errors: list[BaseException] = []

        def poll() -> None:
            try:
                started = time.monotonic()
                workflow_server.enrichment_status()
                results.append(time.monotonic() - started)
            except BaseException as exc:  # noqa: BLE001 - surfaced via errors list
                errors.append(exc)

        threads = [threading.Thread(target=poll) for _ in range(5)]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2.0)
        finally:
            workflow_server.REPORTING_REFRESHING = False
            workflow_server.REPORTING_REFRESH_LOCK.release()

        self.assertFalse(errors, f"enrichment_status() raised under contention: {errors}")
        self.assertEqual(len(results), 5, "not every concurrent poller returned in time")
        self.assertTrue(all(elapsed < 1.0 for elapsed in results), results)


if __name__ == "__main__":
    unittest.main()
