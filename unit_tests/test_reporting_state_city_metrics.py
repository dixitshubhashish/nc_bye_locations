from __future__ import annotations

import inspect
import unittest

import whitespace_tool.workflow_server as workflow_server


def _row(zip_code, city, state, state_name, county, brand, location_count, population=None, median_household_income=None):
    return {
        "zip_code": zip_code,
        "zip_city": city,
        "zip_state": state,
        "zip_state_name": state_name,
        "county": county,
        "population": population,
        "median_household_income": median_household_income,
        "median_age": None,
        "listing_id": f"{brand}|{zip_code}" if brand and location_count else None,
        "brand": brand,
        "last_observed_at": None,
        "location_count": location_count,
    }


class MirrorStateMedianIncomeTests(unittest.TestCase):
    """_mirror_state_median_income_by_state() must dedupe by zip before
    averaging - the source rows (fetch_mirror_zip_brand_activity) repeat the
    same income value once per brand fanned out on a zip, so a naive
    average over all rows would double-weight zips with more brands."""

    def test_averages_once_per_zip_not_once_per_brand_row(self) -> None:
        all_zip_rows = [
            {"zip_code": "10001", "state_code": "NY", "median_household_income": 80000},
            {"zip_code": "10001", "state_code": "NY", "median_household_income": 80000},  # same zip, 2nd brand row
            {"zip_code": "10002", "state_code": "NY", "median_household_income": 40000},
        ]
        result = workflow_server._mirror_state_median_income_by_state(all_zip_rows)
        # (80000 + 40000) / 2 zips = 60000, not (80000+80000+40000)/3 = 66666
        self.assertEqual(result["NY"], 60000)

    def test_zips_with_no_income_are_excluded_not_treated_as_zero(self) -> None:
        all_zip_rows = [
            {"zip_code": "10001", "state_code": "NY", "median_household_income": 80000},
            {"zip_code": "10002", "state_code": "NY", "median_household_income": None},
        ]
        result = workflow_server._mirror_state_median_income_by_state(all_zip_rows)
        self.assertEqual(result["NY"], 80000)


class MirrorTopStatesMetricsTests(unittest.TestCase):
    def test_includes_median_income_and_brand_split(self) -> None:
        base_rows = [
            _row("10001", "New York", "NY", "New York", "New York County", "Domino's", 3),
            _row("10002", "Brooklyn", "NY", "New York", "Kings County", "Pizza Hut", 2),
        ]
        state_population = {"NY": 1000000}
        state_median_income = {"NY": 65000}

        rows = workflow_server._mirror_top_states(
            base_rows, state_population, state_median_income,
            main_brands=["Domino's"], competitor_brands=["Pizza Hut"],
        )

        self.assertEqual(len(rows), 1)
        ny = rows[0]
        self.assertEqual(ny["state"], "NY")
        self.assertEqual(ny["state_population"], 1000000)
        self.assertEqual(ny["median_household_income"], 65000)
        self.assertEqual(ny["main_brand_locations"], 3)
        self.assertEqual(ny["competitor_brand_locations"], 2)

    def test_brand_split_is_zero_when_no_brand_filter_given(self) -> None:
        base_rows = [_row("10001", "New York", "NY", "New York", "New York County", "Domino's", 3)]
        rows = workflow_server._mirror_top_states(base_rows, {}, {})
        self.assertEqual(rows[0]["main_brand_locations"], 0)
        self.assertEqual(rows[0]["competitor_brand_locations"], 0)

    def test_missing_population_and_income_default_to_zero_not_error(self) -> None:
        base_rows = [_row("99999", "Nowhere", "ZZ", "Nowhere State", "", "Acme", 1)]
        rows = workflow_server._mirror_top_states(base_rows, {}, {})
        self.assertEqual(rows[0]["state_population"], 0)
        self.assertEqual(rows[0]["median_household_income"], 0)

    def test_covers_every_us_state_not_just_a_top_fifteen(self) -> None:
        # Real bug, 2026-09-10: this same payload draws EVERY state bubble on
        # the national map, not just a top-N leaderboard row. A state outside
        # a small cut gets no entry AT ALL in the response (not a real zero),
        # so a real state like CO rendered as flat "no data" white on the map
        # even though it had genuine listings - just not enough to place in
        # the old top 15. 30 distinct states here must all survive.
        base_rows = [
            _row(f"{10000 + i}", f"City{i}", f"S{i}", f"State {i}", "", "Acme", i + 1)
            for i in range(30)
        ]
        rows = workflow_server._mirror_top_states(base_rows, {}, {})
        self.assertEqual(len(rows), 30, "every state must survive, not just a top-15 cut")
        self.assertIn("S0", {r["state"] for r in rows})


class MirrorTopCitiesMetricsTests(unittest.TestCase):
    def test_population_is_deduped_per_zip_before_summing(self) -> None:
        # Same city, two zips, each fanned out across two brands - population
        # must be counted once per zip, not once per (zip, brand) row.
        base_rows = [
            _row("10001", "New York", "NY", "New York", "New York County", "Domino's", 2, population=50000, median_household_income=90000),
            _row("10001", "New York", "NY", "New York", "New York County", "Pizza Hut", 1, population=50000, median_household_income=90000),
            _row("10002", "New York", "NY", "New York", "New York County", "Domino's", 1, population=30000, median_household_income=70000),
        ]
        rows = workflow_server._mirror_top_cities(base_rows, main_brands=["Domino's"], competitor_brands=["Pizza Hut"])
        self.assertEqual(len(rows), 1)
        ny_city = rows[0]
        self.assertEqual(ny_city["city"], "New York")
        self.assertEqual(ny_city["locations"], 2)  # 2 distinct zips
        self.assertEqual(ny_city["city_population"], 80000)  # 50000 + 30000, not tripled
        self.assertEqual(ny_city["median_household_income"], 80000)  # avg(90000, 70000)
        self.assertEqual(ny_city["main_brand_locations"], 3)  # 2 + 1
        self.assertEqual(ny_city["competitor_brand_locations"], 1)

    def test_city_with_no_population_data_defaults_to_zero(self) -> None:
        base_rows = [_row("10001", "Somewhere", "NY", "New York", "", "Domino's", 1)]
        rows = workflow_server._mirror_top_cities(base_rows)
        self.assertEqual(rows[0]["city_population"], 0)
        self.assertEqual(rows[0]["median_household_income"], 0)


class TopStatesCitiesQuerySourceContractTests(unittest.TestCase):
    """Source-contract checks (matching the existing test_reporting_cache.py
    convention) for the live-BigQuery path, since the mirror-path tests
    above can't exercise actual SQL."""

    def test_top_states_query_includes_median_income_and_brand_split_columns(self) -> None:
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("AS median_household_income", source)
        self.assertIn("main_brand_locations", source)
        self.assertIn("competitor_brand_locations", source)
        self.assertIn("AVG(median_household_income) AS state_income", source)

    def test_top_cities_query_joins_deduped_population_and_income(self) -> None:
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("AS city_population", source)
        self.assertIn("SUM(population) AS city_pop, AVG(median_household_income) AS city_income", source)

    def test_zip_base_fallback_path_has_matching_columns(self) -> None:
        # The pre-bootstrap "zip_base" fallback (no brand/listing data yet)
        # must still return the same column shape the frontend expects, so
        # renderSimpleTable() doesn't render "undefined" for a fresh warehouse.
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("0 AS main_brand_locations", source)
        self.assertIn("0 AS competitor_brand_locations", source)


if __name__ == "__main__":
    unittest.main()
