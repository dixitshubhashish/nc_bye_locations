from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from whitespace_tool.warehouse_bigquery import TABLE_PARTITION_SPECS, TABLE_SCHEMAS, push_to_bigquery


class WarehouseSchemaTests(unittest.TestCase):
    def test_partition_fields_exist_in_table_schemas(self) -> None:
        for table_name, spec in TABLE_PARTITION_SPECS.items():
            schema_fields = {field["name"] for field in TABLE_SCHEMAS[table_name]}
            self.assertIn(
                spec["field"],
                schema_fields,
                f"{table_name} partitions on missing field {spec['field']}",
            )

    def test_business_and_template_source_type_metadata_exists(self) -> None:
        business_fields = {field["name"] for field in TABLE_SCHEMAS["businesses"]}
        template_fields = {field["name"] for field in TABLE_SCHEMAS["workflow_templates"]}

        self.assertIn("source_type_id", business_fields)
        self.assertIn("source_type_id", template_fields)

    def test_sample_lineage_fields_exist(self) -> None:
        for table_name in ("businesses", "listings", "workflow_templates", "error_listings"):
            fields = {field["name"] for field in TABLE_SCHEMAS[table_name]}
            self.assertIn("is_sample_data", fields)
            self.assertIn("sample_batch_id", fields)
        for table_name in ("listings", "error_listings"):
            fields = {field["name"] for field in TABLE_SCHEMAS[table_name]}
            self.assertTrue({"template_id", "ingestion_id", "mapping_id"} <= fields)

    def test_tables_are_created_without_partitioning(self) -> None:
        created_tables = []

        class FakeSchemaField:
            def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", default_value_expression: str | None = None) -> None:
                self.name = name
                self.field_type = field_type
                self.mode = mode
                self.default_value_expression = default_value_expression

        class FakeTimePartitioning:
            def __init__(self, type_: str, field: str) -> None:
                self.type_ = type_
                self.field = field

        class FakeTable:
            def __init__(self, table_ref: str, schema: list[FakeSchemaField]) -> None:
                self.table_ref = table_ref
                self.schema = schema
                self.time_partitioning = None
                self.clustering_fields = None

        class FakeDataset:
            def __init__(self, dataset_ref: str) -> None:
                self.dataset_ref = dataset_ref

        class FakeLoadJobConfig:
            def __init__(self, schema: list[FakeSchemaField], write_disposition: str | None = None) -> None:
                self.schema = schema
                self.write_disposition = write_disposition

        class FakeClient:
            def __init__(self, project: str) -> None:
                self.project = project

            def create_dataset(self, dataset: FakeDataset, exists_ok: bool = False) -> None:
                return None

            def get_table(self, table_ref: str) -> FakeTable:
                exc = Exception("missing")
                setattr(exc, "code", 404)
                raise exc

            def create_table(self, table: FakeTable) -> FakeTable:
                created_tables.append(table)
                return table

            def load_table_from_json(self, rows: list[dict], table_ref: str, job_config: FakeLoadJobConfig):
                return types.SimpleNamespace(result=lambda: None)

        fake_bigquery = types.SimpleNamespace(
            Client=FakeClient,
            Dataset=FakeDataset,
            LoadJobConfig=FakeLoadJobConfig,
            SchemaField=FakeSchemaField,
            Table=FakeTable,
            TimePartitioning=FakeTimePartitioning,
            WriteDisposition=types.SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE"),
        )
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        fake_oauth2 = types.ModuleType("google.oauth2")
        fake_service_account = types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_file=lambda _: None))

        modules = {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
            "google.oauth2": fake_oauth2,
            "google.oauth2.service_account": fake_service_account,
        }
        with patch.dict(sys.modules, modules):
            push_to_bigquery("project", "dataset", {"listings": []})

        # Partitioning was removed (see TABLE_PARTITION_SPECS) to avoid DML
        # friction like partition-filter requirements and streaming-buffer
        # UPDATE/DELETE restrictions - tables are created as plain tables.
        listings_table = next(table for table in created_tables if table.table_ref.endswith(".listings"))
        self.assertIsNone(listings_table.time_partitioning)

    def _fake_bigquery_modules_for_skip_check_tests(self, get_table_calls: list, create_table_calls: list):
        class FakeSchemaField:
            def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", default_value_expression: str | None = None) -> None:
                self.name = name
                self.field_type = field_type
                self.mode = mode
                self.default_value_expression = default_value_expression

        class FakeTimePartitioning:
            def __init__(self, type_: str, field: str) -> None:
                self.type_ = type_
                self.field = field

        class FakeTable:
            def __init__(self, table_ref: str, schema: list[FakeSchemaField]) -> None:
                self.table_ref = table_ref
                self.schema = schema
                self.time_partitioning = None
                self.clustering_fields = None

        class FakeDataset:
            def __init__(self, dataset_ref: str) -> None:
                self.dataset_ref = dataset_ref

        class FakeLoadJobConfig:
            def __init__(self, schema: list[FakeSchemaField], write_disposition: str | None = None) -> None:
                self.schema = schema
                self.write_disposition = write_disposition

        class FakeClient:
            def __init__(self, project: str) -> None:
                self.project = project

            def create_dataset(self, dataset: FakeDataset, exists_ok: bool = False) -> None:
                return None

            def get_table(self, table_ref: str) -> FakeTable:
                get_table_calls.append(table_ref)
                exc = Exception("missing")
                setattr(exc, "code", 404)
                raise exc

            def create_table(self, table: FakeTable) -> FakeTable:
                create_table_calls.append(table.table_ref)
                return table

            def load_table_from_json(self, rows: list[dict], table_ref: str, job_config: FakeLoadJobConfig):
                return types.SimpleNamespace(result=lambda: None, errors=None, job_id="fake-job")

        fake_bigquery = types.SimpleNamespace(
            Client=FakeClient,
            Dataset=FakeDataset,
            LoadJobConfig=FakeLoadJobConfig,
            SchemaField=FakeSchemaField,
            Table=FakeTable,
            TimePartitioning=FakeTimePartitioning,
            WriteDisposition=types.SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE"),
        )
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        fake_oauth2 = types.ModuleType("google.oauth2")
        fake_service_account = types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_file=lambda _: None))

        return {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
            "google.oauth2": fake_oauth2,
            "google.oauth2.service_account": fake_service_account,
        }

    def test_skip_empty_table_checks_avoids_get_table_round_trip_for_empty_tables(self) -> None:
        get_table_calls: list = []
        create_table_calls: list = []
        modules = self._fake_bigquery_modules_for_skip_check_tests(get_table_calls, create_table_calls)

        with patch.dict(sys.modules, modules):
            push_to_bigquery(
                "project",
                "dataset",
                {"listings": [{"listing_id": "1"}], "businesses": [], "source_types": [], "us_zipcodes": []},
                skip_empty_table_checks=True,
            )

        self.assertTrue(any(ref.endswith(".listings") for ref in get_table_calls))
        for empty_table in ("businesses", "source_types", "us_zipcodes"):
            self.assertFalse(
                any(ref.endswith(f".{empty_table}") for ref in get_table_calls),
                f"{empty_table} should have been skipped but get_table was called for it",
            )
            self.assertFalse(
                any(ref.endswith(f".{empty_table}") for ref in create_table_calls),
                f"{empty_table} should have been skipped but create_table was called for it",
            )

    def test_skip_empty_table_checks_defaults_to_false_and_still_checks_empty_tables(self) -> None:
        get_table_calls: list = []
        create_table_calls: list = []
        modules = self._fake_bigquery_modules_for_skip_check_tests(get_table_calls, create_table_calls)

        with patch.dict(sys.modules, modules):
            push_to_bigquery(
                "project",
                "dataset",
                {"listings": [{"listing_id": "1"}], "businesses": [], "source_types": [], "us_zipcodes": []},
            )

        for empty_table in ("businesses", "source_types", "us_zipcodes"):
            self.assertTrue(
                any(ref.endswith(f".{empty_table}") for ref in get_table_calls),
                f"{empty_table} should still be checked by default (skip_empty_table_checks=False)",
            )
            self.assertTrue(
                any(ref.endswith(f".{empty_table}") for ref in create_table_calls),
                f"{empty_table} should still be created by default (skip_empty_table_checks=False)",
            )

    def test_push_uses_dataframe_bulk_loader_with_computed_hash(self) -> None:
        loaded_frames = []

        class FakeSchemaField:
            def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", default_value_expression: str | None = None) -> None:
                self.name = name
                self.field_type = field_type
                self.mode = mode
                self.default_value_expression = default_value_expression

        class FakeTable:
            def __init__(self, table_ref: str, schema: list[FakeSchemaField]) -> None:
                self.table_ref = table_ref
                self.schema = schema
                self.time_partitioning = None
                self.clustering_fields = None

        class FakeDataset:
            def __init__(self, dataset_ref: str) -> None:
                self.dataset_ref = dataset_ref

        class FakeLoadJobConfig:
            def __init__(self, schema: list[FakeSchemaField], write_disposition: str | None = None) -> None:
                self.schema = schema
                self.write_disposition = write_disposition

        class FakeLoadJob:
            errors = None
            job_id = "job-1"

            def result(self) -> None:
                return None

        class FakeClient:
            def __init__(self, project: str) -> None:
                self.project = project

            def create_dataset(self, dataset: FakeDataset, exists_ok: bool = False) -> None:
                return None

            def get_table(self, table_ref: str) -> FakeTable:
                exc = Exception("missing")
                setattr(exc, "code", 404)
                raise exc

            def create_table(self, table: FakeTable) -> FakeTable:
                return table

            def load_table_from_dataframe(self, frame, table_ref: str, job_config: FakeLoadJobConfig):
                loaded_frames.append((table_ref, frame.copy()))
                return FakeLoadJob()

            def load_table_from_json(self, rows: list[dict], table_ref: str, job_config: FakeLoadJobConfig):
                raise AssertionError("JSON loader should not be used when dataframe loading is available")

        fake_bigquery = types.SimpleNamespace(
            Client=FakeClient,
            Dataset=FakeDataset,
            LoadJobConfig=FakeLoadJobConfig,
            SchemaField=FakeSchemaField,
            Table=FakeTable,
            TimePartitioning=lambda type_, field: types.SimpleNamespace(type_=type_, field=field),
            WriteDisposition=types.SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE"),
        )
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        fake_oauth2 = types.ModuleType("google.oauth2")
        fake_service_account = types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_file=lambda _: None))

        modules = {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
            "google.oauth2": fake_oauth2,
            "google.oauth2.service_account": fake_service_account,
        }
        with patch.dict(sys.modules, modules):
            push_to_bigquery("project", "dataset", {"businesses": [{
                "business_id": "b1",
                "name": "Store",
                "slug": "store",
                "status": "active",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }]})

        self.assertEqual(len(loaded_frames), 1)
        table_ref, frame = loaded_frames[0]
        self.assertTrue(table_ref.endswith(".businesses"))
        self.assertIn("content_hash", frame.columns)
        self.assertTrue(frame.iloc[0]["content_hash"])

    def test_push_uses_json_loader_for_tables_with_json_columns(self) -> None:
        loaded_json_rows = []

        class FakeSchemaField:
            def __init__(self, name: str, field_type: str, mode: str = "NULLABLE", default_value_expression: str | None = None) -> None:
                self.name = name
                self.field_type = field_type
                self.mode = mode
                self.default_value_expression = default_value_expression

        class FakeTable:
            def __init__(self, table_ref: str, schema: list[FakeSchemaField]) -> None:
                self.table_ref = table_ref
                self.schema = schema
                self.time_partitioning = None
                self.clustering_fields = None

        class FakeDataset:
            def __init__(self, dataset_ref: str) -> None:
                self.dataset_ref = dataset_ref

        class FakeLoadJobConfig:
            def __init__(self, schema: list[FakeSchemaField], write_disposition: str | None = None) -> None:
                self.schema = schema
                self.write_disposition = write_disposition

        class FakeLoadJob:
            errors = None
            job_id = "job-json"

            def result(self) -> None:
                return None

        class FakeClient:
            def __init__(self, project: str) -> None:
                self.project = project

            def create_dataset(self, dataset: FakeDataset, exists_ok: bool = False) -> None:
                return None

            def get_table(self, table_ref: str) -> FakeTable:
                exc = Exception("missing")
                setattr(exc, "code", 404)
                raise exc

            def create_table(self, table: FakeTable) -> FakeTable:
                return table

            def load_table_from_dataframe(self, frame, table_ref: str, job_config: FakeLoadJobConfig):
                raise AssertionError("DataFrame loader should not be used for JSON-column tables")

            def load_table_from_json(self, rows: list[dict], table_ref: str, job_config: FakeLoadJobConfig):
                loaded_json_rows.append((table_ref, rows))
                return FakeLoadJob()

        fake_bigquery = types.SimpleNamespace(
            Client=FakeClient,
            Dataset=FakeDataset,
            LoadJobConfig=FakeLoadJobConfig,
            SchemaField=FakeSchemaField,
            Table=FakeTable,
            TimePartitioning=lambda type_, field: types.SimpleNamespace(type_=type_, field=field),
            WriteDisposition=types.SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE"),
        )
        fake_google = types.ModuleType("google")
        fake_cloud = types.ModuleType("google.cloud")
        fake_oauth2 = types.ModuleType("google.oauth2")
        fake_service_account = types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_file=lambda _: None))

        modules = {
            "google": fake_google,
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
            "google.oauth2": fake_oauth2,
            "google.oauth2.service_account": fake_service_account,
        }
        with patch.dict(sys.modules, modules):
            push_to_bigquery("project", "dataset", {"workflow_templates": [{
                "workflow_template_id": "t1",
                "business_id": "b1",
                "name": "Template",
                "components": "{}",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            }]})

        self.assertEqual(len(loaded_json_rows), 1)
        self.assertTrue(loaded_json_rows[0][0].endswith(".workflow_templates"))
        self.assertTrue(loaded_json_rows[0][1][0]["content_hash"])


