from __future__ import annotations

import sys
import types
import unittest
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


if __name__ == "__main__":
    unittest.main()
