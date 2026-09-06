"""Unit tests for silver layer ETL enrichment transformations.

Tests silver table creation, zip code reference join, coordinate resolution, and invalid record splitting.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    """Mock BigQuery query job object."""

    def result(self) -> None:
        return None


class _FakeClient:
    """Mock BigQuery client tracking query execution and dataset creation."""

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
    """Test suite for validating silver layer ETL pipeline logic."""

    def test_build_silver_layer_creates_enriched_table_and_views(self) -> None:
        """Verify build_silver_layer constructs listings_enriched table and top/zip views."""
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
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
        self.assertIn("state_code", sql)
        self.assertIn("state_name", sql)

    def test_build_silver_layer_creates_zip_reference_and_invalid_split(self) -> None:
        """Verify build_silver_layer creates zip reference table and routes invalid listings with rejection reasons."""
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_silver_layer()

        sql = "\n".join(client.queries)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.zip_reference`", sql)
        self.assertIn("FROM `project.bronze.us_zipcodes`", sql)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver._listings_staging`", sql)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.listings_invalid`", sql)
        self.assertIn("rejection_reason", sql)
        self.assertIn("latitude IS NOT NULL AND longitude IS NOT NULL", sql)
        self.assertIn("DROP TABLE IF EXISTS `project.silver._listings_staging`", sql)


if __name__ == "__main__":
    unittest.main()
