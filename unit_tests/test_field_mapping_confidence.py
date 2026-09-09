from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache
import whitespace_tool.workflow_server as ws


class FieldMappingConfidenceStorageTests(unittest.TestCase):
    """The confidence score for a (target_key, source_field) pairing must
    accumulate across saves, not overwrite - that's the whole point of an
    "advancing" confidence layer that stabilizes with usage."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test_confidence.db")
        self._db_path_patch.start()
        sqlite_cache.init_sqlite_cache()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_kept_suggestion_accumulates_positive_score(self) -> None:
        sqlite_cache.record_mapping_confidence_events([{"target_key": "cuisine_type", "source_field": "Cuisine Type", "delta": 1}])
        sqlite_cache.record_mapping_confidence_events([{"target_key": "cuisine_type", "source_field": "cuisine_type", "delta": 1}])
        rows = sqlite_cache.get_mapping_confidence("cuisine_type")
        self.assertEqual(len(rows), 1)  # "Cuisine Type" and "cuisine_type" normalize to the same row
        self.assertEqual(rows[0]["score"], 2)
        self.assertEqual(rows[0]["sample_count"], 2)

    def test_switched_to_unmapped_applies_negative_delta(self) -> None:
        sqlite_cache.record_mapping_confidence_events([{"target_key": "phone_number", "source_field": "Phone", "delta": 1}])
        sqlite_cache.record_mapping_confidence_events([{"target_key": "phone_number", "source_field": "Phone", "delta": -0.5}])
        rows = sqlite_cache.get_mapping_confidence("phone_number")
        self.assertEqual(rows[0]["score"], 0.5)
        self.assertEqual(rows[0]["sample_count"], 2)

    def test_different_target_keys_are_tracked_independently(self) -> None:
        sqlite_cache.record_mapping_confidence_events([
            {"target_key": "city", "source_field": "City", "delta": 1},
            {"target_key": "state", "source_field": "City", "delta": -0.5},
        ])
        city_rows = sqlite_cache.get_mapping_confidence("city")
        state_rows = sqlite_cache.get_mapping_confidence("state")
        self.assertEqual(city_rows[0]["score"], 1)
        self.assertEqual(state_rows[0]["score"], -0.5)

    def test_malformed_events_are_skipped_not_raised(self) -> None:
        sqlite_cache.record_mapping_confidence_events([
            {"target_key": "", "source_field": "City", "delta": 1},
            {"target_key": "city", "source_field": "", "delta": 1},
            {"target_key": "city", "source_field": "City", "delta": "not-a-number"},
            {"target_key": "city", "source_field": "City", "delta": 1},
        ])
        rows = sqlite_cache.get_mapping_confidence("city")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 1)
        self.assertEqual(rows[0]["sample_count"], 1)


class MappingConfidenceEventDiffLogicTests(unittest.TestCase):
    """Mirrors computeMappingConfidenceEvents() (ui/js/mapper.js) in Python
    so the scoring rule itself (kept=+1, switched-to-other=+0.5, switched-
    to-unmapped=-0.5, fresh manual pairing=+1) is verified independent of
    the DB layer."""

    @staticmethod
    def _diff(original: dict, final: dict) -> list[dict]:
        events = []
        for key in set(original) | set(final):
            original_source = original.get(key, "")
            final_source = final.get(key, "")
            if not original_source and final_source:
                events.append({"target_key": key, "source_field": final_source, "delta": 1})
            elif original_source and final_source == original_source:
                events.append({"target_key": key, "source_field": original_source, "delta": 1})
            elif original_source and final_source:
                events.append({"target_key": key, "source_field": original_source, "delta": 0.5})
            elif original_source and not final_source:
                events.append({"target_key": key, "source_field": original_source, "delta": -0.5})
        return events

    def test_kept_as_suggested(self) -> None:
        events = self._diff({"city": "City"}, {"city": "City"})
        self.assertEqual(events, [{"target_key": "city", "source_field": "City", "delta": 1}])

    def test_switched_to_a_different_mapped_field(self) -> None:
        events = self._diff({"city": "Town"}, {"city": "City"})
        self.assertEqual(events, [{"target_key": "city", "source_field": "Town", "delta": 0.5}])

    def test_switched_to_unmapped(self) -> None:
        events = self._diff({"city": "Town"}, {})
        self.assertEqual(events, [{"target_key": "city", "source_field": "Town", "delta": -0.5}])

    def test_fresh_manual_pairing_with_no_prior_suggestion(self) -> None:
        events = self._diff({}, {"cuisine_type": "Cuisine"})
        self.assertEqual(events, [{"target_key": "cuisine_type", "source_field": "Cuisine", "delta": 1}])

    def test_never_suggested_never_mapped_produces_no_event(self) -> None:
        self.assertEqual(self._diff({}, {}), [])


class LearnMappingsConfidenceMergeTests(unittest.TestCase):
    """learn_mappings() must layer confidence-earned suggestions on top of
    template-vote suggestions for any target field the template votes
    didn't already cover, but never overwrite an existing template-vote
    suggestion, and never suggest a confidence pairing that hasn't earned
    enough samples or a positive score yet."""

    def test_high_confidence_pairing_fills_a_gap_left_by_template_votes(self) -> None:
        with patch.object(ws, "get_cached_query", return_value={"templates": []}), \
             patch.object(ws, "get_mapping_confidence", return_value=[
                 {"target_key": "cuisine_type", "source_field_normalized": "cuisinetype", "score": 5.0, "sample_count": 5},
             ]):
            result = ws.learn_mappings({"source_type": "csv", "source_fields": ["Cuisine Type", "Name"]})
        self.assertIn("cuisine_type", result["suggestions"])
        self.assertEqual(result["suggestions"]["cuisine_type"]["source"], "Cuisine Type")

    def test_low_sample_count_is_not_suggested_yet(self) -> None:
        with patch.object(ws, "get_cached_query", return_value={"templates": []}), \
             patch.object(ws, "get_mapping_confidence", return_value=[
                 {"target_key": "cuisine_type", "source_field_normalized": "cuisinetype", "score": 1.0, "sample_count": 1},
             ]):
            result = ws.learn_mappings({"source_type": "csv", "source_fields": ["Cuisine Type"]})
        self.assertNotIn("cuisine_type", result["suggestions"])

    def test_negative_score_is_never_suggested(self) -> None:
        with patch.object(ws, "get_cached_query", return_value={"templates": []}), \
             patch.object(ws, "get_mapping_confidence", return_value=[
                 {"target_key": "state", "source_field_normalized": "city", "score": -1.5, "sample_count": 4},
             ]):
            result = ws.learn_mappings({"source_type": "csv", "source_fields": ["City"]})
        self.assertNotIn("state", result["suggestions"])

    def test_confidence_pairing_not_present_in_this_source_is_ignored(self) -> None:
        with patch.object(ws, "get_cached_query", return_value={"templates": []}), \
             patch.object(ws, "get_mapping_confidence", return_value=[
                 {"target_key": "cuisine_type", "source_field_normalized": "cuisinetype", "score": 5.0, "sample_count": 5},
             ]):
            result = ws.learn_mappings({"source_type": "csv", "source_fields": ["Name", "Address"]})
        self.assertNotIn("cuisine_type", result["suggestions"])


if __name__ == "__main__":
    unittest.main()
