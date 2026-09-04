from __future__ import annotations

from typing import Any

from whitespace_tool.normalization import get_nested, optional_date, optional_float, optional_int
from whitespace_tool.field_registry import load_field_registry


FIELD_VALIDATORS = {
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
}

FIELD_VALIDATORS = {field["key"]: FIELD_VALIDATORS[field["type"] == "date" and "opening_date" or field["key"]]
                    for field in load_field_registry()
                    if field["key"] in FIELD_VALIDATORS}


def validate_source_row(row: dict[str, Any], mapper: dict[str, Any]) -> list[dict[str, str]]:
    """Validate a parsed row independently of whether it came from CSV, Excel, JSON, XML, or an API."""
    errors: list[dict[str, str]] = []
    fields = mapper.get("fields", {})
    for field_name, validator in FIELD_VALIDATORS.items():
        source_path = fields.get(field_name)
        if not source_path:
            continue
        value = get_nested(row, source_path, "")
        if value in (None, ""):
            continue
        if validator(value) is None:
            errors.append({
                "field": field_name,
                "source_path": source_path,
                "reason": "invalid value for expected type",
                "hint": f"Field '{field_name}' value '{value}' could not be parsed as a valid type.",
                "value": str(value),
            })
    return errors


def validate_normalized_location(location: Any, registry: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field in registry:
        key = field["key"]
        value = getattr(location, key, None)
        if field.get("required") and not str(value or "").strip():
            errors.append({
                "field": key,
                "reason": "missing standardized value",
                "hint": f"Mandatory field '{key}' is blank or unmapped.",
                "value": ""
            })
            continue
        if value is None:
            continue
        expected = field.get("type")
        valid = (
            expected in {"string", "timestamp"} and isinstance(value, str)
            or expected == "float" and isinstance(value, (int, float))
            or expected == "integer" and isinstance(value, int)
            or expected == "date" and isinstance(value, str)
        )
        if not valid:
            errors.append({
                "field": key,
                "reason": f"invalid standardized {expected} value",
                "hint": f"Field '{key}' has value '{value}' which does not match required type {expected}.",
                "value": str(value)
            })
    
    # Standard geographic and assessment field validation
    if getattr(location, "postal_code", None):
        zip_str = str(location.postal_code).strip()
        if not (len(zip_str) == 5 and zip_str.isdigit()):
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
        if not (in_us_lat and in_us_lon):
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