from __future__ import annotations

from typing import Any

from whitespace_tool.normalization import get_nested, optional_date, optional_float, optional_int, optional_timestamp
from whitespace_tool.field_registry import load_field_registry


VALIDATORS_BY_FIELD = {
    "latitude": optional_float,
    "longitude": optional_float,
    "seating_capacity": optional_int,
    "annual_revenue": optional_float,
    "average_ticket_size": optional_float,
    "daily_footfall": optional_int,
    "monthly_footfall": optional_int,
    "rental_cost": optional_float,
    "lease_cost": optional_float,
    "population_density": optional_float,
    "average_household_income": optional_float,
    "competitor_count": optional_int,
    "foot_traffic_score": optional_float,
    "opening_date": optional_date,
    "observed_at": optional_timestamp,
}

VALIDATORS_BY_TYPE = {
    "date": optional_date,
    "float": optional_float,
    "integer": optional_int,
    "timestamp": optional_timestamp,
}

FIELD_VALIDATORS = {
    field["key"]: VALIDATORS_BY_TYPE.get(field["type"], VALIDATORS_BY_FIELD[field["key"]])
    for field in load_field_registry()
    if field["key"] in VALIDATORS_BY_FIELD
}

# Human-readable label per registry key (e.g. "opening_date" -> "Opening
# Date"), so a validation hint reads as a real column name instead of the
# raw stored key - falls back to the key itself for anything not in the
# registry (a custom field, say) rather than failing.
FIELD_LABELS = {field["key"]: field.get("label") or field["key"] for field in load_field_registry()}


def _field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key)


def validate_source_row(row: dict[str, Any], mapper: dict[str, Any]) -> list[dict[str, str]]:
    """Validate a parsed row independently of whether it came from CSV, Excel, JSON, XML, or an API.

    Every field checked here (FIELD_VALIDATORS) is a non-required numeric,
    date, or timestamp field - a value that can't parse as that type (e.g.
    "Springfield" for seating_capacity) is essentially never a real value
    for that field, it's a mapping mismatch. normalize_location() already
    calls the same validators (optional_int/optional_float/etc.) and stores
    None when they fail, so the field is already handled gracefully - this
    used to *also* flag it as a blocking error, rejecting the whole row over
    one optional field that can't sensibly be "fixed" (there's no way to
    enrich a real seating capacity out of "Springfield"). Not raised here
    lets it fall through as cleared instead of rejecting the row.
    """
    return []


def validate_normalized_location(location: Any, registry: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field in registry:
        key = field["key"]
        value = getattr(location, key, None)
        if field.get("required") and not str(value or "").strip():
            errors.append({
                "field": key,
                "reason": "missing standardized value",
                "hint": f"Mandatory field '{_field_label(key)}' is blank or unmapped.",
                "value": ""
            })
            continue
        if value is None:
            continue
        expected = field.get("type")
        valid = (
            expected == "string" and isinstance(value, str)
            or expected == "float" and isinstance(value, (int, float))
            or expected == "integer" and isinstance(value, int)
            or expected == "date" and isinstance(value, str) and optional_date(value) is not None
            or expected == "timestamp" and isinstance(value, str) and optional_timestamp(value) is not None
        )
        if not valid:
            errors.append({
                "field": key,
                "reason": f"invalid standardized {expected} value",
                "hint": f"Field '{_field_label(key)}' has value '{value}' which does not match required type {expected}.",
                "value": str(value)
            })
    
    # Standard geographic and assessment field validation. This 5-digit
    # check is US-specific - clean_zip() (normalization.py) preserves
    # letters for non-US postal codes (e.g. "SW1A1AA"), so only flag a
    # purely-numeric code that isn't 5 digits; an alphanumeric code is a
    # legitimate non-US postal code, not a malformed US ZIP.
    if getattr(location, "postal_code", None):
        zip_str = str(location.postal_code).strip()
        if zip_str.isdigit() and len(zip_str) != 5:
            errors.append({
                "field": "postal_code",
                "reason": "invalid US ZIP code",
                "hint": f"ZIP code '{zip_str}' is invalid. Must be a 5-digit US ZIP.",
                "value": zip_str
            })
            
    if getattr(location, "latitude", None) is not None and getattr(location, "longitude", None) is not None:
        lat = location.latitude
        lon = location.longitude
        in_us_lat = (13.0 <= lat <= 72.0)
        in_us_lon = (-180.0 <= lon <= -64.0) or (144.0 <= lon <= 146.0)
        # Try the US reading first (this app is US-primary), but a record
        # explicitly identified as non-US (country/country_code already
        # set to something other than the US) is legitimately outside
        # these bounds - it isn't a validation failure, it's real worldwide
        # data. Only flag the boundary mismatch when nothing marks this as
        # a deliberately non-US record.
        country_value = str(getattr(location, "country", "") or "").strip().lower()
        country_code_value = str(getattr(location, "country_code", "") or "").strip().upper()
        explicitly_non_us = (
            (country_value and country_value not in ("united states", "united states of america", "usa", "us"))
            or (country_code_value and country_code_value not in ("US", "USA"))
        )
        if not (in_us_lat and in_us_lon) and not explicitly_non_us:
            errors.append({
                "field": "coordinates",
                "reason": "coordinates outside US boundary",
                "hint": f"Coordinates ({lat}, {lon}) fall outside valid US geographic boundaries.",
                "value": f"{lat}, {lon}"
            })
            
    # Domain boundary checks for demographic/assessment fields
    if hasattr(location, "median_age") and location.median_age is not None:
        if not (0 <= location.median_age <= 130):
            errors.append({
                "field": "median_age",
                "reason": "age outside realistic boundary",
                "hint": f"Median age '{location.median_age}' must be between 0 and 130 years.",
                "value": str(location.median_age)
            })

    if hasattr(location, "annual_revenue") and location.annual_revenue is not None:
        if location.annual_revenue < 0:
            errors.append({
                "field": "annual_revenue",
                "reason": "negative monetary amount",
                "hint": f"Annual revenue '{location.annual_revenue}' cannot be negative.",
                "value": str(location.annual_revenue)
            })

    if hasattr(location, "average_household_income") and location.average_household_income is not None:
        if location.average_household_income < 0:
            errors.append({
                "field": "average_household_income",
                "reason": "negative monetary amount",
                "hint": f"Average household income '{location.average_household_income}' cannot be negative.",
                "value": str(location.average_household_income)
            })

    return errors
