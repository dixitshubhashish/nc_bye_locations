from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    def __init__(self, rows: list[dict[str, int]] | None = None) -> None:
        self._rows = rows or [{"ok": 1}]

    def result(self) -> list[dict[str, int]]:
        return self._rows


class _FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()


class BigQueryBootstrapTests(unittest.TestCase):
    def test_storage_connection_writes_health_probe_and_prepares_zips(self) -> None:
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
                                                # Sample loading no longer blocks the response on the silver/gold
                                                # rebuild (see _background_medallion_refresh_status) - it kicks
                                                # that off in a background thread instead, so wait for it here.
                                                result = workflow_server.load_sample_dataset()
                                                for thread in threading.enumerate():
                                                    if thread.name == "reporting-silver-refresh":
                                                        thread.join(timeout=5)

        self.assertEqual(calls, ["prepare_zips", "sample_status", "silver", "gold"])
        self.assertTrue(result["already_loaded"])
        self.assertEqual(result["zips"]["rows"], 33791)
        self.assertEqual(result["silver"]["status"], "refreshing")

    def test_sample_dataset_status_reports_loaded_when_core_sample_tables_have_rows(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
