"""Coverage for whitespace_tool/analysis.py (44% covered at time of writing,
missing lines 21, 52, 58, 89-93, 97, 105-116, 120-130, 138-218 per
`coverage report -m`).

whitespace_tool/analysis.py is pure in-memory logic with no BigQuery/network
dependency, so these tests build real LocationRecord/ZipDemographics objects
directly rather than mocking anything.

dedupe_locations()/is_fuzzy_duplicate_location() already have coverage via
unit_tests/test_csv_workflow.py (checked before writing this file), so this
module focuses on the previously-uncovered pieces: _geo_allowed,
_metric_value, _profile_stats, _distance, and analyze_whitespace() end to
end.
"""

from __future__ import annotations

import unittest

from whitespace_tool.analysis import (
    _distance,
    _geo_allowed,
    _metric_value,
    _profile_stats,
    analyze_whitespace,
)
from whitespace_tool.models import LocationRecord, ZipDemographics


def make_location(
    *,
    brand: str,
    zip_code: str,
    location_id: str,
    name: str = "Store",
    address: str = "1 Main St",
    city: str = "Anytown",
    state: str = "TX",
) -> LocationRecord:
    return LocationRecord(
        brand=brand,
        business_id="biz-1",
        source_type_id="src-1",
        location_id=location_id,
        name=name,
        address=address,
        city=city,
        state=state,
        postal_code=zip_code,
        latitude=30.0,
        longitude=-97.0,
        source="test-source",
        observed_at="2026-01-01T00:00:00+00:00",
        raw={},
    )


def make_demo(
    zip_code: str,
    *,
    population: float | None,
    median_household_income: float | None,
    median_age: float | None = 35.0,
    source: str = "census",
) -> ZipDemographics:
    return ZipDemographics(
        zip_code=zip_code,
        population=population,
        median_household_income=median_household_income,
        median_age=median_age,
        source=source,
    )


class GeoAllowedTests(unittest.TestCase):
    def test_us_geography_allows_everything(self) -> None:
        demo = make_demo("10001", population=1, median_household_income=1)
        self.assertTrue(_geo_allowed("10001", demo, {"type": "us"}))

    def test_default_geography_without_type_key_is_us(self) -> None:
        demo = make_demo("10001", population=1, median_household_income=1)
        self.assertTrue(_geo_allowed("10001", demo, {}))

    def test_zip_prefixes_matches_a_configured_prefix(self) -> None:
        demo = make_demo("78701", population=1, median_household_income=1)
        geography = {"type": "zip_prefixes", "values": ["787", "733"]}
        self.assertTrue(_geo_allowed("78701", demo, geography))

    def test_zip_prefixes_rejects_a_non_matching_zip(self) -> None:
        demo = make_demo("10001", population=1, median_household_income=1)
        geography = {"type": "zip_prefixes", "values": ["787"]}
        self.assertFalse(_geo_allowed("10001", demo, geography))

    def test_unsupported_geography_type_raises_value_error(self) -> None:
        demo = make_demo("10001", population=1, median_household_income=1)
        with self.assertRaises(ValueError):
            _geo_allowed("10001", demo, {"type": "county"})


class MetricValueTests(unittest.TestCase):
    def test_reads_an_existing_attribute(self) -> None:
        demo = make_demo("10001", population=500.0, median_household_income=1)
        self.assertEqual(_metric_value(demo, "population"), 500.0)

    def test_unknown_metric_name_returns_none_instead_of_raising(self) -> None:
        demo = make_demo("10001", population=500.0, median_household_income=1)
        self.assertIsNone(_metric_value(demo, "not_a_real_field"))


class ProfileStatsTests(unittest.TestCase):
    def test_computes_mean_and_population_stdev_for_each_metric(self) -> None:
        demographics = {
            "10001": make_demo("10001", population=1000.0, median_household_income=50000.0),
            "10002": make_demo("10002", population=2000.0, median_household_income=60000.0),
        }
        stats = _profile_stats({"10001", "10002"}, demographics, ["population", "median_household_income"])
        self.assertEqual(stats["population"], (1500.0, 500.0))
        self.assertEqual(stats["median_household_income"], (55000.0, 5000.0))

    def test_zero_spread_falls_back_to_one_to_avoid_divide_by_zero(self) -> None:
        # A single subject ZIP (or all-identical values) gives pstdev == 0,
        # which _distance() would later divide by - the "or 1.0" fallback
        # exists specifically to keep that from becoming a ZeroDivisionError.
        demographics = {
            "10001": make_demo("10001", population=1000.0, median_household_income=50000.0),
        }
        stats = _profile_stats({"10001"}, demographics, ["population"])
        self.assertEqual(stats["population"], (1000.0, 1.0))

    def test_metric_missing_for_every_subject_zip_raises_value_error(self) -> None:
        demographics = {
            "10001": make_demo("10001", population=None, median_household_income=50000.0),
        }
        with self.assertRaises(ValueError):
            _profile_stats({"10001"}, demographics, ["population"])


