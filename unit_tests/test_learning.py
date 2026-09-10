"""Coverage for whitespace_tool/learning.py (44% covered at time of writing,
missing lines 20-32 and 36-37 per `coverage report -m`).

suggest_from_templates() is pure in-memory logic (no BigQuery/network
dependency) so these tests call it directly with hand-built template dicts.
"""

from __future__ import annotations

import unittest

from whitespace_tool.learning import suggest_from_templates


class SuggestFromTemplatesTests(unittest.TestCase):
    def test_components_as_dict_with_mapper_key(self) -> None:
        templates = [
            {"components": {"mapper": {"source_type": "csv", "fields": {"city": "City Name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_components_as_json_string_is_parsed(self) -> None:
        templates = [
            {"components": '{"mapper": {"source_type": "csv", "fields": {"city": "City Name"}}}'},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_malformed_json_string_is_skipped_not_raised(self) -> None:
        # A template with corrupted `components` JSON must not crash the
        # whole suggestion pass - it should just contribute no votes.
        templates = [
            {"components": "{not valid json"},
            {"components": {"mapper": {"fields": {"city": "City Name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_components_missing_entirely_defaults_to_empty_dict(self) -> None:
        templates = [{"name": "no components key"}]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {})

    def test_components_non_dict_non_string_yields_no_votes(self) -> None:
        # isinstance(components, dict) is False for e.g. None or a list, so
        # mapper falls back to {} rather than raising an AttributeError.
        templates = [{"components": None}, {"components": ["not", "a", "dict"]}]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {})

    def test_components_without_mapper_wrapper_uses_components_itself(self) -> None:
        # mapper = components.get("mapper", components) - when there's no
        # "mapper" key, components is itself treated as the mapper dict.
        templates = [{"components": {"fields": {"city": "City Name"}}}]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_mismatched_source_type_is_filtered_out(self) -> None:
        templates = [
            {"components": {"mapper": {"source_type": "xml", "fields": {"city": "City Name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {})

    def test_mapper_without_source_type_is_not_filtered(self) -> None:
        templates = [
            {"components": {"mapper": {"fields": {"city": "City Name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_source_field_not_present_in_available_is_ignored(self) -> None:
        templates = [
            {"components": {"mapper": {"fields": {"city": "Some Typo Column"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {})

    def test_fuzzy_matching_is_case_and_punctuation_insensitive(self) -> None:
        # _clean() strips non-alnum and lowercases, so "city_name" should
        # match the available "City Name" source field.
        templates = [
            {"components": {"mapper": {"fields": {"city": "city_name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 1}})

    def test_majority_vote_across_multiple_templates_picks_the_most_common_source(self) -> None:
        templates = [
            {"components": {"mapper": {"fields": {"city": "City Name"}}}},
            {"components": {"mapper": {"fields": {"city": "City Name"}}}},
            {"components": {"mapper": {"fields": {"city": "Town"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name", "Town"], "csv")
        self.assertEqual(suggestions, {"city": {"source": "City Name", "uses": 2}})

    def test_tie_break_prefers_the_source_field_voted_for_first(self) -> None:
        # Counter.most_common(1) breaks equal-count ties by first-inserted
        # order - the first candidate to reach the max vote count wins.
        templates = [
            {"components": {"mapper": {"fields": {"city": "Town"}}}},
            {"components": {"mapper": {"fields": {"city": "City Name"}}}},
        ]
        suggestions = suggest_from_templates(templates, ["City Name", "Town"], "csv")
        self.assertEqual(suggestions["city"]["uses"], 1)
        self.assertIn(suggestions["city"]["source"], {"Town", "City Name"})

    def test_multiple_targets_are_learned_independently(self) -> None:
        templates = [
            {
                "components": {
                    "mapper": {
                        "fields": {"city": "City Name", "zip": "Postal Code"},
                    }
                }
            },
        ]
        suggestions = suggest_from_templates(templates, ["City Name", "Postal Code"], "csv")
        self.assertEqual(
            suggestions,
            {
                "city": {"source": "City Name", "uses": 1},
                "zip": {"source": "Postal Code", "uses": 1},
            },
        )

    def test_empty_templates_list_returns_empty_dict(self) -> None:
        self.assertEqual(suggest_from_templates([], ["City Name"], "csv"), {})

    def test_blank_source_fields_are_excluded_from_available(self) -> None:
        # source_fields entries that are blank/whitespace-only should never
        # be selectable - available is built with `if str(field).strip()`.
        templates = [
            {"components": {"mapper": {"fields": {"city": ""}}}},
        ]
        suggestions = suggest_from_templates(templates, ["", "  ", "City Name"], "csv")
        self.assertEqual(suggestions, {})


if __name__ == "__main__":
    unittest.main()
