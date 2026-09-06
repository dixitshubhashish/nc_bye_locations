"""Analytics module for location deduplication, demographic scoring, and whitespace analysis.

Provides exact and fuzzy location deduplication, demographic similarity calculations,
geographic filtering, and whitespace site identification logic.
"""

from __future__ import annotations

import math
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import mean, pstdev
from typing import Any

from whitespace_tool.common.models import LocationRecord, ZipDemographics

FUZZY_ADDRESS_MATCH_THRESHOLD = 0.70
FUZZY_COORDINATE_TOLERANCE = 0.0005


def _dedupe_text(value: object) -> str:
    """Normalize string value for location deduplication matching."""
    return str(value or "").strip().casefold()


def _dedupe_coordinate(value: float | None) -> str:
    """Format floating point coordinate to fixed 6-decimal string for deduplication."""
    if value is None:
        return ""
    return f"{float(value):.6f}"


def dedupe_location_key(record: LocationRecord) -> tuple[str, str, str, str, str, str, str, str, str]:
    """Generate normalized exact deduplication tuple key for a LocationRecord."""
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
    """Generate coarse bucket tuple key (brand, state, zip5, city) for candidate fuzzy grouping."""
    return (
        _dedupe_text(record.brand),
        _dedupe_text(record.state),
        _dedupe_text(record.zip5),
        _dedupe_text(record.city),
    )


def _addresses_match(left: LocationRecord, right: LocationRecord) -> bool:
    """Determine whether two records have fuzzy-matching street addresses above ratio threshold."""
    left_address = _dedupe_text(left.address)
    right_address = _dedupe_text(right.address)
    if not left_address or not right_address:
        return False
    return SequenceMatcher(None, left_address, right_address).ratio() >= FUZZY_ADDRESS_MATCH_THRESHOLD


def _coordinates_match(left: LocationRecord, right: LocationRecord) -> bool:
    """Determine whether two records have coordinates within coordinate tolerance delta."""
    if left.latitude is None or left.longitude is None or right.latitude is None or right.longitude is None:
        return False
    return (
        abs(left.latitude - right.latitude) <= FUZZY_COORDINATE_TOLERANCE
        and abs(left.longitude - right.longitude) <= FUZZY_COORDINATE_TOLERANCE
    )


def is_fuzzy_duplicate_location(left: LocationRecord, right: LocationRecord) -> bool:
    """Check if two LocationRecord instances represent fuzzy duplicate locations."""
    return _fuzzy_bucket(left) == _fuzzy_bucket(right) and _addresses_match(left, right) and _coordinates_match(left, right)


def dedupe_locations(records: list[LocationRecord]) -> list[LocationRecord]:
    """Filter list of LocationRecord instances removing exact and fuzzy duplicates."""
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
    """Check whether zip code satisfies geographic filter constraints in configuration."""
    if geography.get("type", "us") == "us":
        return True
    if geography["type"] == "zip_prefixes":
        return any(zip_code.startswith(str(prefix)) for prefix in geography["values"])
    raise ValueError(f"Unsupported geography type: {geography['type']}")


def _metric_value(demo: ZipDemographics, metric: str) -> float | None:
    """Extract numeric demographic attribute value by metric name."""
    return getattr(demo, metric, None)


def _profile_stats(
    subject_zips: set[str],
    demographics: dict[str, ZipDemographics],
    metrics: list[str],
) -> dict[str, tuple[float, float]]:
    """Compute mean and standard deviation for demographic similarity metrics across subject ZIPs."""
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
    """Calculate Euclidean distance metric for a ZIP code against subject profile stats."""
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
    """Execute complete whitespace analysis for subject brand against competitors and demographics."""
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


HAVERSINE_EARTH_RADIUS_MILES = 3958.8


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in miles between two points on the earth."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return HAVERSINE_EARTH_RADIUS_MILES * c


def cluster_locations(locations: list[LocationRecord], radius_miles: float = 0.5) -> list[list[LocationRecord]]:
    """Cluster locations within a specified radius in miles."""
    clusters: list[list[LocationRecord]] = []
    for loc in locations:
        if loc.latitude is None or loc.longitude is None:
            continue
        placed = False
        for cluster in clusters:
            ref = cluster[0]
            if ref.latitude is not None and ref.longitude is not None:
                if haversine_distance(loc.latitude, loc.longitude, ref.latitude, ref.longitude) <= radius_miles:
                    cluster.append(loc)
                    placed = True
                    break
        if not placed:
            clusters.append([loc])
    return clusters


deduplicate_locations = dedupe_locations

