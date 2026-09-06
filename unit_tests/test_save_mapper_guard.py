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
        "fields": {"name": "Name", "address": "Addr", "city": "City", "state": "State", "postal_code": "Zip"},
    }


SOURCE_FIELDS = ["Name", "Addr", "City", "State", "Zip"]


def _invalid_rows(n):
    # Empty Zip -> normalize_location() returns None -> required_location error, for every row.
    return [{"Name": f"S{i}", "Addr": "1 St", "City": "Austin", "State": "TX", "Zip": ""} for i in range(n)]


def _valid_row():
    return {"Name": "Good Store", "Addr": "1 Main St", "City": "Austin", "State": "TX", "Zip": "78701"}


class SaveMapperAllInvalidGuardTests(unittest.TestCase):
    """A save where every row fails validation is a wrong-mapping mistake, not
    a set of individually bad records. With the guard on (the mapping-tab
    save), save_mapper must reject and write NOTHING - not flood
    error_listings. reprocess/sample-load leave the guard off and keep the
    old per-row behavior."""

    def setUp(self) -> None:
        # Force field_catalog() down its offline fallback (load_field_registry),
        # so the test needs no BigQuery for field definitions.
        self._fc = patch.object(ws, "field_catalog", side_effect=Exception("no bigquery in test"))
        self._fc.start()

    def tearDown(self) -> None:
        self._fc.stop()

    def test_all_invalid_with_guard_raises_before_touching_bigquery(self) -> None:
        with patch.object(ws, "_warehouse_settings") as settings, \
             patch.object(ws, "push_to_bigquery") as push:
            with self.assertRaises(ValueError) as ctx:
                ws.save_mapper(
                    {"mapper": _mapper(), "rows": _invalid_rows(4), "source_fields": SOURCE_FIELDS},
                    reject_all_invalid=True,
                )
        self.assertIn("field mapping looks wrong", str(ctx.exception))
        # The guard fires before the warehouse is ever contacted: nothing is
        # written and no review records are created.
        settings.assert_not_called()
        push.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
