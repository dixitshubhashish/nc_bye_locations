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
                "value": str(value),
            })
    return errors


def validate_normalized_location(location: Any, registry: list[dict[str, Any]]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field in registry:
        key = field["key"]
        value = getattr(location, key, None)
        if field.get("required") and not str(value or "").strip():
            errors.append({"field": key, "reason": "missing standardized value"})
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
            errors.append({"field": key, "reason": f"invalid standardized {expected} value", "value": str(value)})
    return errors