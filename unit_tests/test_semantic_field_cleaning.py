"""Per-column-type validation, repair and clearing.

The rule: if a column's name or type is commonly understandable and the value
inside it is not what that kind of column should hold, clear it, fix it, and
leave it for enrichment. Before this, only numeric/date registry fields were
checked - junk in a phone/email/URL/percent column reached the warehouse
verbatim, and unmapped or custom columns were never checked at all.
"""

from __future__ import annotations

import unittest

from whitespace_tool.data_validation.semantic_types import (
    CLEARED, GEO_OWNED_FIELDS, OK, REPAIRED, clean_field_value, clean_record,
    infer_semantic_kind, is_geo_owned,
)
from whitespace_tool.normalization import normalize_location


def _mapper(**field_overrides):
    fields = {
        "name": "Name", "address": "Addr", "city": "City", "state": "State",
        "postal_code": "Zip", "country": "Country",
    }
    fields.update(field_overrides)
    return {"brand": "Acme", "business_id": "b1", "source_name": "s.csv",
            "source_type": "csv", "fields": fields}


def _base_row(**extra):
    row = {"Name": "Store 1", "Addr": "1 Main", "City": "Austin", "State": "TX",
           "Zip": "78701", "Country": "United States"}
    row.update(extra)
    return row


class GeoOwnershipTests(unittest.TestCase):
    """The generic cleaner must never touch a field geo enrichment owns.

    Each of these has dedicated logic that is strictly smarter than a regex:
    clean_zip() keeps non-US alphanumeric codes, normalize_state_code()
    resolves names/codes/misspellings, lookup_cached_city_state() does
    city<->ZIP<->state resolution from cached reference data, and
    detect_and_fix_inverted_coords() SWAPS transposed pairs rather than
    discarding them. A generic range check would destroy the very input
    those repairs work from.
    """

    def test_every_geo_field_passes_through_untouched(self) -> None:
        for column, value in [
            ("postal_code", "SW1A1AA"),   # non-US postal code, not a bad ZIP
            ("zip_code", "78701"),
            ("city", "Austin"), ("city_name", "austin"),
            ("state", "tx"), ("state_code", "Texas"),
            ("country", "United States"), ("country_code", "us"),
            ("latitude", "1000"),          # out of range, but the swap repair needs it
            ("longitude", "-97.7"),
            ("address", "1 Main St"), ("county", "Travis"),
        ]:
            cleaned, action, kind = clean_field_value(column, value)
            self.assertEqual(cleaned, value, column)
            self.assertEqual(action, OK, column)
            self.assertEqual(kind, "geo", column)

    def test_an_out_of_range_coordinate_is_never_cleared_here(self) -> None:
        # Inverted coordinates present as an out-of-range latitude. Clearing
        # it would throw away the data detect_and_fix_inverted_coords() needs
        # to swap the pair back.
        self.assertEqual(clean_field_value("latitude", "-97.74")[0], "-97.74")
        self.assertEqual(clean_field_value("longitude", "30.27")[0], "30.27")

    def test_geo_ownership_is_case_and_separator_insensitive(self) -> None:
        for variant in ("Postal Code", "POSTAL_CODE", "postal-code", "Zip Code", "State Code"):
            self.assertTrue(is_geo_owned(variant), variant)

    def test_non_geo_fields_are_not_geo_owned(self) -> None:
        for column in ("phone_number", "email", "annual_revenue", "ratings", "loyalty_tier"):
            self.assertFalse(is_geo_owned(column), column)
        self.assertNotIn("phone_number", GEO_OWNED_FIELDS)


