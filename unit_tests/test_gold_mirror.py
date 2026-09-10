from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache
import whitespace_tool.workflow_server as workflow_server


ZIP_BRAND_ROWS = [
    {"zip_code": "78701", "state_code": "TX", "state_name": "Texas", "county": "Travis", "city_name": "Austin",
     "population": 50000, "median_household_income": 70000, "median_age": 33, "latitude": 30.27, "longitude": -97.74,
     "brand_name": "Acme", "location_count": 2, "last_observed_at": "2026-01-01T00:00:00+00:00"},
    {"zip_code": "78701", "state_code": "TX", "state_name": "Texas", "county": "Travis", "city_name": "Austin",
     "population": 50000, "median_household_income": 70000, "median_age": 33, "latitude": 30.27, "longitude": -97.74,
     "brand_name": "Rival", "location_count": 1, "last_observed_at": "2026-01-02T00:00:00+00:00"},
    {"zip_code": "78702", "state_code": "TX", "state_name": "Texas", "county": "Travis", "city_name": "Austin",
     "population": 30000, "median_household_income": 60000, "median_age": 30, "latitude": 30.28, "longitude": -97.75,
     "brand_name": "Acme", "location_count": 1, "last_observed_at": "2026-01-03T00:00:00+00:00"},
    {"zip_code": "64108", "state_code": "MO", "state_name": "Missouri", "county": "Jackson", "city_name": "Kansas City",
     "population": 20000, "median_household_income": 55000, "median_age": 35, "latitude": 39.09, "longitude": -94.58,
     "brand_name": "Rival", "location_count": 3, "last_observed_at": "2026-01-04T00:00:00+00:00"},
    {"zip_code": "78703", "state_code": "TX", "state_name": "Texas", "county": "Travis", "city_name": "Austin",
     "population": 10000, "median_household_income": 50000, "median_age": 40, "latitude": 30.29, "longitude": -97.76,
     "brand_name": None, "location_count": 0, "last_observed_at": None},
]

LOCATION_ROWS = [
    {"listing_id": "l1", "business_id": "b1", "brand": "Acme", "name": "Acme Store 1", "address": "1 Main", "city_name": "Austin",
     "state_code": "TX", "state_name": "Texas", "county": "Travis", "zip_code": "78701", "phone_number": None,
     "latitude": 30.27, "longitude": -97.74, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-01T00:00:00+00:00",
     "population": 50000, "median_household_income": 70000, "median_age": 33},
    {"listing_id": "l2", "business_id": "b1", "brand": "Acme", "name": "Acme Store 2", "address": "2 Main", "city_name": "Austin",
     "state_code": "TX", "state_name": "Texas", "county": "Travis", "zip_code": "78701", "phone_number": None,
     "latitude": 30.27, "longitude": -97.74, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-01T00:00:00+00:00",
     "population": 50000, "median_household_income": 70000, "median_age": 33},
    {"listing_id": "l3", "business_id": "b2", "brand": "Rival", "name": "Rival Store 1", "address": "3 Main", "city_name": "Austin",
     "state_code": "TX", "state_name": "Texas", "county": "Travis", "zip_code": "78701", "phone_number": None,
     "latitude": 30.27, "longitude": -97.74, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-02T00:00:00+00:00",
     "population": 50000, "median_household_income": 70000, "median_age": 33},
    {"listing_id": "l4", "business_id": "b1", "brand": "Acme", "name": "Acme Store 3", "address": "4 Elm", "city_name": "Austin",
     "state_code": "TX", "state_name": "Texas", "county": "Travis", "zip_code": "78702", "phone_number": None,
     "latitude": 30.28, "longitude": -97.75, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-03T00:00:00+00:00",
     "population": 30000, "median_household_income": 60000, "median_age": 30},
    {"listing_id": "l5", "business_id": "b2", "brand": "Rival", "name": "Rival Store 2", "address": "5 Oak", "city_name": "Kansas City",
     "state_code": "MO", "state_name": "Missouri", "county": "Jackson", "zip_code": "64108", "phone_number": None,
     "latitude": 39.09, "longitude": -94.58, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-04T00:00:00+00:00",
     "population": 20000, "median_household_income": 55000, "median_age": 35},
    {"listing_id": "l6", "business_id": "b2", "brand": "Rival", "name": "Rival Store 3", "address": "6 Oak", "city_name": "Kansas City",
     "state_code": "MO", "state_name": "Missouri", "county": "Jackson", "zip_code": "64108", "phone_number": None,
     "latitude": 39.09, "longitude": -94.58, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-04T00:00:00+00:00",
     "population": 20000, "median_household_income": 55000, "median_age": 35},
    {"listing_id": "l7", "business_id": "b2", "brand": "Rival", "name": "Rival Store 4", "address": "7 Oak", "city_name": "Kansas City",
     "state_code": "MO", "state_name": "Missouri", "county": "Jackson", "zip_code": "64108", "phone_number": None,
     "latitude": 39.09, "longitude": -94.58, "coordinate_source": "source_listing", "coordinate_confidence": 1.0,
     "country": "United States", "last_observed_at": "2026-01-04T00:00:00+00:00",
     "population": 20000, "median_household_income": 55000, "median_age": 35},
]

