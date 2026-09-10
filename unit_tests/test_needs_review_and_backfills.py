"""Coverage for backend work landed 2026-09-10 that had no test coverage yet:

- backfill_orphan_template_ids() / backfill_sample_template_source_structure()
  (dry_run correctness, no live rows/templates ARE required for the report to
  be exact).
- list_needs_review() / fix_needs_review_record() - the new Review-queue-
  adjacent endpoints backing the `vw_listings_needs_review` gold view.
- reporting_heatmap() - a basic smoke test (shape, score bounds), since it was
  entirely un-tested despite being brand new.

Follows the FakeClient/query-capture pattern already used in
test_silver_enrichment.py and the _FakeBigQueryModuleMixin pattern used in
test_custom_fields_lifecycle.py, rather than inventing a new one.
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as ws


def _fake_bigquery_modules():
    # Duplicated locally rather than imported cross-file, matching the
    # existing convention (test_custom_fields_lifecycle.py,
    # test_reporting_timeseries_cache.py each keep their own copy). Other
    # suites inject a fake google.cloud.bigquery into sys.modules and, on
    # cleanup, leave the real namespace package degraded - a later
    # `from google.cloud import bigquery` (list_needs_review() does this)
    # then resolves to a module missing QueryJobConfig. Injecting our own
    # fake here means suite ordering can't reach this file either.
    fake_bigquery = types.SimpleNamespace(
        QueryJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
        ArrayQueryParameter=lambda name, type_, value: (name, type_, value),
        ScalarQueryParameter=lambda name, type_, value: (name, type_, value),
        SchemaField=lambda name, field_type, mode="NULLABLE", default_value_expression=None:
            types.SimpleNamespace(name=name, field_type=field_type, mode=mode,
                                  default_value_expression=default_value_expression),
        Table=lambda *a, **k: types.SimpleNamespace(schema=[]),
        LoadJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.bigquery = fake_bigquery
    return {
        "google": types.ModuleType("google"),
        "google.cloud": fake_cloud,
        "google.cloud.bigquery": fake_bigquery,
    }


class _FakeBigQueryModuleMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._bq_mods = patch.dict(sys.modules, _fake_bigquery_modules())
        self._bq_mods.start()
        self.addCleanup(self._bq_mods.stop)


class BackfillOrphanTemplateIdsTests(unittest.TestCase):
    def test_dry_run_links_existing_template_without_mutating_anything(self) -> None:
        # One orphan pair with a real, existing (non-deleted) template on
        # file - dry_run must report "link_existing_template" and must not
        # touch insert_rows_json/run_sql_dml at all.
        calls: list[str] = []

        def fake_run_sql_rows(client, sql, params=None, *, label="", low_priority=False):
            calls.append(label)
            if label == "backfill_orphan_template_ids:pairs":
                return [{"business_id": "b1", "source_type_id": "s1", "orphan_count": 5}]
            if label == "backfill_orphan_template_ids:existing_template":
                return [{"workflow_template_id": "tmpl-1", "name": "existing_template"}]
            raise AssertionError(f"unexpected query: {label}")

        client = object()
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "run_sql_rows", side_effect=fake_run_sql_rows), \
             patch.object(ws, "run_sql_dml") as dml, \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "invalidate_template_cache") as invalidate_tmpl:
            result = ws.backfill_orphan_template_ids(dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["orphan_listings_total"], 5)
        self.assertEqual(result["orphan_pairs_total"], 1)
        self.assertEqual(result["templates_linked_existing"], 1)
        self.assertEqual(result["templates_created"], 0)
        self.assertEqual(result["listings_updated"], 0)
        self.assertEqual(result["pairs"][0]["action"], "link_existing_template")
        self.assertEqual(result["pairs"][0]["template_id"], "tmpl-1")
        # dry_run must not write anything.
        dml.assert_not_called()
        invalidate.assert_not_called()
        invalidate_tmpl.assert_not_called()

    def test_dry_run_creates_placeholder_when_no_existing_template(self) -> None:
        def fake_run_sql_rows(client, sql, params=None, *, label="", low_priority=False):
            if label == "backfill_orphan_template_ids:pairs":
                return [{"business_id": "b2", "source_type_id": "s2", "orphan_count": 3}]
            if label == "backfill_orphan_template_ids:existing_template":
                return []
            if label == "backfill_orphan_template_ids:business":
                return [{"name": "Acme", "slug": "acme"}]
            if label == "backfill_orphan_template_ids:source_type":
                return [{"name": "CSV"}]
            if label == "backfill_orphan_template_ids:sample":
                return [{"custom_fields": '{"extra_col": "x"}'}]
            raise AssertionError(f"unexpected query: {label}")

        client = object()
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "run_sql_rows", side_effect=fake_run_sql_rows), \
             patch.object(ws, "run_sql_dml") as dml:
            result = ws.backfill_orphan_template_ids(dry_run=True)

        self.assertEqual(result["templates_created"], 1)
        self.assertEqual(result["templates_linked_existing"], 0)
        pair = result["pairs"][0]
        self.assertEqual(pair["action"], "create_placeholder_template")
        self.assertEqual(pair["reconstructed_source_fields"], ["extra_col"])
        # Still dry-run - no mutation.
        dml.assert_not_called()

    def test_no_orphans_returns_zeroed_report(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_rows", return_value=[]):
            result = ws.backfill_orphan_template_ids(dry_run=True)
        self.assertEqual(result["orphan_listings_total"], 0)
        self.assertEqual(result["orphan_pairs_total"], 0)
        self.assertEqual(result["pairs"], [])


class BackfillSampleTemplateSourceStructureTests(unittest.TestCase):
    def test_dry_run_synthesizes_fields_for_a_template_with_listings(self) -> None:
        def fake_run_sql_rows(client, sql, params=None, *, label="", low_priority=False):
            if label == "backfill_sample_template_source_structure:targets":
                return [{"workflow_template_id": "t1", "components": '{"brand": "b1"}'}]
            if label == "backfill_sample_template_source_structure:listings":
                return [{
                    "template_id": "t1", "name": "Store A", "address": None,
                    "city_name": "Austin", "state_code": "TX", "zip_code": "78701",
                    "latitude": 30.1, "longitude": None, "phone_number": None,
                    "custom_fields": '{"loyalty_id": "1"}',
                }]
            raise AssertionError(f"unexpected query: {label}")

        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_rows", side_effect=fake_run_sql_rows), \
             patch.object(ws, "run_sql_dml") as dml:
            result = ws.backfill_sample_template_source_structure(dry_run=True)

        self.assertEqual(result["templates_missing_structure"], 1)
        self.assertEqual(result["templates_synthesized"], 1)
        self.assertEqual(result["templates_unavailable"], 0)
        sample = result["sample"][0]
        self.assertEqual(sample["template_id"], "t1")
        self.assertIn("loyalty_id", sample["source_fields"])
        self.assertIn("city_name", sample["source_fields"])
        dml.assert_not_called()

    def test_dry_run_flags_structure_unavailable_when_template_has_no_listings(self) -> None:
        def fake_run_sql_rows(client, sql, params=None, *, label="", low_priority=False):
            if label == "backfill_sample_template_source_structure:targets":
                return [{"workflow_template_id": "t2", "components": '{"brand": "b2"}'}]
            if label == "backfill_sample_template_source_structure:listings":
                return []
            raise AssertionError(f"unexpected query: {label}")

        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_rows", side_effect=fake_run_sql_rows):
            result = ws.backfill_sample_template_source_structure(dry_run=True)

        self.assertEqual(result["templates_unavailable"], 1)
        self.assertEqual(result["templates_synthesized"], 0)
        sample = result["sample"][0]
        self.assertEqual(sample["source_fields"], [])

    def test_no_targets_returns_zeroed_report(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_rows", return_value=[]):
            result = ws.backfill_sample_template_source_structure(dry_run=True)
        self.assertEqual(result["templates_missing_structure"], 0)
        self.assertEqual(result["sample"], [])


class _FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class ListNeedsReviewTests(_FakeBigQueryModuleMixin):
    def test_returns_records_and_isoformats_timestamps(self) -> None:
        import datetime

        class _Client:
            def query(self, sql, job_config=None):
                self.last_sql = sql
                return _FakeQueryJob([
                    {
                        "listing_id": "L1", "business_id": "b1", "brand_name": "Acme",
                        "source_type_id": "s1", "template_id": "t1",
                        "name": "Store 1", "address": "1 Main St", "city_name": "Austin",
                        "county": "Travis", "state_code": None, "state_name": None,
                        "zip_code": None, "country": "US", "latitude": None, "longitude": None,
                        "phone_number": None, "rejection_reason": "missing_state",
                        "user_reviewed": False,
                        "first_observed_at": datetime.datetime(2026, 9, 9, 12, 0, 0),
                        "last_observed_at": datetime.datetime(2026, 9, 10, 8, 0, 0),
                    },
                ])

        with patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)):
            result = ws.list_needs_review(client=_Client())

        self.assertEqual(result["has_more"], False)
        self.assertEqual(len(result["records"]), 1)
        record = result["records"][0]
        # datetimes must be JSON-safe strings, not raw datetime objects - this
        # was a real live bug ("Object of type datetime is not JSON
        # serializable" on every call) before it was fixed to .isoformat().
        self.assertIsInstance(record["first_observed_at"], str)
        self.assertIsInstance(record["last_observed_at"], str)
        self.assertEqual(record["first_observed_at"], "2026-09-09T12:00:00")

    def test_missing_gold_view_returns_empty_page_not_an_error(self) -> None:
        class _NotFound(Exception):
            code = 404

        class _Client:
            def query(self, sql, job_config=None):
                raise _NotFound("vw_listings_needs_review was not found")

        with patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)):
            result = ws.list_needs_review(client=_Client())

        self.assertEqual(result, {"records": [], "offset": 0, "limit": 50, "has_more": False})

    def test_reviewed_filter_produces_the_correct_clause(self) -> None:
        class _Client:
            def query(self, sql, job_config=None):
                self.last_sql = sql
                return _FakeQueryJob([])

        client = _Client()
        with patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)):
            ws.list_needs_review(reviewed="true", client=client)
        self.assertIn("AND user_reviewed IS TRUE", client.last_sql)

        client2 = _Client()
        with patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)):
            ws.list_needs_review(reviewed="false", client=client2)
        self.assertIn("AND user_reviewed IS NOT TRUE", client2.last_sql)


class FixNeedsReviewRecordTests(unittest.TestCase):
    def test_only_whitelisted_fields_are_written(self) -> None:
        captured = {}

        def fake_run_sql_dml(client, sql, params=None, *, label="", low_priority=False):
            captured["sql"] = sql
            captured["params"] = params
            return 1

        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_dml", side_effect=fake_run_sql_dml), \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "_refresh_silver_background") as refresh:
            result = ws.fix_needs_review_record("L1", {
                "state_code": "TX",
                # Not in the editable whitelist - must be silently dropped,
                # never reach the UPDATE, so this path can't rewrite columns
                # the review-edit UI was never scoped to touch.
                "business_id": "someone-elses-business",
                "is_deleted": True,
            })

        self.assertTrue(result["updated"])
        self.assertEqual(result["fields_applied"], ["state_code"])
        self.assertIn("state_code = @state_code", captured["sql"])
        self.assertNotIn("business_id", captured["params"])
        self.assertNotIn("is_deleted", captured["params"])
        self.assertIn("user_reviewed = TRUE", captured["sql"])
        # A real update must refresh silver so the fix eventually reaches
        # the gold view / mirror, same as other bronze write paths.
        invalidate.assert_called_once()
        refresh.assert_called_once()

    def test_no_editable_fields_raises(self) -> None:
        with self.assertRaises(ValueError):
            ws.fix_needs_review_record("L1", {"business_id": "x"})

    def test_blank_listing_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            ws.fix_needs_review_record("", {"state_code": "TX"})

    def test_no_matching_row_does_not_trigger_a_refresh(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "run_sql_dml", return_value=0), \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "_refresh_silver_background") as refresh:
            result = ws.fix_needs_review_record("does-not-exist", {"state_code": "TX"})

        self.assertFalse(result["updated"])
        invalidate.assert_not_called()
        refresh.assert_not_called()


class ReportingHeatmapSmokeTest(unittest.TestCase):
    def test_returns_expected_shape_with_scores_in_bounds(self) -> None:
        rows = [
            {
                "lat_cell": 1, "lon_cell": 1, "lat": 30.0, "lon": -97.0,
                "listing_count": 10, "population_median": 50000,
                "median_household_income": 60000, "zip_count": 3,
            },
            {
                "lat_cell": 2, "lon_cell": 2, "lat": 40.0, "lon": -80.0,
                "listing_count": 1, "population_median": 5000,
                "median_household_income": 30000, "zip_count": 1,
            },
            {
                # Missing income - must not crash, and must be excluded from
                # the income normalization range rather than dragging every
                # cell toward zero.
                "lat_cell": 3, "lon_cell": 3, "lat": 35.0, "lon": -90.0,
                "listing_count": 5, "population_median": 20000,
                "median_household_income": None, "zip_count": 2,
            },
        ]
        with patch.object(ws, "get_cached_query", return_value=None), \
             patch.object(ws, "set_cached_query") as set_cache, \
             patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "run_sql_rows", return_value=rows):
            result = ws.reporting_heatmap()

        self.assertEqual(result["cell_count"], 3)
        self.assertEqual(len(result["cells"]), 3)
        for cell in result["cells"]:
            self.assertIn("lat", cell)
            self.assertIn("lon", cell)
            self.assertIn("score", cell)
            self.assertGreaterEqual(cell["score"], 0.0)
            self.assertLessEqual(cell["score"], 1.0)
        # The highest listing_count/income/population cell should score
        # strictly higher than the lowest one.
        best = next(c for c in result["cells"] if c["listing_count"] == 10)
        worst = next(c for c in result["cells"] if c["listing_count"] == 1)
        self.assertGreater(best["score"], worst["score"])
        set_cache.assert_called_once()

    def test_uses_cache_when_available_and_not_refreshing(self) -> None:
        cached_payload = {"cells": [], "cell_half_width_km": 3.0, "cell_count": 0}
        with patch.object(ws, "get_cached_query", return_value=cached_payload), \
             patch.object(ws, "run_sql_rows") as run_rows:
            result = ws.reporting_heatmap()
        self.assertEqual(result, cached_payload)
        run_rows.assert_not_called()

    def test_state_and_city_scores_are_weighted_by_zip_and_listing_count(self) -> None:
        # Texas: one well-covered cell (10 listings, 3 ZIPs) plus one
        # single-ZIP, zero-listing outlier cell with a much higher raw
        # score (very high population/income relative to the other rows).
        # A straight average would let the outlier cell pull Texas's score
        # up toward its own high value; the zip_count+listing_count
        # weighting should instead keep Texas close to the well-covered
        # cell's own score.
        rows = [
            {
                "lat_cell": 1, "lon_cell": 1, "lat": 30.0, "lon": -97.0,
                "listing_count": 10, "population_median": 50000,
                "median_household_income": 60000, "zip_count": 3,
                "state_code": "TX", "state_name": "Texas", "city_name": "Austin",
            },
            {
                "lat_cell": 2, "lon_cell": 2, "lat": 30.5, "lon": -97.5,
                "listing_count": 0, "population_median": 200000,
                "median_household_income": 150000, "zip_count": 1,
                "state_code": "TX", "state_name": "Texas", "city_name": "Round Rock",
            },
            {
                "lat_cell": 3, "lon_cell": 3, "lat": 40.0, "lon": -80.0,
                "listing_count": 1, "population_median": 5000,
                "median_household_income": 30000, "zip_count": 1,
                "state_code": "PA", "state_name": "Pennsylvania", "city_name": "Erie",
            },
        ]
        with patch.object(ws, "get_cached_query", return_value=None), \
             patch.object(ws, "set_cached_query"), \
             patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "run_sql_rows", return_value=rows):
            result = ws.reporting_heatmap()

        self.assertIn("state_scores", result)
        self.assertIn("city_scores", result)

        by_state = {row["state"]: row for row in result["state_scores"]}
        self.assertEqual(set(by_state), {"TX", "PA"})
        tx = by_state["TX"]
        pa = by_state["PA"]
        self.assertEqual(tx["cell_count"], 2)
        self.assertEqual(tx["zip_count"], 4)
        self.assertEqual(tx["listing_count"], 10)
        self.assertEqual(pa["cell_count"], 1)
        self.assertGreaterEqual(tx["score"], 0.0)
        self.assertLessEqual(tx["score"], 1.0)

        # The Austin cell (weight 13) should dominate the outlier Round Rock
        # cell (weight 1) in Texas's weighted average - Texas's score should
        # land much closer to the Austin cell's own score than a straight
        # average of the two cells' scores would.
        austin_cell = next(c for c in result["cells"] if c["listing_count"] == 10)
        round_rock_cell = next(c for c in result["cells"] if c["zip_count"] == 1 and c["listing_count"] == 0)
        straight_avg = (austin_cell["score"] + round_rock_cell["score"]) / 2
        self.assertLess(abs(tx["score"] - austin_cell["score"]), abs(tx["score"] - straight_avg))

        by_city = {(row["city"], row["state"]): row for row in result["city_scores"]}
        self.assertIn(("Austin", "TX"), by_city)
        self.assertIn(("Round Rock", "TX"), by_city)
        self.assertIn(("Erie", "PA"), by_city)
        # A single-cell city's score should equal that cell's own score.
        self.assertEqual(by_city[("Erie", "PA")]["score"], next(c for c in result["cells"] if c["listing_count"] == 1)["score"])


if __name__ == "__main__":
    unittest.main()
