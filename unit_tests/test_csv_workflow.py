from __future__ import annotations

import unittest

from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.models import LocationRecord
from whitespace_tool.normalization import clean_zip, normalize_location, optional_date, optional_float, optional_int
from whitespace_tool.source_adapters import csv_source
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows
from whitespace_tool.workflow_server import REQUIRED_MAPPER_FIELDS, validate_mapper


VALID_MAPPER = {
    "brand": "Example Pizza",
    "business_id": "business-123",
    "source_type": "csv",
    "source_type_id": "source-csv",
    "source_name": "example_csv",
    "fields": {
        "location_id": "store_id",
        "name": "store_name",
        "address": "street_address",
        "city": "city",
        "state": "state",
        "postal_code": "zip_code",
        "latitude": "latitude",
        "longitude": "longitude",
        "opening_date": "opened_on",
        "seating_capacity": "seats",
    },
}

VALID_ROW = {
    "store_id": "store-001",
    "store_name": "Example Pizza Downtown",
    "street_address": "1 Main Street",
    "city": "Raleigh",
    "state": "nc",
    "zip_code": "27601-1234",
    "latitude": "35.7796",
    "longitude": "-78.6382",
    "opened_on": "04/12/2024",
    "seats": "42",
}


class CsvWorkflowTests(unittest.TestCase):
    def test_csv_preview_reads_headers_and_rows(self) -> None:
        content = b"store_id,store_name,zip_code\n1,Main Store,27601\n"
        result = csv_source.preview(content)
        self.assertEqual(result["fields"], ["store_id", "store_name", "zip_code"])
        self.assertEqual(result["rows"], [{"store_id": "1", "store_name": "Main Store", "zip_code": "27601"}])

    def test_csv_preview_removes_blank_headers(self) -> None:
        result = csv_source.preview(b"name,,zip_code\nStore,,27601\n")
        self.assertNotIn(None, result["fields"])
        self.assertNotIn("", result["fields"])

    def test_valid_row_normalizes_to_standard_values(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.postal_code, "27601")
        self.assertEqual(location.state, "NC")
        self.assertEqual(location.opening_date, "2024-04-12")
        self.assertEqual(location.seating_capacity, 42)

    def test_zip_and_scalar_normalization(self) -> None:
        self.assertEqual(clean_zip(" 12-345-6789 "), "12345")
        self.assertEqual(clean_zip("27601"), "27601")
        self.assertEqual(optional_float("35.5"), 35.5)
        self.assertIsNone(optional_float("not-a-number"))
        self.assertEqual(optional_int("42.0"), 42)
        self.assertIsNone(optional_int("bad"))
        self.assertEqual(optional_date("2024-04-12"), "2024-04-12")
        self.assertIsNone(optional_date("0"))

    def test_invalid_optional_values_are_rejected(self) -> None:
        row = {**VALID_ROW, "opened_on": "0", "seats": "unknown"}
        errors = validate_source_row(row, VALID_MAPPER)
        self.assertEqual({error["field"] for error in errors}, {"opening_date", "seating_capacity"})

    def test_missing_required_mapping_is_reported(self) -> None:
        mapper = {**VALID_MAPPER, "fields": {"name": "store_name"}}
        errors = validate_mapper(mapper, list(VALID_ROW), [VALID_ROW])
        self.assertEqual(set(error.removeprefix("fields.") for error in errors if error.startswith("fields.")), REQUIRED_MAPPER_FIELDS - {"name"})

    def test_unknown_source_mapping_is_reported(self) -> None:
        mapper = {**VALID_MAPPER, "fields": {**VALID_MAPPER["fields"], "city": "does_not_exist"}}
        errors = validate_mapper(mapper, list(VALID_ROW), [VALID_ROW])
        self.assertTrue(any("unknown source fields" in error for error in errors))

    def test_missing_required_source_value_is_not_digestible(self) -> None:
        row = {**VALID_ROW, "street_address": ""}
        location = normalize_location(row, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.address, "")
        self.assertTrue(any(not getattr(location, field) for field in ("address",)))

    def test_normalized_validation_checks_required_and_types(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        errors = validate_normalized_location(location, load_field_registry())
        self.assertEqual(errors, [])

    def test_bronze_listing_payload_contains_generated_id_and_foreign_keys(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        rows = build_table_rows([location], {})
        listing = rows["listings"][0]
        self.assertTrue(listing["listing_id"])
        self.assertEqual(listing["business_id"], "business-123")
        self.assertEqual(listing["source_type_id"], "source-csv")
        self.assertEqual(set(rows), {"us_zipcodes", "businesses", "listings", "workflow_templates", "source_types", "error_listings"})

    def test_standard_and_optional_fields_keep_expected_modes(self) -> None:
        required = {field["name"] for field in TABLE_SCHEMAS["listings"] if field["mode"] == "REQUIRED"}
        self.assertTrue({"business_id", "source_type_id", "name", "address", "city_name", "state_code", "zip_code"} <= required)
        self.assertEqual(TABLE_SCHEMAS["error_listings"][0]["name"], "event_id")


if __name__ == "__main__":
    unittest.main()
