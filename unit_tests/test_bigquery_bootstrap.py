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

        def fake_quality(*_args: object, **_kwargs: object) -> dict[str, object]:
            calls.append("quality")
            return {"metrics": {"invalid_listings": 0}}

        for thread in list(threading.enumerate()):
            if thread.name in ("reporting-silver-refresh", "automatic-review-repair"):
                thread.join(timeout=5)
        workflow_server.REPORTING_REFRESHING = False
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
                                                with patch.object(workflow_server, "reporting_quality_summary", side_effect=fake_quality):
                                                    with patch.object(workflow_server, "auto_repair_error_batch", return_value={"attempted": 0, "resolved": 0, "remaining": 0}):
                                                        # Sample loading no longer blocks the response on the silver/gold
                                                        # rebuild (see _background_medallion_refresh_status) - it kicks
                                                        # that off in a background thread instead, so wait for it here.
                                                        result = workflow_server.load_sample_dataset()
                                                        for thread in list(threading.enumerate()):
                                                            if thread.name in ("reporting-silver-refresh", "automatic-review-repair"):
                                                                thread.join(timeout=5)

        self.assertEqual(calls, ["prepare_zips", "sample_status", "silver", "gold", "quality"])
        self.assertTrue(result["already_loaded"])
        self.assertEqual(result["zips"]["rows"], 33791)
        self.assertEqual(result["silver"]["status"], "refreshing")

    def test_sample_dataset_status_reports_loaded_when_core_sample_tables_have_rows(self) -> None:
        # refresh=True exercises the compute path; the default now serves the
        # app_settings mirror so a page load does not run six BigQuery COUNTs.
        # The mirror read/write are stubbed so this never touches real state.
        written: dict = {}

        class _SourceCountClient:
            """Answers only the sample_locations source-count query."""

            def query(self, sql, *a, **k):
                assert "sample_locations.listings" in sql, sql
                return type("Job", (), {"result": lambda _self: [{"total": 22500}]})()

        client = _SourceCountClient()
        with patch.object(workflow_server, "_sample_loader_enabled", return_value=True), \
             patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=client), \
             patch.object(workflow_server, "_read_sample_status_mirror", return_value=None), \
             patch.object(workflow_server, "_write_sample_status_mirror", written.update), \
             patch.object(workflow_server, "_sample_data_status", return_value={
                 "businesses": 15,
                 "listings": 9272,
                 "workflow_templates": 15,
                 "error_listings": 141,
             }):
            result = workflow_server.sample_dataset_status(refresh=True)

        self.assertTrue(result["enabled"])
        self.assertTrue(result["loaded"])
        self.assertEqual(result["locations"], 9272)
        # 9,272 of 22,500 is a half-load, and must not be reported as complete.
        self.assertIs(result["complete"], False)
        self.assertEqual(result["source_locations"], 22500)
        self.assertEqual(written.get("locations"), 9272)

    def test_sample_status_serves_the_mirror_when_bigquery_is_unreachable(self) -> None:
        # A failed status check must never render "not loaded" over a loaded
        # warehouse - that is a claim, not a measurement.
        mirror = {"enabled": True, "loaded": True, "complete": True, "locations": 22500}

        def boom(*_a, **_k):
            raise RuntimeError("bigquery unavailable")

        with patch.object(workflow_server, "_sample_loader_enabled", return_value=True), \
             patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=object()), \
             patch.object(workflow_server, "_read_sample_status_mirror", return_value=mirror), \
             patch.object(workflow_server, "_sample_data_status", side_effect=boom):
            result = workflow_server.sample_dataset_status(refresh=True)

        self.assertTrue(result["loaded"])
        self.assertEqual(result["source"], "mirror_stale")

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

    def test_gold_bootstrap_names_the_failing_stage(self) -> None:
        class NotFound(Exception):
            code = 404

        class FakeClient:
            def get_table(self, _ref: str) -> None:
                raise NotFound("missing")

        with patch.object(workflow_server, "prepare_zipcodes", side_effect=RuntimeError("no external demographics access")):
            with self.assertRaisesRegex(RuntimeError, r"gold bootstrap failed at prepare_zipcodes: no external demographics access"):
                workflow_server._ensure_gold_reporting_views(FakeClient(), "project.gold")

    def test_field_catalog_tops_up_missing_standard_fields_without_a_full_reset(self) -> None:
        # A project whose field_catalogs table was already seeded before
        # "ratings" existed in the registry should pick it up on the next
        # call instead of requiring a full wipe.
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
                self.schema_updates = []
                self.queries = []

            def get_table(self, _ref):
                return SimpleNamespace(schema=[SimpleNamespace(name="business_id")])

            def query(self, _query):
                self.queries.append(_query)
                return FakeQueryJob(list(self.rows))

            def update_table(self, table, fields):
                self.schema_updates.append([f.name for f in table.schema])

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
        self.assertIn("name", keys)  # the pre-existing row is preserved
        self.assertEqual(len(client.loaded_batches), 1)  # one top-up batch, not a full reseed
        self.assertGreater(len(client.loaded_batches[0]), 1)  # every missing field, not just ratings

        # The ad-hoc business_id/content_hash ALTERs this used to carry were
        # generalized to reconcile against TABLE_SCHEMAS, so a column added
        # later (is_archived/archived_at, for the archive-not-delete flow)
        # reaches an already-deployed table instead of needing its own
        # hardcoded ALTER. Hardcoding one column at a time is exactly how
        # error_listings ended up missing has_ai_suggestion in production.
        self.assertEqual(len(client.schema_updates), 1)
        added = set(client.schema_updates[0])
        for column in ("is_archived", "archived_at", "content_hash", "slug", "label"):
            self.assertIn(column, added, column)

        # Archived custom fields must never reach the mapper/field pickers.
        self.assertTrue(any("is_archived IS NOT TRUE" in q for q in client.queries))

    def test_reporting_fallback_uses_product_safe_bootstrap_message(self) -> None:
        # A failed first-time bootstrap should not leak BigQuery URLs/job IDs
        # into the UI. The real exception is logged server-side; the response
        # stays product-safe.
        import sys
        import types

        fake_bigquery = types.SimpleNamespace()
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        modules = {"google": fake_google, "google.cloud": fake_cloud, "google.cloud.bigquery": fake_bigquery}

        with patch.dict(sys.modules, modules):
            with patch.object(workflow_server, "_medallion_settings", side_effect=RuntimeError("gold bootstrap failed at build_silver_layer: 400 GET https://bigquery.googleapis.com/example Job ID: abc")):
                with patch.object(workflow_server, "get_mirror_status", return_value=None):
                    result = workflow_server.reporting_summary({"test_case": ["product_safe_bootstrap_message"]})

        self.assertEqual(result["warning"], "Reporting data is being prepared. Please refresh shortly.")
        self.assertTrue(result["refreshing"])
        self.assertNotIn("bigquery.googleapis.com", result["warning"])
        self.assertNotIn("Job ID", result["warning"])
        self.assertEqual(result["filter_options"]["brands"], [])

    def test_sample_locations_dataset_is_strictly_protected_from_deletion(self) -> None:
        from whitespace_tool import warehouse_bigquery

        with self.assertRaises(PermissionError) as ctx1:
            warehouse_bigquery.clear_dataset_tables("project", "sample_locations")
        self.assertIn("CRITICAL SAFETY RULE", str(ctx1.exception))

        with self.assertRaises(PermissionError) as ctx2:
            warehouse_bigquery.drop_dataset_tables("project", "sample_locations")
        self.assertIn("CRITICAL SAFETY RULE", str(ctx2.exception))

    def test_clear_sample_dataset_resets_bronze_and_triggers_refresh(self) -> None:
        reset_called = []

        def fake_reset(client, project_id, dataset_id):
            reset_called.append((project_id, dataset_id))

        # clear_sample_dataset() fires a real daemon thread (clear_worker())
        # that goes on to call invalidate_cache()/_invoke_silver_layer()/
        # _rebuild_gold_and_mirror()/refresh_error_count() for real, entirely
        # outside this test's own `with patch.object(...)` scope (nothing
        # joins it - it's fire-and-forget by design in production). Left
        # unmocked, that thread races the SQLite mirror against whatever
        # OTHER test happens to be running concurrently once this test
        # returns and its mocks are torn down - a real, reproduced
        # multi-second hang (2026-09-10, full-suite stress run + a
        # PYTHONFAULTHANDLER thread dump caught it stuck inside
        # sqlite_cache.get_db_connection() at the same time as an unrelated
        # test in this same file). Mocking threading.Thread itself is the
        # correct fix here (not mocking each individual downstream call,
        # which would just move the leak) - this test only asserts on
        # clear_sample_dataset()'s own return value, not on anything
        # clear_worker() does.
        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=object()):
                with patch.object(workflow_server, "_reset_sample_data", side_effect=fake_reset):
                    with patch.object(workflow_server, "_background_medallion_refresh_status", return_value={"status": "refreshing"}):
                        with patch.object(workflow_server.threading, "Thread"):
                            result = workflow_server.clear_sample_dataset()

        self.assertTrue(result["cleared"])
        self.assertEqual(reset_called, [("project", "bronze")])
        self.assertEqual(result["silver"]["status"], "refreshing")

    def test_clear_sample_dataset_blocks_if_target_is_sample_locations(self) -> None:
        with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "sample_locations", None)):
            with self.assertRaises(PermissionError) as ctx:
                workflow_server.clear_sample_dataset()
        self.assertIn("CRITICAL SAFETY RULE", str(ctx.exception))

    def test_reporting_summary_suppresses_raw_404_table_not_found(self) -> None:
        import sys
        import types
        fake_bigquery = types.SimpleNamespace()
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        modules = {"google": fake_google, "google.cloud": fake_cloud, "google.cloud.bigquery": fake_bigquery}

        with patch.dict(sys.modules, modules):
            with patch.object(workflow_server, "_medallion_settings", side_effect=RuntimeError("gold bootstrap failed at build_gold_layer: 404 Not found: Table keen-device-610:birdeye_silver_listings.listings_enriched was not found")):
                with patch.object(workflow_server, "get_mirror_status", return_value=None):
                    result = workflow_server.reporting_summary({})

        self.assertEqual(result["warning"], "")
        self.assertEqual(result["totals"]["total_locations"], 0)


