from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache
from whitespace_tool.geo_enrichment import (
    detect_and_fix_inverted_coords,
    detect_hierarchy_conflict,
    enrich_raw_listing_row,
    find_nearest_city_and_zip,
    find_nearest_worldwide_city,
    haversine_distance_km,
    is_us_land_coordinate,
    lookup_worldwide_city,
    lookup_zip_and_coords_by_city_state,
    normalize_city_text,
    normalize_state_code,
    resolve_location_hierarchy,
)


class GeoEnrichmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test_geo.db")
        self._db_path_patch.start()
        sqlite_cache.init_sqlite_cache()
        # Seed test reference ZIPs and cities
        sqlite_cache.cache_zipcodes([
            {
                "zip_code": "33311",
                "city_name": "Fort Lauderdale city",
                "county": "Broward County",
                "state_code": "FL",
                "state_name": "Florida",
                "latitude": 26.144,
                "longitude": -80.173,
                "population": 73000,
            },
            {
                "zip_code": "33710",
                "city_name": "St. Petersburg city",
                "county": "Pinellas County",
                "state_code": "FL",
                "state_name": "Florida",
                "latitude": 27.789,
                "longitude": -82.730,
                "population": 34000,
            },
            {
                "zip_code": "94103",
                "city_name": "San Francisco city",
                "county": "San Francisco County",
                "state_code": "CA",
                "state_name": "California",
                "latitude": 37.773,
                "longitude": -122.411,
                "population": 28000,
            },
            {
                "zip_code": "10001",
                "city_name": "New York city",
                "county": "New York County",
                "state_code": "NY",
                "state_name": "New York",
                "latitude": 40.750,
                "longitude": -73.997,
                "population": 24000,
            },
        ])
        # Seed test worldwide cities in cachedb
        sqlite_cache.cache_worldwide_cities([
            {
                "country_code": "CA",
                "country_name": "Canada",
                "state_name": "Ontario",
                "state_code": "ON",
                "district": "Toronto",
                "city": "Toronto",
                "town": "Downtown",
                "zip_code": "M5V 2T6",
                "latitude": 43.653,
                "longitude": -79.383,
            },
            {
                "country_code": "GB",
                "country_name": "United Kingdom",
                "state_name": "Greater London",
                "state_code": "ENG",
                "district": "Westminster",
                "city": "London",
                "town": "Soho",
                "zip_code": "SW1A 1AA",
                "latitude": 51.507,
                "longitude": -0.127,
            },
            {
                "country_code": "FR",
                "country_name": "France",
                "state_name": "Ile-de-France",
                "state_code": "IDF",
                "district": "Paris",
                "city": "Paris",
                "town": "Montmartre",
                "zip_code": "75001",
                "latitude": 48.856,
                "longitude": 2.352,
            },
        ])

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_normalize_state_code(self) -> None:
        self.assertEqual(normalize_state_code("California"), "CA")
        self.assertEqual(normalize_state_code("fl"), "FL")
        self.assertEqual(normalize_state_code("New York"), "NY")
        self.assertEqual(normalize_state_code("Puerto Rico"), "PR")
        self.assertEqual(normalize_state_code("TX"), "TX")
        self.assertEqual(normalize_state_code("UnknownState"), "")

    def test_normalize_city_text(self) -> None:
        self.assertEqual(normalize_city_text("City of Dallas"), "dallas")
        self.assertEqual(normalize_city_text("St. Petersburg"), "saint petersburg")
        self.assertEqual(normalize_city_text("Ft. Lauderdale"), "fort lauderdale")
        self.assertEqual(normalize_city_text("Town of Miami"), "miami")
        self.assertEqual(normalize_city_text("N.Y.C."), "new york")
        self.assertEqual(normalize_city_text("San Francisco, CA"), "san francisco ca")

    def test_detect_and_fix_inverted_coords(self) -> None:
        # Standard US coords: lat 37.77, lon -122.41 -> not inverted
        lat, lon, was_inverted = detect_and_fix_inverted_coords(37.77, -122.41)
        self.assertFalse(was_inverted)
        self.assertAlmostEqual(lat, 37.77)
        self.assertAlmostEqual(lon, -122.41)

        # Inverted coords: lat -122.41, lon 37.77 -> inverted!
        lat, lon, was_inverted = detect_and_fix_inverted_coords(-122.41, 37.77)
        self.assertTrue(was_inverted)
        self.assertAlmostEqual(lat, 37.77)
        self.assertAlmostEqual(lon, -122.41)

    def test_is_us_land_coordinate(self) -> None:
        self.assertTrue(is_us_land_coordinate(37.77, -122.41))
        self.assertFalse(is_us_land_coordinate(0.0, 0.0))  # Null Island
        self.assertFalse(is_us_land_coordinate(None, None))
        self.assertFalse(is_us_land_coordinate(85.0, -100.0))  # North pole
        self.assertFalse(is_us_land_coordinate(50.0, 10.0))  # Europe

    def test_haversine_distance(self) -> None:
        # NYC to SF is ~4100km
        dist = haversine_distance_km(40.75, -73.997, 37.773, -122.411)
        self.assertTrue(4000 < dist < 4300)

    def test_ocean_coordinate_snapping_to_nearest_city(self) -> None:
        # Point offshore SF in Pacific Ocean, within the 50km snap cap:
        # lat 37.75, lon -122.9 (~43km from the seeded San Francisco fixture)
        with sqlite_cache.get_db_connection() as conn:
            nearest = find_nearest_city_and_zip(37.75, -122.9, conn)
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest["city_name"], "San Francisco city")
        self.assertEqual(nearest["zip_code"], "94103")
        self.assertLess(nearest["distance_km"], 50.0)

    def test_far_offshore_coordinate_does_not_snap_beyond_50km(self) -> None:
        # A coordinate reliably nearer than 50km should snap (tested above);
        # one further out must not - snapping to a "nearest" match hundreds
        # of km away is not a reliable repair, just whatever was closest
        # among an unrelated set. lat 37.7, lon -123.0 is ~52km from the
        # seeded San Francisco fixture - just over the cap.
        with sqlite_cache.get_db_connection() as conn:
            nearest = find_nearest_city_and_zip(37.7, -123.0, conn)
        self.assertIsNone(nearest)

    def test_lookup_zip_and_coords_by_city_state(self) -> None:
        with sqlite_cache.get_db_connection() as conn:
            # Fuzzy match Ft. Lauderdale -> Fort Lauderdale city
            match = lookup_zip_and_coords_by_city_state("Ft. Lauderdale", "FL", conn)
            self.assertIsNotNone(match)
            self.assertEqual(match["zip_code"], "33311")

            # Fuzzy match St. Petersburg -> St. Petersburg city
            match2 = lookup_zip_and_coords_by_city_state("St. Petersburg", "Florida", conn)
            self.assertIsNotNone(match2)
            self.assertEqual(match2["zip_code"], "33710")

    def test_enrich_raw_listing_row_with_ocean_coords(self) -> None:
        # A listing with coordinates in the ocean off NY coast (lat 40.5, lon -73.2)
        raw_row = {
            "name": "Beachside Cafe",
            "address": "1 Boardwalk",
            "city": "New York",
            "state": "New York",
            "postal_code": "",  # missing ZIP
            "latitude": 40.5,
            "longitude": -73.2,
        }
        with sqlite_cache.get_db_connection() as conn:
            enriched = enrich_raw_listing_row(raw_row, conn)

        self.assertEqual(enriched["state"], "NY")
        # Missing ZIP should be inferred from New York, NY
        self.assertEqual(enriched["postal_code"], "10001")

    def test_enrich_raw_listing_row_with_inverted_coords(self) -> None:
        raw_row = {
            "name": "Bay Area Bites",
            "address": "1 Market St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94103",
            "latitude": -122.411,  # inverted
            "longitude": 37.773,   # inverted
        }
        with sqlite_cache.get_db_connection() as conn:
            enriched = enrich_raw_listing_row(raw_row, conn)

        self.assertAlmostEqual(enriched["latitude"], 37.773)
        self.assertAlmostEqual(enriched["longitude"], -122.411)
        self.assertEqual(enriched.get("__coordinate_fix"), "inversion_corrected")

    def test_find_nearest_worldwide_city(self) -> None:
        # Offshore point near London, within the 50km snap cap: lat 51.45,
        # lon -0.05 (~8km from the seeded London fixture)
        with sqlite_cache.get_db_connection() as conn:
            nearest = find_nearest_worldwide_city(51.45, -0.05, conn, country="United Kingdom")
        self.assertIsNotNone(nearest)
        self.assertEqual(nearest["city"], "London")
        self.assertEqual(nearest["country_code"], "GB")
        self.assertEqual(nearest["zip_code"], "SW1A 1AA")
        self.assertLess(nearest["distance_km"], 50.0)

    def test_far_offshore_worldwide_coordinate_does_not_snap_beyond_50km(self) -> None:
        # lat 51.0, lon 0.1 is ~58km from the seeded London fixture - just
        # over the cap, so it must not snap.
        with sqlite_cache.get_db_connection() as conn:
            nearest = find_nearest_worldwide_city(51.0, 0.1, conn, country="United Kingdom")
        self.assertIsNone(nearest)

    def test_lookup_worldwide_city_from_cache(self) -> None:
        with sqlite_cache.get_db_connection() as conn:
            # Match Toronto by city + country
            toronto = lookup_worldwide_city(city="Toronto", country="Canada", conn=conn)
            self.assertIsNotNone(toronto)
            self.assertEqual(toronto["city"], "Toronto")
            self.assertEqual(toronto["country_code"], "CA")
            self.assertEqual(toronto["zip_code"], "M5V 2T6")

            # Match Soho as town
            soho = lookup_worldwide_city(town="Soho", country="United Kingdom", conn=conn)
            self.assertIsNotNone(soho)
            self.assertEqual(soho["town"], "Soho")
            self.assertEqual(soho["city"], "London")

    def test_resolve_location_hierarchy_worldwide(self) -> None:
        with sqlite_cache.get_db_connection() as conn:
            # Town > City hierarchy match
            res = resolve_location_hierarchy(town="Montmartre", city="Paris", country="France", conn=conn)
            self.assertIsNotNone(res)
            self.assertEqual(res["city"], "Paris")
            self.assertEqual(res["country"], "France")
            self.assertEqual(res["zip_code"], "75001")
            self.assertAlmostEqual(res["latitude"], 48.856)

    def test_enrich_raw_listing_row_worldwide(self) -> None:
        # Listing in UK with coordinates in the ocean near London
        raw_row = {
            "name": "London Thames Bistro",
            "address": "1 River Way",
            "city": "London",
            "country": "United Kingdom",
            "latitude": 51.2,
            "longitude": 0.2,
        }
        with sqlite_cache.get_db_connection() as conn:
            enriched = enrich_raw_listing_row(raw_row, conn)

        self.assertEqual(enriched["country"], "United Kingdom")
        self.assertEqual(enriched["postal_code"], "SW1A 1AA")
        self.assertAlmostEqual(enriched["latitude"], 51.507)

    def test_seed_or_swap_enrichment_cycle(self) -> None:
        # 1. Initial seeding
        cycle_id, count = sqlite_cache.seed_or_swap_enrichment_cycle(["list_1", "list_2", "list_3"])
        self.assertEqual(cycle_id, 1)
        self.assertEqual(count, 3)

        # 2. Claim batch of 2
        batch = sqlite_cache.claim_enrichment_batch(cycle_id, limit=2)
        self.assertEqual(len(batch), 2)
        sqlite_cache.complete_enrichment_claim(batch[0], cycle_id, improved=True)
        sqlite_cache.complete_enrichment_claim(batch[1], cycle_id, improved=False)

        # 3. Claim remaining 1
        batch2 = sqlite_cache.claim_enrichment_batch(cycle_id, limit=2)
        self.assertEqual(len(batch2), 1)
        sqlite_cache.complete_enrichment_claim(batch2[0], cycle_id, improved=False)

        # 4. Base is now exhausted (0 pending). Swapping should graduate improved, and swap failed to new base!
        new_cycle, new_count = sqlite_cache.seed_or_swap_enrichment_cycle(["list_4"])
        self.assertEqual(new_cycle, 2)
        # 2 failed items from cycle 1 + 1 new item ("list_4") = 3
        self.assertEqual(new_count, 3)


    def test_claim_enrichment_batch_does_not_always_pick_the_same_sorted_first_ids(self) -> None:
        # "Fix with AI" was always working the lexicographically-first ids,
        # which concentrated every cycle on whichever brand sorted first.
        # Claiming is randomised now, so across several fresh cycles the
        # first claimed id must not always be the smallest one.
        listing_ids = [f"listing_{index:03d}" for index in range(40)]
        smallest = min(listing_ids)
        first_claims = []
        for _ in range(8):
            cycle_id, _count = sqlite_cache.seed_or_swap_enrichment_cycle(listing_ids)
            batch = sqlite_cache.claim_enrichment_batch(cycle_id, limit=2)
            first_claims.append(batch[0])
            for claimed in batch:
                sqlite_cache.complete_enrichment_claim(claimed, cycle_id, improved=True)
        self.assertTrue(any(claim != smallest for claim in first_claims))