class PandasIsLazyTests(unittest.TestCase):
    """pandas/pyarrow power the vectorized hashing/load path only - the module
    (and workflow_server.py, which imports from it at module scope) must
    still import cleanly without them, same as this codebase's existing
    lazy `from google.cloud import bigquery` convention."""

    def test_missing_pandas_raises_friendly_error_instead_of_import_crash(self) -> None:
        from whitespace_tool import warehouse_bigquery

        with patch.dict(sys.modules, {"pandas": None}):
            with self.assertRaisesRegex(RuntimeError, "Install pandas and pyarrow"):
                warehouse_bigquery.rows_to_dataframe("businesses", [{"business_id": "b1"}])

    def test_workflow_server_module_has_no_top_level_pandas_dependency(self) -> None:
        import ast

        source_path = Path(__file__).resolve().parent.parent / "whitespace_tool" / "warehouse_bigquery.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        top_level_imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        imported_names = {alias.name for node in top_level_imports for alias in node.names}
        self.assertNotIn("pandas", imported_names)


if __name__ == "__main__":
    unittest.main()


def test_unmapped_source_columns_are_preserved_not_dropped():
    # Every parse can present a different column list, so the fixed listings
    # schema can never cover them all. Before custom_fields existed, anything
    # the mapper did not consume was silently dropped at the bronze write:
    # _listing_row() builds an explicit dict from LocationRecord's typed
    # attributes, and rows_to_dataframe() reindexes onto the static schema.
    # No error, no warning - the value simply was not there.
    from whitespace_tool.warehouse_bigquery import (
        build_table_rows, dataframe_to_records, rows_to_hashed_dataframe)
    from whitespace_tool.normalization import normalize_location
    import json

    mapper = {
        "brand": "Acme", "business_id": "b1", "source_name": "s.csv", "source_type": "csv",
        "fields": {"name": "Name", "address": "Addr", "city": "City",
                   "state": "State", "postal_code": "Zip", "country": "Country"},
    }
    row = {"Name": "Store 1", "Addr": "1 Main", "City": "Austin", "State": "TX",
           "Zip": "78701", "Country": "United States",
           "LoyaltyTier": "gold", "DriveThru": "yes", "Blank": "", "Missing": None}
    record = normalize_location(row, mapper, "s.csv", 0)

    # Mapped columns are not duplicated into extras; empty values are skipped.
    assert record.extras == {"LoyaltyTier": "gold", "DriveThru": "yes"}

    listing = build_table_rows([record], {})["listings"][0]
    pushed = dataframe_to_records(rows_to_hashed_dataframe("listings", [listing]))[0]
    assert json.loads(pushed["custom_fields"]) == {"DriveThru": "yes", "LoyaltyTier": "gold"}


