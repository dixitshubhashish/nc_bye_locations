"""Unit tests for BigQuery storage initialization, health probes, and sample loading bootstrap routines.

Tests storage connection probes, dataset/table bootstrap, sample dataset lifecycle, and field catalog synchronization.
"""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    """Mock BigQuery query job object returning row results."""

    def __init__(self, rows: list[dict[str, int]] | None = None) -> None:
        self._rows = rows or [{"ok": 1}]

    def result(self) -> list[dict[str, int]]:
        return self._rows


class _FakeClient:
    """Mock BigQuery client recording executed SQL queries."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()


class BigQueryBootstrapTests(unittest.TestCase):
    """Test suite for BigQuery storage initialization and sample dataset loading."""

    def setUp(self) -> None:
        """Reset reporting refresh state before each test."""
        workflow_server.REPORTING_REFRESHING = False

    def test_storage_connection_writes_health_probe_and_prepares_zips(self) -> None:
        """Verify storage connection test executes probe query and prepares zip codes."""
        client = _FakeClient()

        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset") as ensure_dataset:
                    with patch.object(workflow_server, "prepare_zipcodes", return_value={"status": "ready", "rows": 33791, "loaded": True, "source": "bronze_copy"}) as prepare:
                        result = workflow_server.test_storage_connection()

        sql = "\n".join(client.queries)
        ensure_dataset.assert_called_once_with(client, "project", "bronze")
        prepare.assert_called_once_with()
        self.assertTrue(result["ok"])
        self.assertEqual(result["zips"]["rows"], 33791)
        self.assertEqual(result["zips"]["source"], "bronze_copy")
        self.assertIn("CREATE OR REPLACE TABLE `project.bronze.connection_health`", sql)
        self.assertIn("SELECT ok FROM `project.bronze.connection_health` LIMIT 1", sql)

    def test_ping_writes_health_probe_table(self) -> None:
        """Verify storage connection ping creates and queries connection_health table."""
        client = _FakeClient()

        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset") as ensure_dataset:
                    result = workflow_server.ping_storage_connection()

        sql = "\n".join(client.queries)
        ensure_dataset.assert_called_once_with(client, "project", "bronze")
        self.assertTrue(result["ok"])
        self.assertEqual(result["health"]["rows"], 1)
        self.assertIn("CREATE OR REPLACE TABLE `project.bronze.connection_health`", sql)

    def test_sample_loader_prepares_zips_before_existing_sample_refresh(self) -> None:
        """Verify load_sample_dataset prepares zip codes before triggering silver background refresh."""
        calls: list[str] = []

        def fake_prepare() -> dict[str, object]:
            calls.append("prepare_zips")
            return {"status": "ready", "rows": 33791, "loaded": False}

        def fake_status(*_args: object) -> dict[str, int]:
            calls.append("sample_status")
            return {"businesses": 15, "listings": 9272, "workflow_templates": 15, "error_listings": 141}

        def fake_silver() -> dict[str, int]:
            calls.append("silver")
            return {"rows": 9272}

        def fake_gold() -> dict[str, int]:
            calls.append("gold")
            return {"views": []}

        self.addCleanup(setattr, workflow_server, "REPORTING_REFRESHING", False)
        with patch.object(workflow_server, "_sample_loader_enabled", return_value=True):
            with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
                with patch.object(workflow_server, "_bigquery_client", return_value=object()):
                    with patch.object(workflow_server, "_ensure_businesses_table"):
                        with patch.object(workflow_server, "_ensure_source_types_table"):
                            with patch.object(workflow_server, "_ensure_workflow_templates_table"):
                                with patch.object(workflow_server, "prepare_zipcodes", side_effect=fake_prepare):
                                    with patch.object(workflow_server, "_sample_data_status", side_effect=fake_status):
                                        with patch.object(workflow_server, "build_silver_layer", side_effect=fake_silver):
                                            with patch.object(workflow_server, "build_gold_layer", side_effect=fake_gold):
                                                result = workflow_server.load_sample_dataset()
                                                for thread in threading.enumerate():
                                                    if thread.name == "reporting-silver-refresh":
                                                        thread.join(timeout=5)

        self.assertEqual(calls, ["prepare_zips", "sample_status", "silver", "gold"])
        self.assertTrue(result["already_loaded"])
        self.assertEqual(result["zips"]["rows"], 33791)
        self.assertEqual(result["silver"]["status"], "refreshing")

    def test_sample_dataset_status_reports_loaded_when_core_sample_tables_have_rows(self) -> None:
        """Verify sample_dataset_status returns loaded=True when core sample tables are present."""
        with patch.object(workflow_server, "_sample_loader_enabled", return_value=True):
            with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
                with patch.object(workflow_server, "_bigquery_client", return_value=object()):
                    with patch.object(workflow_server, "_sample_data_status", return_value={
                        "businesses": 15,
                        "listings": 9272,
                        "workflow_templates": 15,
                        "error_listings": 141,
                    }):
                        result = workflow_server.sample_dataset_status()

        self.assertTrue(result["enabled"])
        self.assertTrue(result["loaded"])
        self.assertEqual(result["locations"], 9272)

    def test_prepare_zipcodes_skips_copy_when_existing_count_is_complete(self) -> None:
        """Verify prepare_zipcodes skips copy query if us_zipcodes table is already populated."""
        client = _FakeClient()
        table = type("Table", (), {"num_rows": 33791})()
        client.get_table = lambda _table_ref: table

        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset"):
                    workflow_server.ZIP_REFERENCE_CACHE.clear()
                    result = workflow_server.prepare_zipcodes()

        self.assertTrue(result["loaded"])
        self.assertFalse(result["created"])
        self.assertEqual(result["rows"], 33791)
        self.assertEqual(client.queries, [])

    def test_prepare_zipcodes_uses_bigquery_side_copy_when_missing(self) -> None:
        """Verify prepare_zipcodes executes copy from public dataset when us_zipcodes table is missing."""
        client = _FakeClient()
        calls = {"get_table": 0}

        def fake_get_table(_table_ref: str):
            calls["get_table"] += 1
            if calls["get_table"] == 1:
                exc = Exception("missing")
                setattr(exc, "code", 404)
                raise exc
            return type("Table", (), {"num_rows": 33791})()

        client.get_table = fake_get_table

        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset"):
                    with patch.object(workflow_server, "resolve_bigquery_connection", return_value=("project", None)):
                        workflow_server.ZIP_REFERENCE_CACHE.clear()
                        result = workflow_server.prepare_zipcodes()

        sql = "\n".join(client.queries)
        self.assertTrue(result["loaded"])
        self.assertTrue(result["created"])
        self.assertEqual(result["rows"], 33791)
        self.assertIn("CREATE OR REPLACE TABLE `project.bronze.us_zipcodes`", sql)
        self.assertIn("bigquery-public-data.geo_us_boundaries.zip_codes", sql)
        self.assertIn("TO_HEX(SHA256(TO_JSON_STRING(STRUCT", sql)

    def test_gold_bootstrap_names_the_failing_stage(self) -> None:
        """Verify error message identifies the exact stage when gold reporting view creation fails."""
        class NotFound(Exception):
            code = 404

        class FakeClient:
            def get_table(self, _ref: str) -> None:
                raise NotFound("missing")

        with patch.object(workflow_server, "prepare_zipcodes", side_effect=RuntimeError("no external demographics access")):
            with self.assertRaisesRegex(RuntimeError, r"gold bootstrap failed at prepare_zipcodes: no external demographics access"):
                workflow_server._ensure_gold_reporting_views(FakeClient(), "project.gold")

    def test_field_catalog_tops_up_missing_standard_fields_without_a_full_reset(self) -> None:
        """Verify field_catalog adds missing standard fields incrementally without resetting catalog."""
        import sys
        import types
        from types import SimpleNamespace

        class FakeSchemaField:
            def __init__(self, name, field_type, mode="NULLABLE", default_value_expression=None):
                self.name = name

        class FakeLoadJobConfig:
            def __init__(self, schema=None):
                self.schema = schema

        class FakeLoadJob:
            def result(self):
                return None

        class FakeQueryJob:
            def __init__(self, rows):
                self._rows = rows

            def result(self):
                return self._rows

        existing_rows = [
            {"field_id": "f1", "business_id": None, "slug": "name", "label": "Restaurant Name", "table_name": "listings",
             "field_name": "name", "data_type": "string", "required": True, "hints": "[]", "aliases": "[]",
             "is_custom": False, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"},
        ]

        class FakeClient:
            def __init__(self):
                self.rows = list(existing_rows)
                self.loaded_batches = []

            def get_table(self, _ref):
                return SimpleNamespace(schema=[SimpleNamespace(name="business_id")])

            def query(self, _query):
                return FakeQueryJob(list(self.rows))

            def load_table_from_json(self, rows, _table_ref, job_config=None):
                self.loaded_batches.append(rows)
                self.rows.extend(rows)
                return FakeLoadJob()

        fake_bigquery = types.SimpleNamespace(SchemaField=FakeSchemaField, LoadJobConfig=FakeLoadJobConfig, Table=lambda *a, **k: None)
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        modules = {"google": fake_google, "google.cloud": fake_cloud, "google.cloud.bigquery": fake_bigquery}

        client = FakeClient()
        with patch.dict(sys.modules, modules):
            with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
                with patch.object(workflow_server, "_bigquery_client", return_value=client):
                    with patch.object(workflow_server, "_ensure_dataset"):
                        result = workflow_server.field_catalog()

        keys = {field["key"] for field in result}
        self.assertIn("ratings", keys)
        self.assertIn("name", keys)
        self.assertEqual(len(client.loaded_batches), 1)
        self.assertGreater(len(client.loaded_batches[0]), 1)

    def test_reporting_fallback_surfaces_the_real_bootstrap_error(self) -> None:
        """Verify reporting summary fallback surfaces gold bootstrap error message when queries fail."""
        import sys
        import types

        fake_bigquery = types.SimpleNamespace()
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        modules = {"google": fake_google, "google.cloud": fake_cloud, "google.cloud.bigquery": fake_bigquery}

        with patch.dict(sys.modules, modules):
            with patch.object(workflow_server, "_medallion_settings", side_effect=RuntimeError("gold bootstrap failed at build_silver_layer: table not found")):
                with patch.object(workflow_server, "get_mirror_status", return_value=None):
                    with patch.object(workflow_server, "get_cached_query", return_value=None):
                        result = workflow_server.reporting_summary({})

        self.assertIn("gold bootstrap failed at build_silver_layer", result["warning"])
        self.assertEqual(result["filter_options"]["brands"], [])


if __name__ == "__main__":
    unittest.main()
