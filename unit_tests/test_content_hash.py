from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from whitespace_tool.models import LocationRecord, ZipDemographics
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows, content_hash, rows_to_hashed_dataframe, table_content_hash
from whitespace_tool.workflow_server import _dedupe_listings_against_bronze


def _fake_bigquery_module() -> dict[str, types.ModuleType]:
    class FakeQueryJobConfig:
        def __init__(self, query_parameters=None) -> None:
            self.query_parameters = query_parameters

    fake_bigquery = types.SimpleNamespace(
        QueryJobConfig=FakeQueryJobConfig,
        ArrayQueryParameter=lambda name, type_, value: (name, type_, value),
        ScalarQueryParameter=lambda name, type_, value: (name, type_, value),
    )
    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    return {
        "google": fake_google,
        "google.cloud": fake_cloud,
        "google.cloud.bigquery": fake_bigquery,
    }


def _location(**overrides) -> LocationRecord:
    base = dict(
        brand="Example Pizza",
        business_id="business-123",
        source_type_id="source-csv",
        location_id="loc-1",
        name="Example Pizza Elm St",
        address="123 Elm St",
        city="Austin",
        state="TX",
        postal_code="78701",
        latitude=30.27,
        longitude=-97.74,
        source="csv",
        observed_at="2026-01-01T00:00:00+00:00",
        raw={},
    )
    base.update(overrides)
    return LocationRecord(**base)


class ContentHashTests(unittest.TestCase):
    def test_listings_schema_has_content_hash_column(self) -> None:
        fields = {field["name"] for field in TABLE_SCHEMAS["listings"]}
        self.assertIn("content_hash", fields)

    def test_all_managed_tables_have_content_hash_column(self) -> None:
        for table_name, schema in TABLE_SCHEMAS.items():
            with self.subTest(table_name=table_name):
                self.assertIn("content_hash", {field["name"] for field in schema})

    def test_build_table_rows_populates_content_hash(self) -> None:
        rows = build_table_rows([_location()], {})
        self.assertEqual(len(rows["listings"]), 1)
        self.assertTrue(rows["listings"][0]["content_hash"])

    def test_build_table_rows_populates_zip_content_hash(self) -> None:
        rows = build_table_rows([], {
            "78701": ZipDemographics(
                zip_code="78701",
                population=1000,
                median_household_income=75000,
                median_age=34,
                source="public_bigquery",
                city="Austin",
                county="Travis",
                state_code="TX",
            )
        })
        self.assertEqual(len(rows["us_zipcodes"]), 1)
        self.assertTrue(rows["us_zipcodes"][0]["content_hash"])

    def test_same_content_different_id_and_observed_at_hashes_identically(self) -> None:
        first = build_table_rows([_location(location_id="loc-1", observed_at="2026-01-01T00:00:00+00:00")], {})["listings"][0]
        second = build_table_rows([_location(location_id="loc-2", observed_at="2026-06-01T00:00:00+00:00")], {})["listings"][0]
        # listing_id is always a fresh uuid, and observed_at differs, but the
        # actual content (name/address/etc.) is identical -> same hash.
        self.assertNotEqual(first["listing_id"], second["listing_id"])
        self.assertEqual(first["content_hash"], second["content_hash"])

    def test_different_address_hashes_differently(self) -> None:
        first = build_table_rows([_location(address="123 Elm St")], {})["listings"][0]
        second = build_table_rows([_location(address="456 Oak Ave")], {})["listings"][0]
        self.assertNotEqual(first["content_hash"], second["content_hash"])

    def test_content_hash_is_deterministic(self) -> None:
        row = {"business_id": "b1", "name": "Store", "address": "1 Main St", "city_name": "Austin"}
        self.assertEqual(content_hash(row), content_hash(dict(row)))

    def test_table_content_hash_uses_all_managed_non_hash_columns(self) -> None:
        base = {"business_id": "b1", "name": "Store", "slug": "store", "status": "active"}
        changed = dict(base, status="paused")
        self.assertNotEqual(table_content_hash("businesses", base), table_content_hash("businesses", changed))

    def test_rows_to_hashed_dataframe_is_schema_ordered_and_vectorized(self) -> None:
        frame = rows_to_hashed_dataframe("businesses", [{
            "business_id": "b1",
            "name": "Store",
            "slug": "store",
            "status": "active",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        self.assertEqual(list(frame.columns), [field["name"] for field in TABLE_SCHEMAS["businesses"]])
        self.assertTrue(frame.iloc[0]["content_hash"])


class DedupeAgainstBronzeTests(unittest.TestCase):
    def test_no_hashes_returns_rows_unchanged(self) -> None:
        rows, skipped = _dedupe_listings_against_bronze(object(), "project", "dataset", [])
        self.assertEqual(rows, [])
        self.assertEqual(skipped, 0)

    def test_matching_content_hash_is_dropped_and_last_observed_at_bumped(self) -> None:
        class FakeJob:
            def __init__(self, rows):
                self._rows = rows

            def result(self):
                return self._rows

        class FakeClient:
            def __init__(self):
                self.update_queries: list[str] = []

            def query(self, sql, job_config=None):
                if sql.strip().startswith("SELECT"):
                    return FakeJob([{"listing_id": "existing-1", "business_id": "b1", "content_hash": "hash-1", "last_observed_at": "2026-01-01T00:00:00+00:00"}])
                self.update_queries.append(sql)
                return FakeJob([])

        new_row = {"business_id": "b1", "content_hash": "hash-1", "last_observed_at": "2026-06-01T00:00:00+00:00"}
        client = FakeClient()
        with patch.dict(sys.modules, _fake_bigquery_module()):
            rows, skipped = _dedupe_listings_against_bronze(client, "project", "dataset", [new_row])
        self.assertEqual(rows, [])
        self.assertEqual(skipped, 1)
        self.assertEqual(len(client.update_queries), 1)
        self.assertIn("UPDATE", client.update_queries[0])

    def test_new_content_hash_is_kept_for_insert(self) -> None:
        class FakeJob:
            def __init__(self, rows):
                self._rows = rows

            def result(self):
                return self._rows

        class FakeClient:
            def query(self, sql, job_config=None):
                return FakeJob([])  # nothing matches in bronze

        new_row = {"business_id": "b1", "content_hash": "hash-new", "last_observed_at": "2026-06-01T00:00:00+00:00"}
        with patch.dict(sys.modules, _fake_bigquery_module()):
            rows, skipped = _dedupe_listings_against_bronze(FakeClient(), "project", "dataset", [new_row])
        self.assertEqual(rows, [new_row])
        self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main()