def test_custom_fields_does_not_move_listings_off_the_dataframe_load_path():
    # custom_fields is deliberately STRING-holding-JSON, not the BigQuery
    # JSON type: a JSON column flips table_has_json_fields("listings") True,
    # which forces every save off load_table_from_dataframe and onto
    # load_table_from_json - a real regression on the hottest write path.
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, table_has_json_fields

    column = next(f for f in TABLE_SCHEMAS["listings"] if f["name"] == "custom_fields")
    assert column["type"] == "STRING"
    assert column["mode"] == "NULLABLE"
    assert table_has_json_fields("listings") is False


def test_custom_fields_is_excluded_from_the_listing_content_hash():
    # Including it would change every previously-stored row's content_hash,
    # so the next save would treat the entire warehouse as new rows.
    from whitespace_tool.warehouse_bigquery import (
        CONTENT_HASH_FIELDS, table_hash_columns, rows_to_hashed_dataframe, dataframe_to_records)

    assert "custom_fields" not in CONTENT_HASH_FIELDS
    assert "custom_fields" not in table_hash_columns("listings")
    base = {"business_id": "b1", "name": "S", "address": "1 Main",
            "city_name": "Austin", "state_code": "TX", "zip_code": "78701"}
    without = dataframe_to_records(rows_to_hashed_dataframe("listings", [dict(base)]))[0]["content_hash"]
    with_extras = dataframe_to_records(
        rows_to_hashed_dataframe("listings", [{**base, "custom_fields": '{"a":1}'}]))[0]["content_hash"]
    assert without == with_extras


