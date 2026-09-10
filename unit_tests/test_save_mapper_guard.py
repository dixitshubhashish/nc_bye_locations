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


class BlankSourceNameFallbackTests(unittest.TestCase):
    """BUG-101 backend hardening: save_mapper() must not hard-fail on a blank
    mapper.source_name - it should generate one the same way the browser
    does for callers that bypass ui/js/mapper.js's fallbackSourceName()
    (a direct POST /api/save, or a hand-built payload)."""

    def setUp(self) -> None:
        self._fc = patch.object(ws, "field_catalog", side_effect=Exception("no bigquery in test"))
        self._fc.start()

    def tearDown(self) -> None:
        self._fc.stop()

    def test_fallback_prefers_source_url_filename(self) -> None:
        mapper = {"source_url": "https://example.com/path/Weekly_Export.CSV", "source_type": "csv"}
        self.assertEqual(ws._fallback_source_name(mapper), "weekly_export")

    def test_fallback_uses_source_type_placeholder_without_url(self) -> None:
        mapper = {"source_type": "json"}
        self.assertEqual(ws._fallback_source_name(mapper), "restaurant_locations_json")

    def test_fallback_uses_generic_placeholder_for_unknown_type(self) -> None:
        mapper = {"source_type": "", "source_url": ""}
        self.assertEqual(ws._fallback_source_name(mapper), "restaurant_locations")

    def test_save_mapper_generates_name_for_blank_source_name(self) -> None:
        mapper = _mapper()
        mapper["source_name"] = "   "
        mapper["source_url"] = "https://example.com/stores/atlanta_locations.json"
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "_maybe_refresh_after_save"):
            # Would raise ValueError("Mapper validation failed: source_name")
            # before this fix, since _resolve_mapper_source_fields() returns a
            # fresh dict (mutating the caller's `mapper` above proves nothing).
            result = ws.save_mapper({"mapper": mapper, "rows": [_valid_row()], "source_fields": SOURCE_FIELDS})
        self.assertEqual(result["mapped_rows"], 1)
        push.assert_called_once()

    def test_save_mapper_still_rejects_when_brand_missing(self) -> None:
        # The fallback only covers source_name - other required fields still
        # raise, exactly as before.
        mapper = _mapper()
        mapper["brand"] = ""
        mapper["source_name"] = ""
        with self.assertRaises(ValueError):
            ws.save_mapper({"mapper": mapper, "rows": [_valid_row()], "source_fields": SOURCE_FIELDS})


class SaveMapperRefreshChainTests(unittest.TestCase):
    """_maybe_refresh_after_save() -> _refresh_silver_background() is the
    mechanism that fires after every mapper save (the "Save Listing Data"
    button) to keep silver+gold+mirror in sync with newly-saved bronze data.
    test_scheduler.py already covers _maybe_refresh_after_save() and
    _refresh_silver_background() as standalone units (called directly), and
    every existing save_mapper() test in this file patches
    _maybe_refresh_after_save() out entirely - none of them assert it is
    actually reached by a real (non skip_cache_invalidation) save_mapper()
    call. These close that gap by patching one level lower
    (_refresh_silver_background, the function _maybe_refresh_after_save()
    itself calls) so the real save_mapper() -> _maybe_refresh_after_save()
    call boundary is exercised, not skipped.
    """

    def setUp(self) -> None:
        self._fc = patch.object(ws, "field_catalog", side_effect=Exception("no bigquery in test"))
        self._fc.start()

    def tearDown(self) -> None:
        self._fc.stop()

    def test_a_normal_save_reaches_the_background_refresh(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "_refresh_silver_background") as refresh:
            result = ws.save_mapper({"mapper": _mapper(), "rows": [_valid_row()], "source_fields": SOURCE_FIELDS})

        self.assertEqual(result["mapped_rows"], 1)
        push.assert_called_once()
        # skip_cache_invalidation defaults to False, so the mapper save path
        # (unlike the sample loader, which passes True deliberately) must
        # actually invalidate the cache and kick off the background refresh -
        # this is what keeps Reporting/Review in sync after "Save Listing Data".
        invalidate.assert_called_once()
        refresh.assert_called_once()

    def test_skip_cache_invalidation_true_bypasses_the_refresh(self) -> None:
        # The sample loader calls save_mapper(..., skip_cache_invalidation=True)
        # deliberately, to avoid firing a full refresh once per brand during a
        # bulk load. Confirms the opposite path of the test above through the
        # same real save_mapper() call, not just _maybe_refresh_after_save()
        # in isolation.
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "_load_mapped_zip_demographics", return_value={}), \
             patch.object(ws, "_dedupe_listings_against_bronze", side_effect=lambda c, p, d, rows: (rows, 0)), \
             patch.object(ws, "push_to_bigquery") as push, \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "_refresh_silver_background") as refresh:
            result = ws.save_mapper(
                {"mapper": _mapper(), "rows": [_valid_row()], "source_fields": SOURCE_FIELDS},
                skip_cache_invalidation=True,
            )

        self.assertEqual(result["mapped_rows"], 1)
        push.assert_called_once()
        invalidate.assert_not_called()
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