class DistanceTests(unittest.TestCase):
    def test_distance_zero_when_demo_equals_the_profile_center(self) -> None:
        stats = {"population": (1500.0, 500.0), "median_household_income": (55000.0, 5000.0)}
        demo = make_demo("30301", population=1500.0, median_household_income=55000.0)
        self.assertEqual(_distance(demo, stats), 0.0)

    def test_distance_reflects_z_score_magnitude(self) -> None:
        stats = {"population": (1500.0, 500.0), "median_household_income": (55000.0, 5000.0)}
        demo = make_demo("30301", population=2500.0, median_household_income=65000.0)
        # z_population = (2500-1500)/500 = 2, z_income = (65000-55000)/5000 = 2
        self.assertAlmostEqual(_distance(demo, stats), (2**2 + 2**2) ** 0.5)

    def test_demo_missing_a_metric_returns_none(self) -> None:
        stats = {"population": (1500.0, 500.0), "median_household_income": (55000.0, 5000.0)}
        demo = make_demo("30301", population=None, median_household_income=65000.0)
        self.assertIsNone(_distance(demo, stats))


class AnalyzeWhitespaceTests(unittest.TestCase):
    """End-to-end analyze_whitespace() over a small, hand-computed scenario.

    Subject brand "Dominos" is present in zips A/B; those seed the
    similarity profile (population mean 1500/spread 500, income mean
    55000/spread 5000). Zips C/D/E don't have the subject brand and become
    whitespace candidates; zip F is deliberately far outside max_distance
    to prove the cutoff is enforced. Distances (population, income) were
    computed by hand:
      C: pop=1500, income=55000  -> distance 0.0
      D: pop=2500, income=65000  -> distance sqrt(2^2+2^2) ~= 2.8284
      E: pop=1400, income=54000  -> distance sqrt(0.2^2+0.2^2) ~= 0.2828
      F: pop=100000, income=200000 -> far outside max_distance, excluded
    """

    def setUp(self) -> None:
        self.locations = [
            make_location(brand="Dominos", zip_code="A0001", location_id="d1"),
            make_location(brand="Dominos", zip_code="B0002", location_id="d2"),
            make_location(brand="Pizza Hut", zip_code="C0003", location_id="p1"),
            make_location(brand="Little Caesars", zip_code="D0004", location_id="l1"),
        ]
        self.demographics = {
            "A0001": make_demo("A0001", population=1000.0, median_household_income=50000.0),
            "B0002": make_demo("B0002", population=2000.0, median_household_income=60000.0),
            "C0003": make_demo("C0003", population=1500.0, median_household_income=55000.0),
            "D0004": make_demo("D0004", population=2500.0, median_household_income=65000.0),
            "E0005": make_demo("E0005", population=1400.0, median_household_income=54000.0),
            "F0006": make_demo("F0006", population=100000.0, median_household_income=200000.0),
        }
        self.config = {
            "subject_brand": "Dominos",
            "competitor_brands": ["Pizza Hut", "Little Caesars"],
            "similarity": {"metrics": ["population", "median_household_income"], "max_distance": 3.0},
        }

    def test_location_output_contains_every_tracked_brand_row_with_demo(self) -> None:
        location_output, _, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        zips_in_output = {row["zip_code"] for row in location_output}
        self.assertEqual(zips_in_output, {"A0001", "B0002", "C0003", "D0004"})
        dominos_row = next(row for row in location_output if row["location_id"] == "d1")
        self.assertEqual(dominos_row["brand"], "Dominos")
        self.assertEqual(dominos_row["population"], 1000.0)

    def test_location_without_demographics_is_dropped_from_location_output(self) -> None:
        locations = self.locations + [make_location(brand="Dominos", zip_code="Z9999", location_id="d3")]
        location_output, _, _ = analyze_whitespace(locations, self.demographics, self.config)
        self.assertNotIn("Z9999", {row["zip_code"] for row in location_output})

    def test_untracked_brand_is_excluded_entirely(self) -> None:
        locations = self.locations + [make_location(brand="Papa Johns", zip_code="C0003", location_id="pj1")]
        location_output, _, summary = analyze_whitespace(locations, self.demographics, self.config)
        self.assertNotIn("pj1", {row["location_id"] for row in location_output})
        # location_records in the summary counts post-dedupe/brand-filter
        # locations, so the untracked brand must not inflate it.
        self.assertEqual(summary["location_records"], 4)

    def test_whitespace_output_excludes_zips_where_subject_brand_present(self) -> None:
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        zips = {row["zip_code"] for row in whitespace_output}
        self.assertNotIn("A0001", zips)
        self.assertNotIn("B0002", zips)

    def test_whitespace_output_excludes_zips_beyond_max_distance(self) -> None:
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        zips = {row["zip_code"] for row in whitespace_output}
        self.assertNotIn("F0006", zips)

    def test_whitespace_output_sorted_ascending_by_similarity_distance(self) -> None:
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        zips_in_order = [row["zip_code"] for row in whitespace_output]
        self.assertEqual(zips_in_order, ["C0003", "E0005", "D0004"])
        distances = [row["similarity_distance"] for row in whitespace_output]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual(whitespace_output[0]["similarity_distance"], 0.0)
        self.assertAlmostEqual(whitespace_output[1]["similarity_distance"], 0.2828, places=3)
        self.assertAlmostEqual(whitespace_output[2]["similarity_distance"], 2.8284, places=3)

    def test_whitespace_type_competitor_present_vs_no_tracked_brand(self) -> None:
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        by_zip = {row["zip_code"]: row for row in whitespace_output}
        self.assertEqual(by_zip["C0003"]["whitespace_type"], "competitor_present")
        self.assertEqual(by_zip["C0003"]["competitors_present"], "Pizza Hut")
        self.assertEqual(by_zip["D0004"]["whitespace_type"], "competitor_present")
        self.assertEqual(by_zip["D0004"]["competitors_present"], "Little Caesars")
        self.assertEqual(by_zip["E0005"]["whitespace_type"], "no_tracked_brand_present")
        self.assertEqual(by_zip["E0005"]["competitors_present"], "")

    def test_hardcoded_brand_count_keys_reflect_actual_locations_present(self) -> None:
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, self.config)
        by_zip = {row["zip_code"]: row for row in whitespace_output}
        self.assertEqual(by_zip["C0003"]["pizza_hut_count"], 1)
        self.assertEqual(by_zip["C0003"]["little_caesars_count"], 0)
        self.assertEqual(by_zip["D0004"]["little_caesars_count"], 1)
        self.assertEqual(by_zip["D0004"]["pizza_hut_count"], 0)

    def test_dominos_count_key_is_hardcoded_regardless_of_the_configured_subject_brand(self) -> None:
        # `dominos_count` is a hardcoded output key in analysis.py regardless
        # of what the configured subject_brand actually is - it always holds
        # counts_by_zip_brand[(zip_code, subject_brand)]. Proven here with a
        # subject brand that is NOT literally "Dominos": whitespace rows can
        # never have the subject brand present (those zips are filtered out
        # earlier), so the value is always 0 - but the key itself must still
        # be named "dominos_count", not e.g. "acme_pizza_count".
        locations = [
            make_location(brand="ACME Pizza", zip_code="A0001", location_id="a1"),
            make_location(brand="ACME Pizza", zip_code="B0002", location_id="a2"),
            make_location(brand="Pizza Hut", zip_code="C0003", location_id="p1"),
        ]
        config = {
            "subject_brand": "ACME Pizza",
            "competitor_brands": ["Pizza Hut"],
            "similarity": {"metrics": ["population", "median_household_income"], "max_distance": 3.0},
        }
        _, whitespace_output, _ = analyze_whitespace(locations, self.demographics, config)
        by_zip = {row["zip_code"]: row for row in whitespace_output}
        self.assertIn("dominos_count", by_zip["C0003"])
        self.assertEqual(by_zip["C0003"]["dominos_count"], 0)

    def test_summary_contents(self) -> None:
        _, _, summary = analyze_whitespace(self.locations, self.demographics, self.config)
        self.assertEqual(summary["subject_brand"], "Dominos")
        self.assertEqual(summary["competitor_brands"], ["Little Caesars", "Pizza Hut"])
        self.assertEqual(summary["location_records"], 4)
        self.assertEqual(summary["subject_zip_count"], 2)
        self.assertEqual(summary["whitespace_zip_count"], 3)
        self.assertEqual(summary["similarity_metrics"], ["population", "median_household_income"])
        self.assertEqual(summary["similarity_centers"]["population"], 1500.0)
        self.assertEqual(summary["similarity_spreads"]["population"], 500.0)

    def test_geography_filter_restricts_whitespace_output(self) -> None:
        # Only zips starting with "A", "B" or "C" are in-geography, so both
        # subject zips (A0001/B0002) still seed the profile, but D0004/
        # E0005/F0006 must be excluded from whitespace_output purely by
        # geography - even though D0004/E0005 would otherwise qualify by
        # distance (as proven by the un-filtered test above).
        config = {
            **self.config,
            "geography": {"type": "zip_prefixes", "values": ["A", "B", "C"]},
        }
        _, whitespace_output, summary = analyze_whitespace(self.locations, self.demographics, config)
        self.assertEqual(summary["subject_zip_count"], 2)
        zips = {row["zip_code"] for row in whitespace_output}
        self.assertEqual(zips, {"C0003"})

    def test_default_geography_is_us_when_key_absent(self) -> None:
        config = dict(self.config)
        config.pop("geography", None)
        # Should not raise and should behave like {"type": "us"}.
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, config)
        self.assertTrue(whitespace_output)

    def test_default_max_distance_used_when_not_configured(self) -> None:
        config = {
            "subject_brand": "Dominos",
            "competitor_brands": ["Pizza Hut", "Little Caesars"],
            "similarity": {"metrics": ["population", "median_household_income"]},
        }
        _, whitespace_output, _ = analyze_whitespace(self.locations, self.demographics, config)
        # Default max_distance is 1.5, so D0004 (distance ~2.83) must be
        # excluded even though it made the cut under this test's explicit 3.0.
        zips = {row["zip_code"] for row in whitespace_output}
        self.assertNotIn("D0004", zips)
        self.assertIn("C0003", zips)


if __name__ == "__main__":
    unittest.main()
