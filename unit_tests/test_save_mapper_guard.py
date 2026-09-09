from __future__ import annotations

import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as ws


def _mapper():
    return {
        "brand": "Acme",
        "source_name": "s.csv",
        "source_type": "csv",
        "source_type_id": "src-1",  # provided, so ensure_source_type() (BigQuery) is skipped
        "business_id": "biz-1",
        "fields": {"name": "Name", "address": "Addr", "city": "City", "state": "State", "postal_code": "Zip", "country": "Country", "latitude": "Lat"},
    }


SOURCE_FIELDS = ["Name", "Addr", "City", "State", "Zip", "Country", "Lat"]


def _invalid_rows(n):
    # Under the "only brand is mandatory" rule (see normalize_location()),
    # a blank name/address/city/state/zip no longer makes a row invalid -
    # brand is always present here via the mapper-level fallback. A
    # malformed *numeric* value (e.g. latitude that isn't a number) no
    # longer fails validate_source_row() either - every field it checks is
    # optional, so an unparseable value is cleared to None (normalize_location()
    # already does this) rather than blocking the row, since there's
    # nothing to "fix" by rejecting a record over one bad optional field.
    # A malformed ZIP is still a genuine hard rule (validate_normalized_location()'s
    # "invalid US ZIP code" check), so it's used here as the one remaining
    # way to produce an invalid row.
    return [{"Name": f"S{i}", "Addr": "1 St", "City": "Austin", "State": "TX", "Zip": "999", "Country": "United States", "Lat": "30.27"} for i in range(n)]


def _valid_row():
    return {"Name": "Good Store", "Addr": "1 Main St", "City": "Austin", "State": "TX", "Zip": "78701", "Country": "United States", "Lat": "30.27"}


class SaveMapperAllInvalidGuardTests(unittest.TestCase):
    """Every invalid source row is retained for review, including when the
    entire source batch fails validation."""

    def setUp(self) -> None:
        # Force field_catalog() down its offline fallback (load_field_registry),
        # so the test needs no BigQuery for field definitions.
        self._fc = patch.object(ws, "field_catalog", side_effect=Exception("no bigquery in test"))
        self._fc.start()

    def tearDown(self) -> None:
        self._fc.stop()

    def test_all_invalid_with_guard_still_writes_error_listings(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            result = ws.save_mapper(
                {"mapper": _mapper(), "rows": _invalid_rows(4), "source_fields": SOURCE_FIELDS},
                reject_all_invalid=True,
            )
        self.assertEqual(result["mapped_rows"], 0)
        self.assertEqual(result["error_listings"], 4)
        push.assert_called_once()

    def test_single_invalid_row_is_exempt_from_the_guard(self) -> None:
        # One bad row is a genuine record to review, not a mapping mistake, so
        # the guard must NOT fire (it should fall through to the normal write).
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            result = ws.save_mapper(
                {"mapper": _mapper(), "rows": _invalid_rows(1), "source_fields": SOURCE_FIELDS},
                reject_all_invalid=True,
            )
        self.assertEqual(result["mapped_rows"], 0)
        self.assertEqual(result["error_listings"], 1)
        push.assert_called_once()

    def test_all_invalid_without_guard_still_writes_error_listings(self) -> None:
        # reprocess/sample-load path (default reject_all_invalid=False): the
        # rows still go to error_listings as before.
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            result = ws.save_mapper({"mapper": _mapper(), "rows": _invalid_rows(4), "source_fields": SOURCE_FIELDS})
        self.assertEqual(result["mapped_rows"], 0)
        self.assertEqual(result["error_listings"], 4)
        push.assert_called_once()

    def test_partial_failure_with_guard_does_not_raise(self) -> None:
        # Some valid, some broken -> the real error-listings use case. The
        # guard must not fire; valid rows save and broken ones queue.
        rows = [_valid_row()] + _invalid_rows(2)
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            result = ws.save_mapper(
                {"mapper": _mapper(), "rows": rows, "source_fields": SOURCE_FIELDS},
                reject_all_invalid=True,
            )
        self.assertEqual(result["mapped_rows"], 1)
        self.assertEqual(result["error_listings"], 2)
        push.assert_called_once()

    def test_non_brand_fields_are_no_longer_mandatory(self) -> None:
        # A row with nothing but a well-typed value set (brand only comes
        # from the mapper level here) is valid - no address/city/state/zip
        # at all. Only brand is mandatory now, at every layer.
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            result = ws.save_mapper({
                "mapper": _mapper(),
                "rows": [{"Name": "", "Addr": "", "City": "", "State": "", "Zip": "", "Country": "", "Lat": ""}],
                "source_fields": SOURCE_FIELDS,
            })
        self.assertEqual(result["mapped_rows"], 1)
        self.assertEqual(result["error_listings"], 0)
        push.assert_called_once()


if __name__ == "__main__":
    unittest.main()