BUSINESS_ROWS = [{"business_id": "b1", "name": "Acme"}, {"business_id": "b2", "name": "Rival"}]


class GoldMirrorStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_mirror_status_is_none_before_first_sync(self) -> None:
        self.assertIsNone(sqlite_cache.get_mirror_status())

    def test_replace_gold_mirror_populates_status_and_tables(self) -> None:
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS, LOCATION_ROWS, BUSINESS_ROWS)
        status = sqlite_cache.get_mirror_status()
        self.assertIsNotNone(status)
        self.assertEqual(status["zip_brand_rows"], 5)
        self.assertEqual(status["location_rows"], 7)
        self.assertEqual(status["business_rows"], 2)

    def test_replace_gold_mirror_is_a_full_replace_not_an_append(self) -> None:
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS, LOCATION_ROWS, BUSINESS_ROWS)
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS[:1], LOCATION_ROWS[:1], BUSINESS_ROWS[:1])
        status = sqlite_cache.get_mirror_status()
        self.assertEqual(status["zip_brand_rows"], 1)
        self.assertEqual(status["location_rows"], 1)

    def test_geo_filtered_fetch(self) -> None:
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS, LOCATION_ROWS, BUSINESS_ROWS)
        tx_rows = sqlite_cache.fetch_mirror_zip_brand_activity(state="TX")
        self.assertEqual({r["zip_code"] for r in tx_rows}, {"78701", "78702", "78703"})
        mo_rows = sqlite_cache.fetch_mirror_zip_brand_activity(state="MO")
        self.assertEqual({r["zip_code"] for r in mo_rows}, {"64108"})
        empty = sqlite_cache.fetch_mirror_zip_brand_activity(state="CA")
        self.assertEqual(empty, [])

    def test_brand_filtered_location_fetch(self) -> None:
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS, LOCATION_ROWS, BUSINESS_ROWS)
        acme_only = sqlite_cache.fetch_mirror_reporting_locations_by_brand(["Acme"])
        self.assertEqual(len(acme_only), 3)
        everything = sqlite_cache.fetch_mirror_reporting_locations_by_brand([])
        self.assertEqual(len(everything), 7)