class HierarchyConflictTests(unittest.TestCase):
    """detect_hierarchy_conflict() - a record can carry a ZIP/city/state AND
    lat/lon that disagree with each other (e.g. ZIP says San Francisco but
    the coordinates land near open ocean 50+km away). It must offer both
    readings rather than silently picking or accepting either."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test_hierarchy.db")
        self._db_path_patch.start()
        sqlite_cache.init_sqlite_cache()
        sqlite_cache.cache_zipcodes([{
            "zip_code": "94103",
            "city_name": "San Francisco city",
            "county": "San Francisco County",
            "state_code": "CA",
            "state_name": "California",
            "latitude": 37.773,
            "longitude": -122.411,
            "population": 28000,
        }])

    def tearDown(self) -> None:
        self._db_path_patch.stop()

    def test_agreeing_zip_and_coordinates_report_no_conflict(self) -> None:
        with sqlite_cache.get_db_connection() as conn:
            conflict = detect_hierarchy_conflict("94103", "United States", 37.773, -122.411, conn)
        self.assertIsNone(conflict)

    def test_disagreeing_zip_and_coordinates_offer_both_readings(self) -> None:
        # lat 37.7, lon -123.0 is ~52km from the seeded 94103 ZIP - just
        # over the 50km cap, so it's a genuine conflict, not measurement
        # noise.
        with sqlite_cache.get_db_connection() as conn:
            conflict = detect_hierarchy_conflict("94103", "United States", 37.7, -123.0, conn)
        self.assertIsNotNone(conflict)
        self.assertGreater(conflict["distance_km"], 50)
        self.assertEqual(conflict["zip_based"]["city"], "San Francisco city")
        self.assertEqual(conflict["zip_based"]["zip_code"], "94103")
        # coordinate_based comes from find_nearest_city_and_zip() on the
        # row's own lat/lon - with only one seeded ZIP and a >50km gap, no
        # nearest match exists either, so this side is correctly None
        # rather than a fabricated guess.
        self.assertIsNone(conflict["coordinate_based"])

    def test_missing_zip_or_coordinates_is_not_a_conflict(self) -> None:
        with sqlite_cache.get_db_connection() as conn:
            self.assertIsNone(detect_hierarchy_conflict("", "United States", 37.7, -123.0, conn))
            self.assertIsNone(detect_hierarchy_conflict("94103", "United States", None, None, conn))

    def test_unknown_zip_is_not_a_conflict(self) -> None:
        # A ZIP with no reference data can't be compared against anything -
        # absence of evidence isn't evidence of a conflict.
        with sqlite_cache.get_db_connection() as conn:
            self.assertIsNone(detect_hierarchy_conflict("00000", "United States", 37.7, -123.0, conn))
