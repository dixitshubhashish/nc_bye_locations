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

    def create_dataset(self, dataset: object, exists_ok: bool = False) -> None:
        return None

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()

    def get_table(self, table_ref: str) -> SimpleNamespace:
        return SimpleNamespace(num_rows=10)


class GoldLayerTests(unittest.TestCase):
    def test_build_gold_layer_creates_all_five_views_over_silver(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    result = workflow_server.build_gold_layer()

        sql = "\n".join(client.queries)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_zip_brand_activity`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_state_summary`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_city_summary`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_brand_summary`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_listing_quality_summary`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.gold.vw_geo_reference`", sql)
        self.assertEqual(result["gold_dataset"], "project.gold")
        self.assertEqual(len(result["views"]), 6)

    def test_foundation_view_joins_silver_zip_reference_not_bronze(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_gold_layer()

        zip_brand_sql = next(q for q in client.queries if "vw_zip_brand_activity" in q)
        self.assertIn("FROM `project.silver.zip_reference`", zip_brand_sql)
        self.assertNotIn("bronze.us_zipcodes", zip_brand_sql)
        self.assertIn("LEFT JOIN `project.silver.listings_enriched`", zip_brand_sql)

        geo_sql = next(q for q in client.queries if "vw_geo_reference" in q)
        self.assertIn("FROM `project.silver.zip_reference`", geo_sql)

    def test_zip_brand_activity_groups_by_zip_and_brand(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_gold_layer()

        zip_brand_sql = next(q for q in client.queries if "CREATE OR REPLACE VIEW `project.gold.vw_zip_brand_activity`" in q)
        self.assertIn("GROUP BY z.zip_code", zip_brand_sql)
        self.assertIn("l.brand_name", zip_brand_sql)

    def test_brand_summary_excludes_null_brand_and_zero_location_rows(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_gold_layer()

        brand_sql = next(q for q in client.queries if "CREATE OR REPLACE VIEW `project.gold.vw_brand_summary`" in q)
        self.assertIn("WHERE brand_name IS NOT NULL AND location_count > 0", brand_sql)


if __name__ == "__main__":
    unittest.main()
