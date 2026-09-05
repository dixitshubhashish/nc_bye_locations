from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

from whitespace_tool.analysis import dedupe_locations
from whitespace_tool.data_quality import run_quality_checks
from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.models import LocationRecord
from whitespace_tool.normalization import clean_zip, normalize_location, optional_date, optional_float, optional_int, optional_timestamp
from whitespace_tool.source_adapters import csv_source
from whitespace_tool.source_adapters.common import preview_payload
from whitespace_tool.source_adapters import json_source
from whitespace_tool.source_adapters import xml_source
from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS, build_table_rows
from whitespace_tool.workflow_server import REQUIRED_MAPPER_FIELDS, save_mapper, validate_mapper


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

    def test_preview_field_discovery_scans_all_rows(self) -> None:
        rows = [{"store_id": index, "store_name": f"Store {index}"} for index in range(100)]
        rows[80]["late_column"] = "present"
        result = preview_payload(rows)

        self.assertIn("late_column", result["fields"])

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
        self.assertEqual(optional_timestamp("2024-04-12T10:00:00Z"), "2024-04-12T10:00:00+00:00")
        self.assertIsNone(optional_timestamp("not-a-timestamp"))

    def test_invalid_optional_values_are_rejected(self) -> None:
        row = {**VALID_ROW, "opened_on": "0", "seats": "unknown", "observed": "not-a-timestamp"}
        mapper = {**VALID_MAPPER, "fields": {**VALID_MAPPER["fields"], "observed_at": "observed"}}
        errors = validate_source_row(row, mapper)
        self.assertEqual({error["field"] for error in errors}, {"opening_date", "seating_capacity", "observed_at"})

    def test_field_validator_registry_is_explicit_and_type_driven(self) -> None:
        from whitespace_tool.data_validation.fields import FIELD_VALIDATORS

        self.assertIn("opening_date", FIELD_VALIDATORS)
        self.assertIn("latitude", FIELD_VALIDATORS)
        self.assertIn("seating_capacity", FIELD_VALIDATORS)
        self.assertIn("observed_at", FIELD_VALIDATORS)
        self.assertIsNone(FIELD_VALIDATORS["opening_date"]("0"))
        self.assertEqual(FIELD_VALIDATORS["latitude"]("$1,250.50"), 1250.5)
        self.assertEqual(FIELD_VALIDATORS["seating_capacity"]("42.0"), 42)
        self.assertIsNone(FIELD_VALIDATORS["observed_at"]("0"))

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

    def test_normalized_validation_rejects_invalid_observed_at(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        bad_location = dataclasses.replace(location, observed_at="not-a-timestamp")
        errors = validate_normalized_location(bad_location, load_field_registry())
        self.assertTrue(any(error["field"] == "observed_at" for error in errors))

    def test_dedupe_uses_standard_location_identity_fields(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None

        same_identity = dataclasses.replace(
            location,
            brand=f" {location.brand.upper()} ",
            name=location.name.upper(),
            address=location.address.upper(),
            city=location.city.upper(),
            state=location.state.lower(),
        )
        changed_name_same_place = dataclasses.replace(location, name="Example Pizza Midtown")
        different_place = dataclasses.replace(
            location,
            location_id="store-002",
            name="Example Pizza North",
            address="900 Capital Boulevard",
            latitude=35.8123,
            longitude=-78.6211,
        )

        self.assertEqual(dedupe_locations([location, same_identity]), [location])
        self.assertEqual(dedupe_locations([location, changed_name_same_place]), [location])
        self.assertEqual(len(dedupe_locations([location, different_place])), 2)

    def test_dedupe_drops_fuzzy_address_and_coordinate_matches(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        fuzzy_duplicate = dataclasses.replace(
            location,
            location_id="store-001-alt",
            address="1 Main St.",
            latitude=35.77961,
            longitude=-78.63819,
        )
        same_address_far_away = dataclasses.replace(
            location,
            location_id="store-003",
            latitude=35.9000,
            longitude=-78.9000,
        )

        self.assertEqual(dedupe_locations([location, fuzzy_duplicate]), [location])
        self.assertEqual(len(dedupe_locations([location, same_address_far_away])), 2)

    def test_quality_duplicate_check_uses_standard_location_identity_fields(self) -> None:
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        different_place = dataclasses.replace(
            location,
            location_id="store-002",
            name="Example Pizza North",
            address="900 Capital Boulevard",
            latitude=35.8123,
            longitude=-78.6211,
        )
        duplicate = dataclasses.replace(location, address=location.address.upper())
        config = {"subject_brand": "Example Pizza", "competitor_brands": [], "freshness_policy": {}}

        no_duplicate_result = run_quality_checks([location, different_place], {}, config)
        self.assertFalse(any(issue["check"] == "duplicate_location_keys" for issue in no_duplicate_result["issues"]))

        duplicate_result = run_quality_checks([location, duplicate], {}, config)
        duplicate_issue = next(issue for issue in duplicate_result["issues"] if issue["check"] == "duplicate_location_keys")
        self.assertEqual(duplicate_issue["sample"][0]["postal_code"], "27601")

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

    def test_save_mapper_routes_bad_rows_to_error_listings_without_halting_valid_rows(self) -> None:
        captured_rows = {}
        rows = [
            VALID_ROW,
            {**VALID_ROW, "store_id": "bad-coords", "latitude": "not-a-latitude"},
            ["unexpected", "row", "shape"],
        ]

        def fake_push(_project_id, _dataset_id, rows_by_table, _credentials_json, **_kwargs):
            captured_rows.update(rows_by_table)

        def fake_dedupe(_client, _project_id, _dataset_id, listing_rows):
            return listing_rows, 0

        with patch("whitespace_tool.workflow_server.field_catalog", side_effect=RuntimeError("catalog unavailable")):
            with patch("whitespace_tool.workflow_server._load_mapped_zip_demographics", side_effect=RuntimeError("zip enrichment unavailable")):
                with patch("whitespace_tool.workflow_server._warehouse_settings", return_value=("project", "dataset", None)):
                    with patch("whitespace_tool.workflow_server._bigquery_client", return_value=object()):
                        with patch("whitespace_tool.workflow_server._dedupe_listings_against_bronze", side_effect=fake_dedupe):
                            with patch("whitespace_tool.workflow_server.push_to_bigquery", side_effect=fake_push):
                                result = save_mapper({"mapper": VALID_MAPPER, "rows": rows, "source_fields": list(VALID_ROW)})

        self.assertEqual(result["total_rows"], 3)
        self.assertEqual(result["mapped_rows"], 1)
        self.assertEqual(result["error_listings"], 2)
        self.assertEqual(len(captured_rows["listings"]), 1)
        self.assertEqual(len(captured_rows["error_listings"]), 2)

    def test_save_mapper_batch_flags_preserve_event_and_skip_duplicate_template(self) -> None:
        captured_batches = []
        rows = [
            VALID_ROW,
            {**VALID_ROW, "store_id": "bad-coords", "latitude": "not-a-latitude"},
        ]

        def fake_push(_project_id, _dataset_id, rows_by_table, _credentials_json, **_kwargs):
            captured_batches.append(rows_by_table)

        def fake_dedupe(_client, _project_id, _dataset_id, listing_rows):
            return listing_rows, 0

        with patch("whitespace_tool.workflow_server.field_catalog", side_effect=RuntimeError("catalog unavailable")):
            with patch("whitespace_tool.workflow_server._load_mapped_zip_demographics", side_effect=RuntimeError("zip enrichment unavailable")):
                with patch("whitespace_tool.workflow_server._warehouse_settings", return_value=("project", "dataset", None)):
                    with patch("whitespace_tool.workflow_server._bigquery_client", return_value=object()):
                        with patch("whitespace_tool.workflow_server._dedupe_listings_against_bronze", side_effect=fake_dedupe):
                            with patch("whitespace_tool.workflow_server.push_to_bigquery", side_effect=fake_push):
                                first = save_mapper({
                                    "mapper": dict(VALID_MAPPER),
                                    "rows": [rows[0]],
                                    "source_fields": list(VALID_ROW),
                                    "batch_event_id": "batch-123",
                                    "row_offset": 0,
                                    "save_template": True,
                                })
                                second = save_mapper({
                                    "mapper": dict(VALID_MAPPER),
                                    "rows": [rows[1]],
                                    "source_fields": list(VALID_ROW),
                                    "batch_event_id": "batch-123",
                                    "row_offset": 1,
                                    "save_template": False,
                                })

        self.assertEqual(first["event_id"], "batch-123")
        self.assertEqual(second["event_id"], "batch-123")
        self.assertTrue(first["template_saved"])
        self.assertFalse(second["template_saved"])
        self.assertEqual(len(captured_batches[0]["workflow_templates"]), 1)
        self.assertEqual(captured_batches[1]["workflow_templates"], [])
        self.assertEqual(captured_batches[1]["error_listings"][0]["row_number"], 2)

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


    def test_invalid_geographic_and_type_data_flags_error_listings(self) -> None:
        """Test edge cases with malformed ZIPs, bad dates, and out-of-bounds coordinates."""
        # 1. Invalid ZIP code (not 5 digits)
        row_bad_zip = {**VALID_ROW, "zip_code": "999"}
        loc_bad_zip = normalize_location(row_bad_zip, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(loc_bad_zip)
        errors_zip = validate_normalized_location(loc_bad_zip, load_field_registry())
        self.assertTrue(any(e["field"] == "postal_code" for e in errors_zip))
        self.assertIn("invalid US ZIP code", [e["reason"] for e in errors_zip])

        # 2. Out-of-bounds US Coordinates (Lat 95.0, Lon 20.0 - inside Europe/Asia)
        row_bad_coords = {**VALID_ROW, "latitude": "95.0", "longitude": "20.0"}
        loc_bad_coords = normalize_location(row_bad_coords, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(loc_bad_coords)
        errors_coords = validate_normalized_location(loc_bad_coords, load_field_registry())
        self.assertTrue(any(e["field"] == "coordinates" for e in errors_coords))
        self.assertIn("coordinates outside US boundary", [e["reason"] for e in errors_coords])

        # 3. Malformed dates and seating capacities
        row_bad_types = {**VALID_ROW, "opened_on": "not-a-date", "seats": "invalid_number"}
        errors_types = validate_source_row(row_bad_types, VALID_MAPPER)
        self.assertEqual({e["field"] for e in errors_types}, {"opening_date", "seating_capacity"})
        self.assertTrue(all("hint" in e for e in errors_types))

    def test_currency_formatting_and_domain_boundary_checks(self) -> None:
        """Test currency cleaning ($1,250.50 -> 1250.5) and age/income domain boundaries."""
        # Currency string cleaning
        self.assertEqual(optional_float("$1,250.50"), 1250.5)
        self.assertEqual(optional_int("$50,000"), 50000)

        # Domain boundary checks
        location = normalize_location(VALID_ROW, VALID_MAPPER, "example_csv", 0)
        self.assertIsNotNone(location)
        assert location is not None
        
        # Domain boundary checks for ZipDemographics and LocationRecord
        from whitespace_tool.models import ZipDemographics
        demo_bad_age = ZipDemographics(zip_code="27601", population=5000, median_household_income=50000, median_age=145, source="demo")
        errs_age = validate_normalized_location(demo_bad_age, load_field_registry())
        self.assertTrue(any(e["field"] == "median_age" for e in errs_age))
        self.assertIn("age outside realistic boundary", [e["reason"] for e in errs_age])

        # Test negative revenue on LocationRecord
        import dataclasses
        loc_bad_rev = dataclasses.replace(location, annual_revenue=-5000.0)
        errs_rev = validate_normalized_location(loc_bad_rev, load_field_registry())
        self.assertTrue(any(e["field"] == "annual_revenue" for e in errs_rev))
        self.assertIn("negative monetary amount", [e["reason"] for e in errs_rev])


if __name__ == "__main__":
    unittest.main()
