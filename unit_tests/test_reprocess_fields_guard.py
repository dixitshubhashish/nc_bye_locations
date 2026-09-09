from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as ws
from whitespace_tool.data_validation.fields import validate_normalized_location, validate_source_row
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.normalization import normalize_location


class ReprocessRejectedFieldsGuardTests(unittest.TestCase):
    """Regression test for the reported "'str' object has no attribute
    'get'"/'values' crash in the Review Error Listings retry-fix flow.

    Root cause chain:
    - ui/js/review.js built retryMapper.fields via
      `activeMapper.fields && Object.keys(activeMapper.fields).length ? ... `
      - if activeMapper.fields was ever a non-empty STRING (not an object),
        Object.keys(aString) still returns a truthy-length array in JS (it
        indexes the string's characters), so the ternary picked the raw
        string instead of falling back to a real fields object.
    - workflow_server.reprocess_rejected() then called
      `mapper.get("fields", {}).values()` with no type guard - unlike
      validate_mapper() (which does check isinstance(fields, dict)) and
      validate_source_row() (fixed alongside this test), this line ran
      earlier, before save_mapper()/validate_mapper() ever got a chance to
      catch the bad shape.

    This test only covers the backend guard (JS truthiness is out of reach
    for a Python test) - it proves reprocess_rejected() no longer raises
    when mapper["fields"] is a string.
    """

    def test_non_dict_mapper_fields_does_not_crash_source_field_extraction(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 0}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"brand": "Acme", "fields": "not-a-dict-string"},
                "rows": [{"name": "Test Store"}],
            })

        self.assertIn("mapped_rows", result)
        save_mapper_mock.assert_called_once()
        passed_payload = save_mapper_mock.call_args[0][0]
        # mapper["fields"] itself is passed through untouched (reprocess_rejected
        # doesn't mutate the caller's mapper) - the guard only protects the
        # derived source_fields extraction from crashing on it.
        self.assertEqual(passed_payload["mapper"]["fields"], "not-a-dict-string")
        # Falls back to the row's own keys, since the mapper's fields were unusable.
        self.assertEqual(passed_payload["source_fields"], ["name"])

    def test_dict_mapper_fields_still_extracts_source_fields_normally(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 1, "error_listings": 0}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"brand": "Acme", "fields": {"name": "Name", "city": "City"}},
                "rows": [{"Name": "Test Store", "City": "Austin"}],
            })

        passed_payload = save_mapper_mock.call_args[0][0]
        self.assertEqual(passed_payload["source_fields"], ["City", "Name"])


class ReprocessRejectedBrandImmutabilityTests(unittest.TestCase):
    """A record's brand is fixed by its event_id -> business_id relation -
    reprocess_rejected() must always re-resolve mapper["brand"] from the
    businesses table via business_id, never trust a client-supplied brand
    string (closes a gap where the edit-record dialog could submit a
    different brand than the record's real business_id maps to)."""

    def test_client_supplied_brand_is_overridden_by_the_businesses_table(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": [{"business_id": "biz-1", "source_type_id": "src-1"}]}), \
             patch.object(ws, "fetch_mirror_businesses", return_value=[{"business_id": "biz-1", "name": "Real Brand"}]), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 1, "error_listings": 0}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Attacker-Supplied Brand", "fields": {"name": "Name"}},
                "rows": [{"name": "Test Store"}],
            })

        passed_mapper = save_mapper_mock.call_args[0][0]["mapper"]
        self.assertEqual(passed_mapper["brand"], "Real Brand")

    def test_brand_resolution_falls_back_to_submitted_value_if_business_not_found(self) -> None:
        # No matching business_id in the businesses table (shouldn't happen
        # in practice) - don't blank out brand entirely, keep whatever was
        # submitted rather than losing it.
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": [{"business_id": "biz-missing", "source_type_id": "src-1"}]}), \
             patch.object(ws, "fetch_mirror_businesses", return_value=[]), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 1, "error_listings": 0}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-missing", "brand": "Submitted Brand", "fields": {"name": "Name"}},
                "rows": [{"name": "Test Store"}],
            })

        passed_mapper = save_mapper_mock.call_args[0][0]["mapper"]
        self.assertEqual(passed_mapper["brand"], "Submitted Brand")


class ValidateSourceRowFieldsGuardTests(unittest.TestCase):
    """validate_source_row() is a second, independent entry point into the
    same mapper["fields"] shape - it must not assume its caller already
    validated it (defense in depth alongside the reprocess_rejected guard)."""

    def test_non_dict_fields_returns_no_errors_instead_of_raising(self) -> None:
        errors = validate_source_row({"latitude": "not-a-number"}, {"fields": "not-a-dict-string"})
        self.assertEqual(errors, [])

    def test_missing_fields_key_returns_no_errors_instead_of_raising(self) -> None:
        errors = validate_source_row({"latitude": "not-a-number"}, {})
        self.assertEqual(errors, [])


class ValidationHintFieldLabelFormattingTests(unittest.TestCase):
    """Validation hints must show the field registry's human label (e.g.
    "Opening Date"), not the raw stored key ("opening_date"), so the
    Review Error Listings Action column reads as a real column name
    instead of a literal backend field key."""

    def test_type_mismatch_hint_uses_registry_label(self) -> None:
        # validate_source_row() no longer raises type-mismatch errors itself
        # (see test_csv_workflow.py's test_invalid_optional_values_are_cleared_not_rejected -
        # every field it checks is optional and normalize_location() already
        # clears an unparseable value to None) - validate_normalized_location()
        # is the surviving consumer of _field_label() for this kind of hint,
        # exercised here by forcing a value of the wrong Python type directly
        # (bypassing the normal optional_date() null-coercion).
        row = {"name": "Test Brand", "zip": "27601"}
        mapper = {"brand": "Test Brand", "fields": {"name": "name", "postal_code": "zip"}}
        location = normalize_location(row, mapper, "example_csv", 0)
        self.assertIsNotNone(location)
        bad_location = dataclasses.replace(location, opening_date="not-a-real-date")
        errors = validate_normalized_location(bad_location, load_field_registry())
        matching = [e for e in errors if e["field"] == "opening_date"]
        self.assertEqual(len(matching), 1)
        self.assertIn("Opening Date", matching[0]["hint"])
        self.assertNotIn("'opening_date'", matching[0]["hint"])

    def test_unknown_key_falls_back_to_the_key_itself(self) -> None:
        # A custom field with no registry label shouldn't crash formatting -
        # it just displays as its own key.
        from whitespace_tool.data_validation.fields import _field_label
        self.assertEqual(_field_label("some_custom_field"), "some_custom_field")


if __name__ == "__main__":
    unittest.main()