class GoldMirrorReportingTests(unittest.TestCase):
    """Full pipeline: seed the SQLite mirror, then verify
    _reporting_data_from_mirror() reproduces the exact same aggregation
    semantics as the BigQuery totals_query/top_states_query/top_cities_query/
    brand_query/gap_query/data_quality_query - worked out by hand against
    a small, fully-specified dataset."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()
        sqlite_cache.replace_gold_mirror(ZIP_BRAND_ROWS, LOCATION_ROWS, BUSINESS_ROWS)

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def _fetch(self, **overrides):
        params = dict(
            main_brands=[], competitor_brands=[], selected_brands=[],
            state_filter="", county_filter="", city_filter="", zip_filter="",
            min_population=None, min_income=None, max_median_age=None,
        )
        params.update(overrides)
        return workflow_server._reporting_data_from_mirror(
            params["main_brands"], params["competitor_brands"], params["selected_brands"],
            params["state_filter"], params["county_filter"], params["city_filter"], params["zip_filter"],
            params["min_population"], params["min_income"], params["max_median_age"],
        )

    def test_synced_but_empty_mirror_returns_empty_shaped_data_not_none(self) -> None:
        # A genuinely empty dataset (fresh project, zero listings) that HAS
        # been synced must be treated as a real (empty) answer, not a
        # trigger to fall back to BigQuery.
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sqlite_cache, "DB_PATH", Path(tmp) / "empty.db"):
                sqlite_cache.replace_gold_mirror([], [], [])
                result = workflow_server._reporting_data_from_mirror([], [], [], "", "", "", "", None, None, None)
        self.assertIsNotNone(result)
        self.assertEqual(result["totals"]["total_zips"], 0)
        self.assertEqual(result["map_records"], [])

    def test_returns_none_when_never_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sqlite_cache, "DB_PATH", Path(tmp) / "unsynced.db"):
                self.assertIsNone(workflow_server._reporting_data_from_mirror([], [], [], "", "", "", "", None, None, None))

    def test_totals_match_hand_computed_values(self) -> None:
        result = self._fetch()
        self.assertEqual(result["totals"], {
            "total_states": 2, "total_zips": 4, "total_brands": 2, "total_listings": 7,
            "total_stores": 7,
            "active_market_locations": 3, "active_brand_states": 2, "active_brand_cities": 2,
            "total_locations": 4, "total_cities": 2, "gap_zips": 1, "last_updated": "2026-01-04T00:00:00+00:00",
        })

    def test_top_states_grain_and_population_dedup(self) -> None:
        result = self._fetch()
        by_state = {row["state"]: row for row in result["top_states"]}
        self.assertEqual(by_state["TX"]["locations"], 3)
        self.assertEqual(by_state["TX"]["cities"], 1)
        self.assertEqual(by_state["TX"]["brands"], 2)
        # 50000 (78701) + 30000 (78702) + 10000 (78703) - each zip's population
        # counted once despite 78701 appearing twice (Acme + Rival rows).
        self.assertEqual(by_state["TX"]["state_population"], 90000)
        self.assertEqual(by_state["MO"]["locations"], 1)
        self.assertEqual(by_state["MO"]["state_population"], 20000)

    def test_top_cities(self) -> None:
        result = self._fetch()
        by_city = {row["city"]: row for row in result["top_cities"]}
        self.assertEqual(by_city["Austin"]["locations"], 3)
        self.assertEqual(by_city["Kansas City"]["locations"], 1)

    def test_brand_query_sums_location_count_across_zips(self) -> None:
        result = self._fetch()
        by_brand = {row["brand"]: row for row in result["brands"]}
        self.assertEqual(by_brand["Acme"]["locations"], 3)
        self.assertEqual(by_brand["Acme"]["zips"], 2)
        self.assertEqual(by_brand["Rival"]["locations"], 4)
        self.assertEqual(by_brand["Rival"]["zips"], 2)
        # Sorted by locations desc.
        self.assertEqual([row["brand"] for row in result["brands"]], ["Rival", "Acme"])

    def test_filter_options_are_global_not_scoped_to_geo_filter(self) -> None:
        result = self._fetch(state_filter="MO")
        self.assertEqual(result["filter_options"]["states"], ["MO", "TX"])
        self.assertEqual(result["filter_options"]["brands"], ["Acme", "Rival"])

    def test_gap_analysis_classifies_and_orders_zips_correctly(self) -> None:
        result = self._fetch(main_brands=["Acme"], competitor_brands=["Rival"])
        gaps_by_zip = {row["zip_code"]: row for row in result["raw_whitespace"]}
        self.assertEqual(gaps_by_zip["78701"]["whitespace_type"], "COMPETITIVE_MARKET")
        self.assertEqual(gaps_by_zip["78701"]["competition_level"], "Moderate")
        self.assertEqual(gaps_by_zip["78702"]["whitespace_type"], "SUBJECT_PRESENT")
        self.assertEqual(gaps_by_zip["64108"]["whitespace_type"], "COMPETITOR_WHITESPACE")
        self.assertEqual(gaps_by_zip["64108"]["competition_level"], "High")
        self.assertEqual(gaps_by_zip["78703"]["whitespace_type"], "OPEN_WHITESPACE")
        # Sorted by competitor_stores desc, then population desc.
        self.assertEqual([row["zip_code"] for row in result["raw_whitespace"]], ["64108", "78701", "78702", "78703"])

    def test_data_quality_over_all_listings_when_no_brand_filter(self) -> None:
        result = self._fetch()
        self.assertEqual(result["data_quality_row"]["total_rows"], 7)
        self.assertEqual(result["data_quality_row"]["with_coordinates"], 7)
        self.assertEqual(result["data_quality_row"]["with_zip"], 7)
        self.assertEqual(result["data_quality_row"]["distinct_rows"], 7)
        self.assertEqual(result["data_quality_row"]["last_observed_at"], "2026-01-04T00:00:00+00:00")

    def test_map_and_sample_records_respect_brand_filter(self) -> None:
        result = self._fetch(selected_brands=["Acme"])
        self.assertEqual({r["brand"] for r in result["map_records"]}, {"Acme"})
        self.assertEqual(len(result["map_records"]), 3)

    def test_map_records_include_country_for_non_us_marker_coloring(self) -> None:
        # 2026-09-10: the non-US marker coloring feature (ui/js/reporting.js)
        # colors a map marker state-primary/country-secondary, which requires
        # `country` to actually survive the mirror round trip - not just be
        # present in the BigQuery map_query SELECT list (already true, see
        # workflow_server.py's map_query). Every LOCATION_ROWS fixture row
        # carries country="United States", so every map_records row returned
        # here must carry it straight through, unmangled.
        result = self._fetch()
        self.assertTrue(result["map_records"], "expected at least one map record")
        for record in result["map_records"]:
            self.assertEqual(record["country"], "United States")

    def test_present_states_reflects_full_filtered_base_set(self) -> None:
        result = self._fetch()
        self.assertEqual(result["present_states"], {"TX", "MO"})

    def test_full_reporting_summary_uses_mirror_when_synced(self) -> None:
        result = workflow_server.reporting_summary({})
        self.assertEqual(result["reporting_cache"], "mirror")
        self.assertEqual(result["source_table"], "sqlite_gold_mirror")
        self.assertEqual(result["totals"]["total_zips"], 4)


class SyncGoldMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_path_patch.start()

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_sync_gold_mirror_reads_gold_views_and_writes_the_mirror(self) -> None:
        class FakeJob:
            def __init__(self, rows):
                self._rows = rows

            def result(self):
                return self._rows

        class FakeClient:
            def query(self, sql):
                if "vw_zip_brand_activity" in sql:
                    return FakeJob(ZIP_BRAND_ROWS)
                if "vw_reporting_locations" in sql:
                    return FakeJob(LOCATION_ROWS)
                if ".businesses`" in sql:
                    return FakeJob(BUSINESS_ROWS)
                raise AssertionError(f"unexpected query: {sql}")

        with patch.object(workflow_server, "_medallion_settings", return_value=("proj", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=FakeClient()):
                result = workflow_server.sync_gold_mirror()

        self.assertEqual(result, {"zip_brand_rows": 5, "location_rows": 7, "business_rows": 2})
        status = sqlite_cache.get_mirror_status()
        self.assertEqual(status["zip_brand_rows"], 5)

    def test_rebuild_gold_and_mirror_syncs_after_building_gold(self) -> None:
        calls: list[str] = []

        def fake_gold():
            calls.append("gold")
            return {"views": ["a"]}

        # force is passed through so the deliberate clear paths can swap in
        # an empty mirror (see sync_gold_mirror's empty-swap guard).
        def fake_sync(force: bool = False):
            calls.append(f"mirror(force={force})")
            return {"zip_brand_rows": 0, "location_rows": 0, "business_rows": 0}

        with patch.object(workflow_server, "build_gold_layer", side_effect=fake_gold):
            with patch.object(workflow_server, "sync_gold_mirror", side_effect=fake_sync):
                result = workflow_server._rebuild_gold_and_mirror()
                forced = workflow_server._rebuild_gold_and_mirror(force_mirror=True)

        self.assertEqual(calls, ["gold", "mirror(force=False)", "gold", "mirror(force=True)"])
        self.assertIn("mirror", forced)
        self.assertEqual(result["gold"]["views"], ["a"])

    def test_rebuild_gold_and_mirror_survives_a_mirror_sync_failure(self) -> None:
        with patch.object(workflow_server, "build_gold_layer", return_value={"views": []}):
            with patch.object(workflow_server, "sync_gold_mirror", side_effect=RuntimeError("no bigquery access")):
                result = workflow_server._rebuild_gold_and_mirror()

        self.assertIn("error", result["mirror"])
        self.assertEqual(result["gold"]["views"], [])


if __name__ == "__main__":
    unittest.main()


def test_a_collapse_in_either_collection_blocks_the_swap():
    """The guard used to require BOTH collections to be empty:

        if had_real_data and not force and not zip_brand_rows and not location_rows

    vw_zip_brand_activity is a LEFT JOIN off the ZIP reference, so it returns
    ~41.5k rows whether or not any brand has activity - it is never empty.
    That made the condition unreachable for locations, so a gold read landing
    during a silver rebuild's drop-then-recreate window swapped 0 locations
    straight in. Observed live: 13,803 location rows replaced by 0 while
    41,585 zip rows "looked fine", after which reporting served 0 listings and
    0 brands as a legitimate answer.
    """
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.sync_gold_mirror)
    # The unreachable conjunction must be gone from the CODE (it survives in
    # the comment explaining why, so match the whole statement).
    assert "if had_real_data and not force and not zip_brand_rows and not location_rows:" not in source
    # Each collection is judged on its own collapse from non-empty to empty.
    assert "if previous_locations > 0 and not location_rows:" in source
    assert "if previous_zip_brand > 0 and not zip_brand_rows:" in source
    assert "if had_real_data and not force and collapsed:" in source
    # Row count alone cannot tell a healthy zip-brand read from an empty one.
    assert 'zip_brand_has_activity = any(row.get("brand_name") for row in zip_brand_rows)' in source
    # A deliberate clear must still be able to empty the mirror.
    assert "not force" in source


def test_a_slow_sync_cannot_commit_its_empty_result_over_a_newer_good_mirror():
    """The three gold reads can take over a minute. Another sync (or a manual
    rebuild) can land a good mirror in that window, and committing this
    thread's older empty result over it is a lost update - which is how a
    freshly rebuilt 13,803-row mirror went back to 0 about sixty seconds
    later. The first guard compares against the mirror at READ time; this one
    compares against it at WRITE time, which is the state that matters."""
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.sync_gold_mirror)
    swap_at = source.index("replace_gold_mirror(zip_brand_rows, location_rows, business_rows)")
    recheck = source[:swap_at]
    assert "if not force and not location_rows:" in recheck
    assert "current = get_mirror_status()" in recheck
    assert "gold_mirror_sync_stale_empty_write" in recheck
    # A deliberate clear must still be able to empty the mirror.
    assert recheck.index("if not force and not location_rows:") < swap_at
