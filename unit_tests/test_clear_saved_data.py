from __future__ import annotations

import unittest
from types import SimpleNamespace

from whitespace_tool.warehouse_bigquery import _clear_dataset_tables_with_client


class _FakeJob:
    def result(self) -> None:
        return None


class _FakeClient:
    def __init__(self, table_ids: list[str]) -> None:
        self.table_ids = table_ids
        self.queries: list[str] = []

    def list_tables(self, dataset_ref: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(table_id=table_id, reference=SimpleNamespace(table_id=table_id))
            for table_id in self.table_ids
        ]

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()


class ClearSavedDataTests(unittest.TestCase):
    def test_soft_deletes_known_tables_and_truncates_other_clearable_tables(self) -> None:
        client = _FakeClient([
            "us_zipcodes",
            "field_catalogs",
            "source_types",
            "workflow_templates",
            "businesses",
            "listings",
            "error_listings",
            "analysis_runs",
        ])

        result = _clear_dataset_tables_with_client(client, "project.dataset")

        self.assertEqual(result["soft_deleted_tables"], ["businesses", "listings", "error_listings"])
        self.assertEqual(result["truncated_tables"], ["analysis_runs"])
        self.assertTrue(any("UPDATE `project.dataset.businesses` SET is_deleted = TRUE" in query for query in client.queries))
        self.assertTrue(any("UPDATE `project.dataset.listings` SET is_deleted = TRUE" in query for query in client.queries))
        self.assertTrue(any("UPDATE `project.dataset.error_listings` SET is_deleted = TRUE" in query for query in client.queries))
        self.assertIn("TRUNCATE TABLE `project.dataset.analysis_runs`", client.queries)
        self.assertFalse(any("DROP TABLE" in query.upper() for query in client.queries))
        self.assertFalse(any("TRUNCATE TABLE `project.dataset.workflow_templates`" in query for query in client.queries))


if __name__ == "__main__":
    unittest.main()