def test_extras_payload_is_bounded_and_says_when_it_truncated():
    # A pathological source (hundreds of wide columns) must not blow the
    # 512MB budget one row at a time - but truncation must be visible in the
    # payload, never silent.
    from whitespace_tool.normalization import _collect_extras, EXTRAS_MAX_KEYS

    wide = {f"col_{i}": f"value_{i}" for i in range(EXTRAS_MAX_KEYS + 40)}
    bounded = _collect_extras(wide, {})
    assert len(bounded) <= EXTRAS_MAX_KEYS + 1
    assert bounded["__truncated"] == "key limit reached"

    huge = {"a": "x" * 20000, "b": "y" * 20000}
    trimmed = _collect_extras(huge, {})
    assert trimmed["__truncated"] == "size limit reached"


def test_new_schema_columns_reach_already_deployed_tables():
    # custom_fields only helps if it actually lands on the live table. Both
    # reconcile passes append any TABLE_SCHEMAS column the deployed table
    # lacks - this is the mechanism that was MISSING for error_listings,
    # which is why has_ai_suggestion broke the quality tab.
    import inspect
    from whitespace_tool import warehouse_bigquery
    import whitespace_tool.workflow_server as ws

    push = inspect.getsource(warehouse_bigquery.push_to_bigquery)
    assert "if field.name not in existing_names" in push
    assert 'client.update_table(existing, ["schema"])' in push
    for ensure in (ws._ensure_listings_table, ws._ensure_error_listings_table):
        assert 'client.update_table(existing, ["schema"])' in inspect.getsource(ensure), ensure.__name__


