from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from whitespace_tool.analysis import dedupe_location_key, is_fuzzy_duplicate_location
from whitespace_tool.models import LocationRecord, ZipDemographics


US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


def _issue(severity: str, check: str, message: str, count: int = 1, sample: Any = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "check": check,
        "message": message,
        "count": count,
        "sample": sample,
    }


def _parse_observed_at(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _check_source_freshness(config: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    policy = config.get("freshness_policy", {})
    require_live = bool(policy.get("require_live_location_sources", False))
    for source in config.get("location_sources", []):
        source_tier = source.get("source_tier", "snapshot")
        if source_tier == "demo":
            issues.append(
                _issue(
                    "warning",
                    "demo_source_in_use",
                    "Source is marked as demo data and should be replaced for a current run",
                    sample={"source": source.get("name"), "type": source.get("type")},
                )
            )
        if require_live and source_tier != "live":
            issues.append(
                _issue(
                    "warning",
                    "non_live_location_source",
                    "Configured source is not marked live",
                    sample={"source": source.get("name"), "source_tier": source_tier},
                )
            )
        if source.get("sample_path"):
            issues.append(
                _issue(
                    "warning",
                    "sample_source_in_use",
                    "Source is reading a local sample file instead of the live endpoint",
                    sample={"source": source.get("name"), "sample_path": source.get("sample_path")},
                )
            )


def run_quality_checks(
    locations: list[LocationRecord],
    demographics: dict[str, ZipDemographics],
    config: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    brands = {config["subject_brand"], *config["competitor_brands"]}
    by_brand = Counter(row.brand for row in locations)
    by_source = Counter(row.source for row in locations)
    _check_source_freshness(config, issues)

    missing_by_brand = sorted(brands - set(by_brand))
    if missing_by_brand:
        issues.append(_issue("error", "brand_coverage", "Configured brands with no records", len(missing_by_brand), missing_by_brand))

    exact_duplicate_keys = Counter(dedupe_location_key(row) for row in locations)
    duplicates: list[Any] = [
        {
            "brand": key[0],
            "location_id": key[1],
            "name": key[2],
            "address": key[3],
            "city": key[4],
            "state": key[5],
            "postal_code": key[6],
            "latitude": key[7],
            "longitude": key[8],
            "count": count,
        }
        for key, count in exact_duplicate_keys.items()
        if count > 1
    ]
    fuzzy_duplicates = []
    fuzzy_kept: list[LocationRecord] = []
    for row in locations:
        duplicate_of = next((existing for existing in fuzzy_kept if is_fuzzy_duplicate_location(existing, row)), None)
        if duplicate_of:
            fuzzy_duplicates.append({
                "brand": row.brand,
                "location_id": row.location_id,
                "duplicate_of": duplicate_of.location_id,
                "address": row.address,
                "matched_address": duplicate_of.address,
                "latitude": row.latitude,
                "longitude": row.longitude,
            })
            continue
        fuzzy_kept.append(row)
    duplicates.extend(fuzzy_duplicates)
    if duplicates:
        issues.append(_issue("warning", "duplicate_location_keys", "Duplicate standard or fuzzy location identities", len(duplicates), duplicates[:10]))

    missing_required: dict[str, int] = defaultdict(int)
    for row in locations:
        for field in ("brand", "location_id", "address", "city", "state", "postal_code", "observed_at"):
            if not getattr(row, field):
                missing_required[field] += 1
    for field, count in sorted(missing_required.items()):
        issues.append(_issue("error", f"missing_{field}", f"Location records missing {field}", count))

    max_age_hours = config.get("freshness_policy", {}).get("max_location_age_hours")
    if max_age_hours is not None:
        now = datetime.now(timezone.utc)
        stale = []
        invalid_timestamps = []
        for row in locations:
            observed_at = _parse_observed_at(row.observed_at)
            if observed_at is None:
                invalid_timestamps.append(row.location_id)
            elif (now - observed_at).total_seconds() > float(max_age_hours) * 3600:
                stale.append(row.location_id)
        if invalid_timestamps:
            issues.append(
                _issue(
                    "warning",
                    "invalid_observed_at",
                    "Location records with unparseable observed_at timestamps",
                    len(invalid_timestamps),
                    invalid_timestamps[:20],
                )
            )
        if stale:
            issues.append(
                _issue(
                    "warning",
                    "stale_location_records",
                    f"Location records older than {max_age_hours} hours",
                    len(stale),
                    stale[:20],
                )
            )

    invalid_states = sorted({row.state for row in locations if row.state and row.state not in US_STATE_CODES})
    if invalid_states:
        issues.append(_issue("warning", "invalid_state_codes", "Unexpected state codes in location data", len(invalid_states), invalid_states))

    bad_zip_rows = [asdict(row) for row in locations if len(row.zip5) != 5 or not row.zip5.isdigit()]
    if bad_zip_rows:
        issues.append(_issue("error", "invalid_zip_codes", "Location records with invalid ZIP codes", len(bad_zip_rows), bad_zip_rows[:5]))

    unmatched_zips = sorted({row.zip5 for row in locations if row.zip5 not in demographics})
    if unmatched_zips:
        issues.append(_issue("warning", "zip_without_demographics", "Restaurant ZIPs missing Census/demographic data", len(unmatched_zips), unmatched_zips[:20]))

    demo_missing = defaultdict(int)
    for demo in demographics.values():
        for field in ("population", "median_household_income", "median_age"):
            if getattr(demo, field) is None:
                demo_missing[field] += 1
    for field, count in sorted(demo_missing.items()):
        issues.append(_issue("warning", f"missing_demographic_{field}", f"ZIP records missing {field}", count))

    suspicious_coordinates = [
        row.location_id
        for row in locations
        if row.latitude is not None
        and row.longitude is not None
        and not (18 <= row.latitude <= 72 and -180 <= row.longitude <= -60)
    ]
    if suspicious_coordinates:
        issues.append(
            _issue(
                "warning",
                "suspicious_coordinates",
                "Coordinates outside broad US bounds",
                len(suspicious_coordinates),
                suspicious_coordinates[:20],
            )
        )

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "passed": error_count == 0,
        "summary": {
            "location_records": len(locations),
            "zip_records": len(demographics),
            "brand_counts": dict(sorted(by_brand.items())),
            "source_counts": dict(sorted(by_source.items())),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "issues": issues,
    }