if __name__ == "__main__":
    unittest.main()


class MasterDeleteDropTests(unittest.TestCase):
    """The master delete dropped 21 objects across three datasets one HTTP
    round trip at a time, and built a brand new bigquery.Client per dataset
    that it never closed - the exact gRPC socket/OOM leak pattern this repo
    already records."""

    class _Table:
        def __init__(self, table_id, table_type="TABLE"):
            self.table_id = table_id
            self.table_type = table_type
            self.reference = f"ref/{table_id}"

    class _Client:
        def __init__(self, tables):
            self._tables = tables
            self.queries = []
            self.deleted = []
            self.closed = False

        def list_tables(self, _ref):
            return list(self._tables)

        def query(self, sql, *a, **k):
            self.queries.append(sql)
            return type("Job", (), {"result": lambda _s: []})()

        def delete_table(self, ref, not_found_ok=False):
            self.deleted.append(ref)

        def close(self):
            self.closed = True

    def _run(self, tables):
        from whitespace_tool import warehouse_bigquery

        client = self._Client(tables)
        result = warehouse_bigquery.drop_dataset_tables("project", "bronze", None, client=client)
        return client, result

    def test_every_object_is_deleted_and_reported(self):
        tables = [self._Table(f"t{i}") for i in range(10)]
        client, result = self._run(tables)
        self.assertEqual(len(client.deleted), 10)
        self.assertEqual(sorted(result["dropped_tables"]), sorted(f"t{i}" for i in range(10)))
        # MEASURED: collapsing these into one multi-statement DROP job was
        # SLOWER (9.4s vs 8.1s for 14 objects) - a query job carries seconds
        # of fixed scheduling overhead that a REST delete does not. So the
        # cheap per-object call stays; concurrency is what makes it fast.
        self.assertEqual(client.queries, [])

    def test_object_types_are_preserved_in_the_report(self):
        client, result = self._run([self._Table("tbl"), self._Table("vw", "VIEW"),
                                    self._Table("mv", "MATERIALIZED_VIEW")])
        by_name = {entry["name"]: entry["type"] for entry in result["dropped_objects"]}
        self.assertEqual(by_name["vw"], "VIEW")
        self.assertEqual(by_name["mv"], "MATERIALIZED_VIEW")
        self.assertEqual(by_name["tbl"], "TABLE")
        self.assertEqual(len(client.deleted), 3)

    def test_deletes_run_concurrently(self):
        import inspect
        from whitespace_tool import warehouse_bigquery

        source = inspect.getsource(warehouse_bigquery.drop_dataset_tables)
        self.assertIn("ThreadPoolExecutor(", source)
        self.assertIn("pool.map(drop_one, table_items)", source)

    def test_a_caller_supplied_client_is_not_closed(self):
        client, _ = self._run([self._Table("t1")])
        self.assertFalse(client.closed, "must not close a client it does not own")

    def test_an_empty_dataset_does_no_work(self):
        client, result = self._run([])
        self.assertEqual(client.deleted, [])
        self.assertEqual(client.queries, [])
        self.assertEqual(result["dropped_tables"], [])

    def test_master_delete_reuses_one_client_across_all_three_datasets(self):
        import inspect
        import whitespace_tool.workflow_server as ws

        source = inspect.getsource(ws.master_delete_data)
        self.assertIn("client = _bigquery_client(project_id, credentials_json)", source)
        self.assertIn("drop_dataset_tables(project_id, dataset_id, credentials_json, client=client)", source)