def test_custom_fields_flows_bronze_to_silver_to_gold_to_mirror():
    # A custom field that stops at bronze is invisible to reporting, quality,
    # the map and every export - the warehouse stored it but nothing
    # downstream could see it. Each hop is an explicit column list, so each
    # one has to name it.
    import inspect
    import whitespace_tool.workflow_server as ws
    from whitespace_tool.sqlite_cache import MIRROR_LOCATION_COLUMNS

    silver = inspect.getsource(ws.build_silver_layer)
    # Silver staging: listings_enriched/listings_invalid are SELECT * off it.
    assert "l.custom_fields," in silver
    assert "SELECT * FROM `{staging_table}`" in silver

    gold = inspect.getsource(ws.build_gold_layer)
    assert "l.custom_fields," in gold
    assert "CREATE OR REPLACE VIEW `{location_view}`" in gold

    # Gold -> SQLite mirror.
    sync = inspect.getsource(ws.sync_gold_mirror)
    assert "median_age, custom_fields" in sync
    assert "custom_fields" in MIRROR_LOCATION_COLUMNS


def test_mirror_location_columns_have_a_top_up_migration():
    # mirror_reporting_locations had no ALTER pass (unlike mirror_businesses),
    # so an existing .cache/whitespace_cache.db predating a newly added column
    # would fail replace_gold_mirror()'s explicit-column INSERT with
    # "no such column" on the first sync after an upgrade.
    import inspect
    from whitespace_tool import sqlite_cache

    source = inspect.getsource(sqlite_cache.init_sqlite_cache)
    assert "PRAGMA table_info(mirror_reporting_locations)" in source
    assert "ALTER TABLE mirror_reporting_locations ADD COLUMN" in source


