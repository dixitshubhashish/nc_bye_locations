from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


def _fake_bigquery_modules():
    """Other suites in this repo inject a fake google.cloud.bigquery into
    sys.modules and, on cleanup, leave the real namespace package in a
    degraded state - a later `from google.cloud import bigquery` can then
    resolve to a module missing QueryJobConfig. Every test that needs the
    symbol injects its own fake for exactly this reason; do the same here so
    these tests don't depend on suite ordering (they passed standalone and
    failed only in a full-suite run)."""
    fake_bigquery = types.SimpleNamespace(
        QueryJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
        ArrayQueryParameter=lambda name, type_, value: (name, type_, value),
        ScalarQueryParameter=lambda name, type_, value: (name, type_, value),
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


class _FakeJob:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def result(self) -> list[dict]:
        return self._rows


class _FakeClient:
    """Returns one row per .query() call, so callers can tell how many live
    BigQuery queries actually ran."""

    def __init__(self) -> None:
        self.query_count = 0

    def query(self, query: str, job_config=None):
        self.query_count += 1
        return _FakeJob([{"bucket": "2024-01-01", "cnt": 5}])


class _QueryRecordingClient:
    """Records every query's SQL text instead of asserting on row content -
    used to catch a query that references a column that doesn't exist on
    the table it selects from, which a content-blind fake client (like
    _FakeClient above) can never catch since it returns the same fixed row
    regardless of what SQL was actually sent."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, query: str, job_config=None):
        self.queries.append(query)
        return _FakeJob([{"bucket": "2024-01-01", "cnt": 5}])


class ReportingTimeseriesQueryColumnTests(_FakeBigQueryModuleMixin):
    """Regression tests for real column-reference bugs in the four
    Trends Over Time queries - a content-blind fake client can't catch
    these, so assertions run against the actual SQL text sent."""

    def _run(self):
        client = _QueryRecordingClient()
        with patch.object(workflow_server, "get_cached_query", return_value=None):
            with patch.object(workflow_server, "set_cached_query"):
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=client):
                        workflow_server.reporting_timeseries({"period": ["1M"]})
        return client.queries

    def test_locations_query_joins_businesses_instead_of_selecting_brand_name_directly(self) -> None:
        # Regression: the "locations" query used to select brand_name
        # directly from `listings`, a column that table doesn't have (only
        # business_id - brand comes from a join to `businesses`). Against a
        # real warehouse this raised inside _collect()'s broad except and
        # was swallowed into an empty series with just a log warning -
        # "Trends Over Time is empty" with no visible error.
        queries = self._run()
        self.assertEqual(len(queries), 4)
        locations_query = queries[0]
        self.assertIn("FROM `project.gold.listings` l", locations_query)
        self.assertIn("LEFT JOIN `project.gold.businesses` b", locations_query)
        self.assertNotIn("COALESCE(brand_name, business_id, 'Unknown')", locations_query)

    def test_fix_queries_join_error_listings_for_business_id_not_a_nonexistent_column(self) -> None:
        # quality_fix_events carries no business_id of its own (only
        # event_id/row_number) - joining straight to businesses on a
        # qf.business_id that doesn't exist would raise the same class of
        # "Unrecognized name" error the locations regression above already
        # covers. Must join through error_listings first.
        queries = self._run()
        ai_query, manual_query = queries[2], queries[3]
        for query in (ai_query, manual_query):
            self.assertIn("FROM `project.gold.quality_fix_events` qf", query)
            self.assertIn("LEFT JOIN `project.gold.error_listings` e", query)
            self.assertIn("ON e.event_id = qf.event_id AND e.row_number = qf.row_number", query)
            self.assertIn("LEFT JOIN `project.gold.businesses` b", query)
            self.assertIn("ON b.business_id = e.business_id", query)
            self.assertNotIn("qf.business_id", query)
        self.assertIn("qf.created_at", ai_query)
        self.assertNotIn("qf.fixed_at", ai_query)
        self.assertIn("AND qf.fix_type = 'AI' AND qf.processed AND qf.improved", ai_query)
        self.assertIn("AND qf.fix_type = 'MANUAL' AND qf.processed AND qf.improved", manual_query)

    def test_day_is_the_finest_granularity_even_for_the_1d_period(self) -> None:
        # Explicit ask: "granularity till day level only" - 1D used to
        # bucket by HOUR.
        with patch.object(workflow_server, "get_cached_query", return_value=None):
            with patch.object(workflow_server, "set_cached_query"):
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=_FakeClient()):
                        result = workflow_server.reporting_timeseries({"period": ["1D"]})
        self.assertEqual(result["granularity"], "DAY")


class ReportingTimeseriesSeriesShapeTests(_FakeBigQueryModuleMixin):
    """Per RPT-05, the legend is never brands - every call returns all four
    metric-dimension series (Locations / Errors / AI Fixed / Manual Fixed),
    aggregated across whichever brands are filtered, never split into one
    line per brand."""

    def test_all_four_metric_series_are_returned_labelled_by_dimension_not_brand(self) -> None:
        with patch.object(workflow_server, "get_cached_query", return_value=None):
            with patch.object(workflow_server, "set_cached_query"):
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=_FakeClient()):
                        result = workflow_server.reporting_timeseries({"period": ["1M"]})
        labels = [s["label"] for s in result["series"]]
        self.assertEqual(labels, ["Locations", "Errors", "AI Fixed", "Manual Fixed"])
        for s in result["series"]:
            self.assertNotIn("brand", s)


class ReportingTimeseriesCacheTests(_FakeBigQueryModuleMixin):
    """/api/reporting/timeseries must be SQLite-cache-first, BigQuery-fallback -
    same contract as reporting_summary()/reporting_quality_summary() - so a
    dashboard left open doesn't re-hit BigQuery on every poll."""

    def test_cache_hit_returns_without_touching_bigquery(self) -> None:
        cached_payload = {"period": "1M", "granularity": "DAY", "series": [{"label": "Locations", "points": [{"date": "2024-01-01", "count": 5}]}]}

        with patch.object(workflow_server, "get_cached_query", return_value=cached_payload) as get_cached:
            with patch.object(workflow_server, "_bigquery_client", side_effect=AssertionError("BigQuery should not be queried on a cache hit")):
                result = workflow_server.reporting_timeseries({"period": ["1M"]})

        get_cached.assert_called_once()
        self.assertEqual(result["timeseries_cache"], "sqlite")
        self.assertEqual(result["series"], cached_payload["series"])

    def test_cache_miss_falls_back_to_bigquery_and_caches_the_result(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "get_cached_query", return_value=None):
            with patch.object(workflow_server, "set_cached_query") as set_cached:
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=client):
                        result = workflow_server.reporting_timeseries({"period": ["1M"]})

        self.assertGreater(client.query_count, 0)
        self.assertEqual(result["timeseries_cache"], "live")
        self.assertEqual(result["series"][0]["label"], "Locations")
        set_cached.assert_called_once()
        cached_key, cached_payload = set_cached.call_args[0]
        self.assertTrue(cached_key.startswith("reporting_timeseries:v2:1M:"))
        self.assertEqual(cached_payload["series"], result["series"])

    def test_refresh_param_bypasses_cache_even_on_a_hit(self) -> None:
        cached_payload = {"period": "1M", "granularity": "DAY", "series": [{"label": "Locations", "points": []}]}
        client = _FakeClient()

        with patch.object(workflow_server, "get_cached_query", return_value=cached_payload) as get_cached:
            with patch.object(workflow_server, "set_cached_query"):
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=client):
                        result = workflow_server.reporting_timeseries({"period": ["1M"], "refresh": ["1"]})

        get_cached.assert_not_called()
        self.assertGreater(client.query_count, 0)
        self.assertEqual(result["timeseries_cache"], "live")

    def test_empty_series_is_not_cached(self) -> None:
        # A BigQuery error inside _collect() is swallowed and logged, leaving
        # series == []. That failure result must not be written to the
        # SQLite cache, or a transient BQ hiccup would poison every
        # subsequent read for the cache's TTL.
        class _FailingClient:
            def query(self, query: str, job_config=None):
                raise RuntimeError("boom")

        with patch.object(workflow_server, "get_cached_query", return_value=None):
            with patch.object(workflow_server, "set_cached_query") as set_cached:
                with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "gold", None)):
                    with patch.object(workflow_server, "_bigquery_client", return_value=_FailingClient()):
                        result = workflow_server.reporting_timeseries({"period": ["1M"]})

        self.assertEqual(result["series"], [])
        set_cached.assert_not_called()


if __name__ == "__main__":
    unittest.main()
