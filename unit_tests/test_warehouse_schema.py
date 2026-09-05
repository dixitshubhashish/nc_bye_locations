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

    def test_partition_creation_does_not_require_time_partition_type_enum(self) -> None:
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

        listings_table = next(table for table in created_tables if table.table_ref.endswith(".listings"))
        self.assertEqual(listings_table.time_partitioning.type_, "DAY")
        self.assertEqual(listings_table.time_partitioning.field, "first_observed_at")

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