def test_removing_a_custom_field_archives_it_instead_of_deleting():
    # Listings already saved carry that field's values inside
    # listings.custom_fields. A hard DELETE of the catalog row would strand
    # them with no label, type or provenance to read them by.
    import inspect
    import whitespace_tool.workflow_server as ws
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

    catalog_columns = {f["name"] for f in TABLE_SCHEMAS["field_catalogs"]}
    assert {"is_archived", "archived_at"} <= catalog_columns

    delete = inspect.getsource(ws.delete_custom_field)
    assert "SET is_archived = TRUE" in delete
    assert "DELETE FROM" not in delete
    assert '"archived": True' in delete

    # Archived definitions must not reach the mapper or any field picker.
    catalog = inspect.getsource(ws.field_catalog)
    assert "WHERE is_archived IS NOT TRUE" in catalog


def test_recreating_an_archived_custom_field_revives_it():
    # Re-adding a previously archived slug must restore that definition, not
    # insert a duplicate slug alongside it - the archived row already
    # describes the values sitting in listings.custom_fields.
    import inspect
    import whitespace_tool.workflow_server as ws

    create = inspect.getsource(ws.create_custom_field)
    assert "SET is_archived = FALSE" in create
    assert "num_dml_affected_rows" in create
    # And the column that physically stores custom values must exist before
    # the catalog advertises somewhere for the data to go.
    assert "_ensure_listings_table(client, project_id, dataset_id)" in create