class SemanticKindInferenceTests(unittest.TestCase):
    def test_column_name_wins_over_a_vague_declared_type(self) -> None:
        # The registry declares 25 of 41 fields as plain "string", so the
        # declared type tells us almost nothing; the name is what identifies
        # the column.
        self.assertEqual(infer_semantic_kind("phone_number", "string"), "phone")
        self.assertEqual(infer_semantic_kind("website_url", "string"), "url")
        self.assertEqual(infer_semantic_kind("annual_revenue", "string"), "money")

    def test_declared_type_is_used_when_the_name_says_nothing(self) -> None:
        self.assertEqual(infer_semantic_kind("xyz_column", "integer"), "count")
        self.assertEqual(infer_semantic_kind("xyz_column", "date"), "date")
        self.assertEqual(infer_semantic_kind("xyz_column", None), "text")

    def test_common_column_names_are_understood(self) -> None:
        for column, expected in [
            ("contact_number", "phone"), ("fax", "phone"), ("e_mail", "email"),
            ("homepage", "url"), ("google_maps_link", "url"),
            ("occupancy_percent", "percent"), ("conversion_pct", "percent"),
            ("star_rating", "rating"), ("foot_traffic_score", "rating"),
            ("monthly_sales", "money"), ("rental_cost", "money"), ("lease_cost", "money"),
            ("seating_capacity", "count"), ("daily_footfall", "count"),
            ("founded_year", "year"), ("opening_date", "date"),
            ("created_at", "timestamp"), ("is_active", "boolean"),
        ]:
            self.assertEqual(infer_semantic_kind(column), expected, column)


class ValueRepairTests(unittest.TestCase):
    def test_placeholder_values_are_cleared_in_every_kind_of_column(self) -> None:
        # Stored verbatim these look like real data and defeat every
        # completeness metric downstream.
        for placeholder in ("N/A", "n/a", "NULL", "none", "-", "--", "unknown",
                            "not available", "TBD", "#N/A", "(blank)", "?"):
            value, action, _ = clean_field_value("loyalty_tier", placeholder)
            self.assertIsNone(value, placeholder)
            self.assertEqual(action, CLEARED, placeholder)

    def test_values_that_can_be_fixed_are_fixed_not_discarded(self) -> None:
        for column, raw, expected in [
            ("phone_number", "(512) 555-1234", "5125551234"),
            ("phone_number", "+1 512 555 1234", "+15125551234"),
            ("email", "  BOB@Example.COM ", "bob@example.com"),
            ("website_url", "example.com/store", "https://example.com/store"),
            ("annual_revenue", "$1,250,000.50", 1250000.5),
            ("seating_capacity", "1,200", 1200),
            ("occupancy_percent", "87%", 87.0),
            ("founded_year", "1998", 1998),
            ("is_active", "Yes", True),
            ("store_name", "  Downtown   Store ", "Downtown Store"),
        ]:
            value, action, _ = clean_field_value(column, raw)
            self.assertEqual(value, expected, column)
            self.assertEqual(action, REPAIRED, column)

    def test_values_that_cannot_be_that_kind_are_cleared(self) -> None:
        # "if you are so sure a column can't hold a string, just clear it and
        # try to enrich" - the generalized form of that instruction.
        for column, raw in [
            ("phone_number", "Springfield"),
            ("phone_number", "12"),              # too short to be a phone
            ("email", "not-an-email"),
            ("website_url", "just some words"),
            ("annual_revenue", "excellent"),
            ("annual_revenue", "-500"),          # negative money is not real
            ("seating_capacity", "Springfield"),
            ("ratings", "excellent"),
            ("occupancy_percent", "300%"),       # outside 0-100
            ("founded_year", "99999"),
            ("is_active", "maybe"),
            ("notes", "---"),                    # separator noise, no content
        ]:
            value, action, _ = clean_field_value(column, raw)
            self.assertIsNone(value, f"{column}={raw}")
            self.assertEqual(action, CLEARED, f"{column}={raw}")

    def test_a_valid_value_is_left_exactly_as_it_is(self) -> None:
        for column, raw in [("loyalty_tier", "gold"), ("opening_date", "2020-05-01"),
                            ("store_name", "Downtown Store")]:
            value, action, _ = clean_field_value(column, raw)
            self.assertEqual(value, raw, column)
            self.assertEqual(action, OK, column)

    def test_structured_and_none_values_are_passed_through(self) -> None:
        self.assertEqual(clean_field_value("anything", None)[1], OK)
        self.assertEqual(clean_field_value("payload", {"a": 1})[0], {"a": 1})
        self.assertEqual(clean_field_value("payload", [1, 2])[0], [1, 2])

    def test_clean_record_reports_what_it_changed(self) -> None:
        row = {"phone": "N/A", "email": "BOB@X.COM", "loyalty": "gold", "__meta": {"x": 1}}
        cleaned, actions = clean_record(row)
        self.assertIsNone(cleaned["phone"])
        self.assertEqual(cleaned["email"], "bob@x.com")
        self.assertEqual(cleaned["loyalty"], "gold")
        self.assertEqual(cleaned["__meta"], {"x": 1})  # internal key untouched
        self.assertEqual(actions, {"phone": CLEARED, "email": REPAIRED})


