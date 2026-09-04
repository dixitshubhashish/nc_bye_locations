from __future__ import annotations

import unittest

from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.models import LocationRecord
from whitespace_tool.normalization import clean_zip, normalize_location, optional_date, optional_float, optional_int
from whitespace_tool.source_adapters import csv_source
from whitespace_tool.source_adapters import json_source
from whitespace_tool.source_adapters import xml_source
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

    def test_csv_preview_returns_all_rows_for_processing(self) -> None:
        content = "store_id,store_name,zip_code\n" + "\n".join(f"{index},Store {index},27601" for index in range(30))
        result = csv_source.preview(content.encode("utf-8"))
        self.assertEqual(result["record_count"], 30)
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(len(result["preview_rows"]), 25)

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

    def test_field_catalogs_are_business_aware_and_plural(self) -> None:
        self.assertIn("field_catalogs", TABLE_SCHEMAS)
        self.assertNotIn("field_catalog", TABLE_SCHEMAS)
        field_names = {field["name"] for field in TABLE_SCHEMAS["field_catalogs"]}
        self.assertIn("business_id", field_names)

    def test_json_preview_offers_record_layers_through_depth_three(self) -> None:
        content = b'{"level1": {"level2": {"stores": [{"name": "Main", "details": {"location": {"coordinates": {"latitude": 35.7, "longitude": -78.6}}}}]}, "too_deep": {"level3": {"level4": [{"name": "Hidden"}]}}}}'
        result = json_source.preview(content)
        self.assertIn("level1.level2.stores", result["record_paths"])
        self.assertNotIn("level1.too_deep.level3.level4", result["record_paths"])
        self.assertIn("details.location.coordinates.latitude", result["fields"])

    def test_json_preview_returns_all_rows_for_processing(self) -> None:
        content = ('{"stores": [' + ",".join(f'{{"id": "{index}", "name": "Store {index}"}}' for index in range(30)) + "]}").encode("utf-8")
        result = json_source.preview(content, "stores")
        self.assertEqual(result["record_count"], 30)
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(len(result["preview_rows"]), 25)

    def test_xml_preview_returns_all_rows_for_processing(self) -> None:
        content = ("<stores>" + "".join(f"<store><id>{index}</id><name>Store {index}</name></store>" for index in range(30)) + "</stores>").encode("utf-8")
        result = xml_source.preview(content)
        self.assertEqual(result["record_count"], 30)
        self.assertEqual(len(result["rows"]), 30)
        self.assertEqual(len(result["preview_rows"]), 25)

    def test_geojson_feature_collection_promotes_properties_and_point_coordinates(self) -> None:
        content = b"""{
          "type": "FeatureCollection",
          "features": [{
            "type": "Feature",
            "id": "store-1",
            "properties": {
              "name": "Geo Pizza",
              "address": "1 Map Lane",
              "city": "Raleigh",
              "state": "NC",
              "postal_code": "27601"
            },
            "geometry": { "type": "Point", "coordinates": [-78.6382, 35.7796] }
          }]
        }"""

        result = json_source.preview(content)

        self.assertEqual(result["record_path"], "features")
        self.assertIn("features", result["record_paths"])
        self.assertTrue({"name", "address", "city", "state", "postal_code", "latitude", "longitude", "geometry_type"} <= set(result["fields"]))
        self.assertEqual(result["rows"][0]["name"], "Geo Pizza")
        self.assertEqual(result["rows"][0]["longitude"], -78.6382)
        self.assertEqual(result["rows"][0]["latitude"], 35.7796)

    def test_geojson_features_record_path_is_mapper_friendly(self) -> None:
        content = b'{"features":[{"type":"Feature","properties":{"store_id":"10","name":"Point Store"},"geometry":{"type":"Point","coordinates":[-80.1,35.2]}}]}'

        result = json_source.preview(content, "features")

        self.assertEqual(result["record_path"], "features")
        self.assertEqual(result["rows"][0]["store_id"], "10")
        self.assertEqual(result["rows"][0]["latitude"], 35.2)
        self.assertEqual(result["rows"][0]["longitude"], -80.1)


if __name__ == "__main__":
    unittest.main()