def test_edited_records_round_trip_unmapped_columns():
    # The review edit form is built from Object.entries(rawObj) - every raw
    # key, not just mapped ones - so an edit resubmits unmapped columns
    # rather than silently dropping them. reprocess then re-derives extras
    # from that full record via normalize_location().
    from pathlib import Path

    review_js = (Path(__file__).resolve().parents[1] / "ui" / "js" / "review.js").read_text()
    assert "Object.entries(rawObj).filter(" in review_js
    assert "updatedRaw[rawKey] = input.value;" in review_js


def test_mapping_confidence_is_mirrored_to_bigquery_and_survives_a_clear():
    # SQLite is the fast read path, but on Render it sits on ephemeral disk -
    # a restart would erase everything the app had learned about which source
    # column maps to which field.
    import inspect
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, _clear_dataset_tables_with_client
    import whitespace_tool.workflow_server as ws

    assert "field_mapping_confidence" in TABLE_SCHEMAS
    columns = {f["name"] for f in TABLE_SCHEMAS["field_mapping_confidence"]}
    assert {"target_key", "source_field_normalized", "score", "sample_count"} <= columns

    # The learning describes HOW to map, not what was mapped, so a data clear
    # must not cost it.
    clear_source = inspect.getsource(_clear_dataset_tables_with_client)
    assert '"field_mapping_confidence"' in clear_source

    sync = inspect.getsource(ws.sync_mapping_confidence_to_warehouse)
    # Full replace keeps BigQuery exactly in step rather than accumulating
    # superseded scores.
    assert 'write_disposition="WRITE_TRUNCATE"' in sync

    restore = inspect.getsource(ws.restore_mapping_confidence_from_warehouse)
    assert "INSERT OR REPLACE INTO field_mapping_confidence" in restore
    # A missing table is an empty restore, not a crash.
    assert 'return {"restored": 0}' in restore

    # Restore is lazy and runs at most once per process.
    once = inspect.getsource(ws._restore_mapping_confidence_once)
    assert "if _CONFIDENCE_RESTORED:" in once
    assert "if get_mapping_confidence():" in once  # cache survived -> skip


def test_sample_load_records_phase_timings():
    # The ZIP path logs per-phase durations; the sample load had event logs
    # but no timings, so "why does it stick" could only be answered by
    # staring at it.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.load_sample_dataset)
    assert "phase_started = perf_counter()" in source
    assert "sample_brand_loaded brand=%s rows=%d elapsed_s=%.2f" in source
    assert "sample_load_timing total_s=%.2f brands=%d skipped=%d slowest=%s" in source
    # Timings are returned to the caller, not only logged.
    assert 'summary["timing"] = {"total_seconds": total_elapsed, "per_brand_seconds": brand_timings}' in source


def test_confidence_restore_never_blocks_the_mapping_request():
    # This is called from the auto-map path, which a user is waiting on. Doing
    # the BigQuery round trip inline stalled mapping and hung the test suite
    # (3s -> >500s). The scores are an optimisation: the current request
    # proceeds without them and the next one benefits.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws._restore_mapping_confidence_once)
    assert 'threading.Thread(target=restore, name="mapping-confidence-restore", daemon=True).start()' in source
    # The network call must sit inside the thread body, not at call level.
    before_thread = source.split("threading.Thread(", 1)[0]
    assert "restore_mapping_confidence_from_warehouse()" not in before_thread.split("def restore()", 1)[0]


def test_confidence_sync_is_also_backgrounded():
    import inspect
    import whitespace_tool.workflow_server as ws

    # Recorded on the save path, pushed to BigQuery off-thread.
    source = inspect.getsource(ws.save_mapper)
    assert 'name="mapping-confidence-sync", daemon=True).start()' in source
