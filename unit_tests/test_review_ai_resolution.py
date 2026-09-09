from __future__ import annotations

import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as ws


class ReprocessAttemptCountTests(unittest.TestCase):
    """A record's "Review Again" counter (attempt_count) must accumulate
    across retries - it comes from the OLD error_listings row (via
    list_rejected(), which now selects attempt_count) and is incremented by
    one each time reprocess_rejected() is called on that record."""

    def test_attempt_count_increments_from_the_prior_error_row(self) -> None:
        prior_record = {"business_id": "biz-1", "source_type_id": "src-1", "row_number": 1, "attempt_count": 2, "raw_record": {}}
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": [prior_record]}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": ""}],
            })
        passed_payload = save_mapper_mock.call_args[0][0]
        self.assertEqual(passed_payload["attempt_count"], 3)

    def test_attempt_count_starts_at_one_when_no_prior_attempts_recorded(self) -> None:
        prior_record = {"business_id": "biz-1", "source_type_id": "src-1", "row_number": 1, "raw_record": {}}  # no attempt_count key at all
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": [prior_record]}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}) as save_mapper_mock, \
             patch.object(ws, "refresh_error_count", return_value=0):
            ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": ""}],
            })
        passed_payload = save_mapper_mock.call_args[0][0]
        self.assertEqual(passed_payload["attempt_count"], 1)


class ReprocessSuggestionOnRepeatFailureTests(unittest.TestCase):
    """When a resubmitted fix still fails validation, reprocess_rejected()
    must attach a concrete suggestion (from enrich_raw_listing_row) instead
    of returning nothing actionable - and a hierarchy conflict (ZIP vs
    coordinates disagreeing) must be surfaced as two explicit options."""

    def _mock_common(self):
        return [
            patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)),
            patch.object(ws, "_bigquery_client", return_value=object()),
            patch.object(ws, "list_rejected", return_value={"records": []}),
            patch.object(ws, "refresh_error_count", return_value=0),
        ]

    def test_suggested_fix_is_attached_when_enrichment_finds_a_better_value(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}), \
             patch.object(ws, "refresh_error_count", return_value=0), \
             patch("whitespace_tool.geo_enrichment.enrich_raw_listing_row", return_value={"city": "Austin", "state": "TX", "postal_code": "78701"}), \
             patch("whitespace_tool.geo_enrichment.detect_hierarchy_conflict", return_value=None):
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name", "city": "City"}},
                "rows": [{"name": "Store", "city": ""}],
            })
        self.assertIn("suggested_fix", result)
        self.assertEqual(result["suggested_fix"].get("city"), "Austin")
        self.assertNotIn("hierarchy_conflict", result)

    def test_hierarchy_conflict_is_attached_when_zip_and_coordinates_disagree(self) -> None:
        conflict_payload = {
            "distance_km": 62.0,
            "zip_based": {"city": "Boston", "state": "MA", "country": "United States", "zip_code": "02134", "latitude": 42.36, "longitude": -71.06},
            "coordinate_based": {"city": "Miami", "state": "FL", "country": "United States", "zip_code": "33101", "latitude": 25.77, "longitude": -80.19},
        }
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}), \
             patch.object(ws, "refresh_error_count", return_value=0), \
             patch("whitespace_tool.geo_enrichment.enrich_raw_listing_row", return_value={}), \
             patch("whitespace_tool.geo_enrichment.detect_hierarchy_conflict", return_value=conflict_payload):
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": "Store", "postal_code": "02134", "latitude": 25.77, "longitude": -80.19}],
            })
        self.assertEqual(result.get("hierarchy_conflict"), conflict_payload)

    def test_non_us_suggestion_is_attached_when_coordinates_are_genuinely_outside_us(self) -> None:
        worldwide_match = {
            "city": "Manchester", "state_code": "ENG", "country_name": "United Kingdom",
            "country_code": "GB", "zip_code": "M1 1AE", "distance_km": 3.2,
        }
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}), \
             patch.object(ws, "refresh_error_count", return_value=0), \
             patch("whitespace_tool.geo_enrichment.enrich_raw_listing_row", return_value={}), \
             patch("whitespace_tool.geo_enrichment.detect_hierarchy_conflict", return_value=None), \
             patch("whitespace_tool.geo_enrichment.is_us_land_coordinate", return_value=False), \
             patch("whitespace_tool.geo_enrichment.find_nearest_worldwide_city", return_value=worldwide_match):
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": "Store", "latitude": 53.48, "longitude": -2.24}],
            })
        self.assertEqual(result.get("non_us_suggestion"), {
            "city": "Manchester", "state": "ENG", "country": "United Kingdom",
            "country_code": "GB", "zip_code": "M1 1AE", "distance_km": 3.2,
        })

    def test_non_us_suggestion_absent_when_coordinates_are_within_us(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 0, "error_listings": 1}), \
             patch.object(ws, "refresh_error_count", return_value=0), \
             patch("whitespace_tool.geo_enrichment.enrich_raw_listing_row", return_value={}), \
             patch("whitespace_tool.geo_enrichment.detect_hierarchy_conflict", return_value=None), \
             patch("whitespace_tool.geo_enrichment.is_us_land_coordinate", return_value=True), \
             patch("whitespace_tool.geo_enrichment.find_nearest_worldwide_city") as worldwide_mock:
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": "Store", "latitude": 30.0, "longitude": -97.0}],
            })
        worldwide_mock.assert_not_called()
        self.assertNotIn("non_us_suggestion", result)

    def test_no_suggestion_block_added_when_reprocess_succeeds(self) -> None:
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=object()), \
             patch.object(ws, "list_rejected", return_value={"records": []}), \
             patch.object(ws, "save_mapper", return_value={"mapped_rows": 1, "error_listings": 0}), \
             patch.object(ws, "refresh_error_count", return_value=0), \
             patch("whitespace_tool.geo_enrichment.enrich_raw_listing_row") as enrich_mock:
            result = ws.reprocess_rejected({
                "event_id": "evt-1",
                "mapper": {"business_id": "biz-1", "brand": "Acme", "fields": {"name": "Name"}},
                "rows": [{"name": "Store"}],
            })
        enrich_mock.assert_not_called()
        self.assertNotIn("suggested_fix", result)
        self.assertNotIn("hierarchy_conflict", result)


if __name__ == "__main__":
    unittest.main()
