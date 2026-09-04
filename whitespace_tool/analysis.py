from __future__ import annotations

import math
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import mean, pstdev
from typing import Any

from whitespace_tool.models import LocationRecord, ZipDemographics

FUZZY_ADDRESS_MATCH_THRESHOLD = 0.70
FUZZY_COORDINATE_TOLERANCE = 0.0005


def _dedupe_text(value: object) -> str:
    return str(value or "").strip().casefold()


def _dedupe_coordinate(value: float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.6f}"


def dedupe_location_key(record: LocationRecord) -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
        _dedupe_text(record.brand),
        _dedupe_text(record.location_id),
        _dedupe_text(record.name),
        _dedupe_text(record.address),
        _dedupe_text(record.city),
        _dedupe_text(record.state),
        _dedupe_text(record.zip5),
        _dedupe_coordinate(record.latitude),
        _dedupe_coordinate(record.longitude),
    )


def _fuzzy_bucket(record: LocationRecord) -> tuple[str, str, str, str]:
    return (
        _dedupe_text(record.brand),
        _dedupe_text(record.state),
        _dedupe_text(record.zip5),
        _dedupe_text(record.city),
    )


def _addresses_match(left: LocationRecord, right: LocationRecord) -> bool:
    left_address = _dedupe_text(left.address)
    right_address = _dedupe_text(right.address)
    if not left_address or not right_address:
        return False
    return SequenceMatcher(None, left_address, right_address).ratio() >= FUZZY_ADDRESS_MATCH_THRESHOLD


def _coordinates_match(left: LocationRecord, right: LocationRecord) -> bool:
    if left.latitude is None or left.longitude is None or right.latitude is None or right.longitude is None:
        return False
    return (
        abs(left.latitude - right.latitude) <= FUZZY_COORDINATE_TOLERANCE
        and abs(left.longitude - right.longitude) <= FUZZY_COORDINATE_TOLERANCE
    )


def is_fuzzy_duplicate_location(left: LocationRecord, right: LocationRecord) -> bool:
    return _fuzzy_bucket(left) == _fuzzy_bucket(right) and _addresses_match(left, right) and _coordinates_match(left, right)


def dedupe_locations(records: list[LocationRecord]) -> list[LocationRecord]:
    seen: set[tuple[str, str, str, str, str, str, str, str, str]] = set()
    fuzzy_buckets: dict[tuple[str, str, str, str], list[LocationRecord]] = defaultdict(list)
    deduped: list[LocationRecord] = []
    for record in records:
        key = dedupe_location_key(record)
        if key in seen:
            continue

        bucket = _fuzzy_bucket(record)
        if any(is_fuzzy_duplicate_location(existing, record) for existing in fuzzy_buckets[bucket]):
            continue

        seen.add(key)
        fuzzy_buckets[bucket].append(record)
        deduped.append(record)
    return deduped


def _geo_allowed(zip_code: str, demographics: ZipDemographics, geography: dict[str, Any]) -> bool:
    if geography.get("type", "us") == "us":
        return True
    if geography["type"] == "zip_prefixes":
        return any(zip_code.startswith(str(prefix)) for prefix in geography["values"])
    raise ValueError(f"Unsupported geography type: {geography['type']}")


def _metric_value(demo: ZipDemographics, metric: str) -> float | None:
    return getattr(demo, metric, None)


def _profile_stats(
    subject_zips: set[str],
    demographics: dict[str, ZipDemographics],
    metrics: list[str],
) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for metric in metrics:
        values = [
            value
            for zip_code in subject_zips
            if (value := _metric_value(demographics[zip_code], metric)) is not None
        ]
        if not values:
            raise ValueError(f"No subject ZIP data found for similarity metric: {metric}")
        spread = pstdev(values) or 1.0
        stats[metric] = (mean(values), spread)
    return stats


def _distance(demo: ZipDemographics, stats: dict[str, tuple[float, float]]) -> float | None:
    total = 0.0
    used = 0
    for metric, (center, spread) in stats.items():
        value = _metric_value(demo, metric)
        if value is None:
            return None
        total += ((value - center) / spread) ** 2
        used += 1
    if not used:
        return None
    return math.sqrt(total)


def analyze_whitespace(
    locations: list[LocationRecord],
    demographics: dict[str, ZipDemographics],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    subject_brand = config["subject_brand"]
    competitor_brands = set(config["competitor_brands"])
    all_brands = {subject_brand, *competitor_brands}
    metrics = config["similarity"]["metrics"]
    max_distance = float(config["similarity"].get("max_distance", 1.5))
    geography = config.get("geography", {"type": "us"})

    locations = [row for row in dedupe_locations(locations) if row.brand in all_brands]

    brands_by_zip: dict[str, set[str]] = defaultdict(set)
    counts_by_zip_brand: dict[tuple[str, str], int] = defaultdict(int)
    for row in locations:
        brands_by_zip[row.zip5].add(row.brand)
        counts_by_zip_brand[(row.zip5, row.brand)] += 1

    subject_zips = {
        row.zip5
        for row in locations
        if row.brand == subject_brand and row.zip5 in demographics and _geo_allowed(row.zip5, demographics[row.zip5], geography)
    }
    stats = _profile_stats(subject_zips, demographics, metrics)

    location_output: list[dict[str, Any]] = []
    for row in locations:
        demo = demographics.get(row.zip5)
        if not demo or not _geo_allowed(row.zip5, demo, geography):
            continue
        location_output.append(
            {
                "brand": row.brand,
                "location_id": row.location_id,
                "name": row.name,
                "address": row.address,
                "city": row.city,
                "state": row.state,
                "zip_code": row.zip5,
                "population": demo.population,
                "median_household_income": demo.median_household_income,
                "median_age": demo.median_age,
                "source": row.source,
                "observed_at": row.observed_at,
            }
        )

    whitespace_output: list[dict[str, Any]] = []
    for zip_code, demo in demographics.items():
        if not _geo_allowed(zip_code, demo, geography):
            continue
        if subject_brand in brands_by_zip[zip_code]:
            continue
        distance = _distance(demo, stats)
        if distance is None or distance > max_distance:
            continue
        competitors_present = sorted(brands_by_zip[zip_code] & competitor_brands)
        whitespace_output.append(
            {
                "zip_code": zip_code,
                "population": demo.population,
                "median_household_income": demo.median_household_income,
                "median_age": demo.median_age,
                "similarity_distance": round(distance, 4),
                "whitespace_type": "competitor_present" if competitors_present else "no_tracked_brand_present",
                "competitors_present": "|".join(competitors_present),
                "dominos_count": counts_by_zip_brand[(zip_code, subject_brand)],
                "pizza_hut_count": counts_by_zip_brand[(zip_code, "Pizza Hut")],
                "little_caesars_count": counts_by_zip_brand[(zip_code, "Little Caesars")],
                "demographics_source": demo.source,
            }
        )

    summary = {
        "subject_brand": subject_brand,
        "competitor_brands": sorted(competitor_brands),
        "location_records": len(locations),
        "subject_zip_count": len(subject_zips),
        "whitespace_zip_count": len(whitespace_output),
        "similarity_metrics": metrics,
        "similarity_centers": {metric: stats[metric][0] for metric in metrics},
        "similarity_spreads": {metric: stats[metric][1] for metric in metrics},
    }
    return location_output, sorted(whitespace_output, key=lambda row: row["similarity_distance"]), summary