class NormalizeLocationIntegrationTests(unittest.TestCase):
    """The cleaning must actually reach the record the warehouse stores."""

    def test_mapped_fields_are_cleaned_on_the_stored_record(self) -> None:
        record = normalize_location(
            _base_row(Phone="N/A", Email="BOB@Example.COM", Web="example.com",
                      Rev="$1,250,000", Stars="excellent"),
            _mapper(phone_number="Phone", email="Email", website_url="Web",
                    annual_revenue="Rev", ratings="Stars"),
            "s.csv", 0)
        self.assertIsNone(record.phone_number)
        self.assertEqual(record.email, "bob@example.com")
        self.assertEqual(record.website_url, "https://example.com")
        self.assertEqual(record.annual_revenue, 1250000.0)
        self.assertIsNone(record.ratings)

    def test_geo_values_survive_normalize_location_untouched(self) -> None:
        # The end-to-end version of GeoOwnershipTests: the older city/ZIP/
        # state features must keep working exactly as before.
        record = normalize_location(_base_row(), _mapper(), "s.csv", 0)
        self.assertEqual(record.postal_code, "78701")
        self.assertEqual(record.city, "Austin")
        self.assertEqual(record.state, "TX")
        self.assertEqual(record.country, "United States")

    def test_cleared_fields_are_recorded_so_enrichment_can_target_them(self) -> None:
        # A silently blank field is indistinguishable from one that was never
        # supplied; recording the list is what makes it enrichable.
        record = normalize_location(
            _base_row(Phone="N/A"), _mapper(phone_number="Phone"), "s.csv", 0)
        self.assertEqual(record.raw["__meta"]["semantically_cleared_fields"], ["phone_number"])

    def test_custom_and_unmapped_columns_are_cleaned_too(self) -> None:
        # Custom fields land in extras (they have no typed column), so they
        # are cleaned by column name exactly like mapped fields.
        record = normalize_location(
            _base_row(loyalty_tier="gold", franchise_phone="(512) 555-1234",
                      opened_year="1998", custom_revenue="$99,000",
                      store_rating="not-a-number", notes="---", junk="N/A"),
            _mapper(), "s.csv", 0)
        extras = record.extras or {}
        self.assertEqual(extras["loyalty_tier"], "gold")
        self.assertEqual(extras["franchise_phone"], "5125551234")
        self.assertEqual(extras["opened_year"], 1998)
        self.assertEqual(extras["custom_revenue"], 99000.0)
        # Values that cannot be what their column means never reach storage.
        for dropped in ("store_rating", "notes", "junk"):
            self.assertNotIn(dropped, extras, dropped)

    def test_a_row_with_bad_optional_values_still_saves(self) -> None:
        # Clearing, not rejecting: the row's good fields must survive.
        record = normalize_location(
            _base_row(Phone="Springfield", Rev="excellent"),
            _mapper(phone_number="Phone", annual_revenue="Rev"), "s.csv", 0)
        self.assertIsNotNone(record)
        self.assertEqual(record.name, "Store 1")
        self.assertEqual(record.postal_code, "78701")


if __name__ == "__main__":
    unittest.main()
