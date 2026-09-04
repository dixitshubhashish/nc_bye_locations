from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    def result(self) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.created_datasets: list[str] = []

    def create_dataset(self, dataset: object, exists_ok: bool = False) -> None:
        self.created_datasets.append(str(getattr(dataset, "dataset_ref", dataset)))

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()

    def get_table(self, table_ref: str) -> SimpleNamespace:
        return SimpleNamespace(num_rows=42)


class SilverEnrichmentTests(unittest.TestCase):
    def test_build_silver_layer_creates_enriched_table_and_views(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    result = workflow_server.build_silver_layer()

        sql = "\n".join(client.queries)
        self.assertEqual(result["rows"], 42)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.listings_enriched`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.silver.vw_brand_location_top10`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.silver.vw_brand_zip_income`", sql)
        self.assertIn("REGEXP_EXTRACT(CAST(zip_code AS STRING)", sql)
        self.assertIn("United States", sql)
        self.assertIn("median_household_income", sql)
        self.assertIn("z.income_per_capita", sql)
        self.assertIn("city_geos AS", sql)
        self.assertIn("COALESCE(l.latitude, z.latitude, cg.latitude) AS latitude", sql)
        self.assertIn("COALESCE(l.normalized_city_name, LOWER(TRIM(z.city_name))) = cg.normalized_city_name", sql)
        self.assertIn("coordinate_source", sql)
        self.assertIn("coordinate_confidence", sql)
        self.assertIn("geocode_query", sql)


if __name__ == "__main__":
    unittest.main()
