from __future__ import annotations

from typing import Any

from whitespace_tool.mapper import get_nested, optional_date, optional_float, optional_int


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