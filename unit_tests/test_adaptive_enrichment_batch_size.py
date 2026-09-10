from __future__ import annotations

import unittest

import whitespace_tool.workflow_server as workflow_server


class AdaptiveEnrichmentBatchSizeTests(unittest.TestCase):
    """Regression tests for the success-rate-adaptive full-speed batch size
    (explicit user ask, 2026-09-10): grow the batch after a mostly-successful
    pass, shrink it after a mostly-failed one, bounded to
    AUTO_REPAIR_ADAPTIVE_MIN/MAX_BATCH_SIZE (5-50) so a bad run never
    throttles itself down to not running at all, and a hot streak never
    grows past a size that would monopolise the shared BigQuery client."""

    def setUp(self) -> None:
        self._original = workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = self._original

    def test_a_high_success_rate_grows_the_batch(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 10
        workflow_server._record_enrichment_batch_result(attempted=10, resolved=9)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, 15)

    def test_a_low_success_rate_shrinks_the_batch(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 10
        workflow_server._record_enrichment_batch_result(attempted=10, resolved=1)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, 5)

    def test_a_mid_range_success_rate_leaves_the_batch_unchanged(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 10
        workflow_server._record_enrichment_batch_result(attempted=10, resolved=5)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, 10)

    def test_growth_never_exceeds_the_maximum(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = workflow_server.AUTO_REPAIR_ADAPTIVE_MAX_BATCH_SIZE
        workflow_server._record_enrichment_batch_result(attempted=10, resolved=10)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, workflow_server.AUTO_REPAIR_ADAPTIVE_MAX_BATCH_SIZE)

    def test_shrinkage_never_goes_below_the_minimum_it_always_keeps_running(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = workflow_server.AUTO_REPAIR_ADAPTIVE_MIN_BATCH_SIZE
        workflow_server._record_enrichment_batch_result(attempted=10, resolved=0)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, workflow_server.AUTO_REPAIR_ADAPTIVE_MIN_BATCH_SIZE)
        self.assertGreaterEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, 5)

    def test_an_empty_batch_does_not_change_the_size(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 10
        workflow_server._record_enrichment_batch_result(attempted=0, resolved=0)
        self.assertEqual(workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE, 10)

    def test_pacing_returns_the_adaptive_size_when_not_throttled(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 25
        workflow_server.ENRICHMENT_THROTTLED.clear()
        batch_size, _pause = workflow_server._enrichment_pacing()
        self.assertEqual(batch_size, 25)

    def test_pacing_ignores_the_adaptive_size_while_eased(self) -> None:
        workflow_server._ENRICHMENT_ADAPTIVE_BATCH_SIZE = 40
        workflow_server.ENRICHMENT_THROTTLED.set()
        try:
            batch_size, _pause = workflow_server._enrichment_pacing()
            self.assertEqual(batch_size, workflow_server.AUTO_REPAIR_EASED_BATCH_SIZE)
        finally:
            workflow_server.ENRICHMENT_THROTTLED.clear()


if __name__ == "__main__":
    unittest.main()
