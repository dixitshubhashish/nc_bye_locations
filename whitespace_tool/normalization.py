from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, utc_now_iso


def load_mapper(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_nested(row: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = row
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        else:
            return default
    return current


def clean_zip(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:5].zfill(5) if digits else ""


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def optional_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for parser in (date.fromisoformat,):
        try:
            return parser(text).isoformat()
        except ValueError:
            pass
    for format_string in ("%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, format_string).date().isoformat()
        except ValueError:
            pass
    return None


def normalize_location(row: dict[str, Any], mapper: dict[str, Any], source_name: str, index: int) -> LocationRecord | None:
    fields = mapper["fields"]
    brand = str(mapper.get("brand") or get_nested(row, fields.get("brand", "brand"))).strip()
    postal_code = clean_zip(get_nested(row, fields["postal_code"]))
    if not brand or not postal_code:
        return None

    location_id = str(get_nested(row, fields.get("location_id", ""), "")).strip()
    if not location_id:
        location_id = f"{brand.lower().replace(' ', '_')}:{postal_code}:{index}"

    return LocationRecord(
        brand=brand,
        business_id=str(mapper.get("business_id") or "") or None,
        source_type_id=str(mapper.get("source_type_id") or "") or None,
        location_id=location_id,
        name=str(get_nested(row, fields.get("name", ""), "")).strip(),
        address=str(get_nested(row, fields.get("address", ""), "")).strip(),
        city=str(get_nested(row, fields.get("city", ""), "")).strip(),
        state=str(get_nested(row, fields.get("state", ""), "")).strip().upper(),
        postal_code=postal_code,
        latitude=optional_float(get_nested(row, fields.get("latitude", ""), "")),
        longitude=optional_float(get_nested(row, fields.get("longitude", ""), "")),
        source=source_name,
        observed_at=str(get_nested(row, fields.get("observed_at", ""), "")).strip() or utc_now_iso(),
        raw=dict(row),
        franchise_name=str(get_nested(row, fields.get("franchise_name", ""), "")).strip() or None,
        concept_type=str(get_nested(row, fields.get("concept_type", ""), "")).strip() or None,
        cuisine_type=str(get_nested(row, fields.get("cuisine_type", ""), "")).strip() or None,
        town=str(get_nested(row, fields.get("town", ""), "")).strip() or None,
        province=str(get_nested(row, fields.get("province", ""), "")).strip() or None,
        country=str(get_nested(row, fields.get("country", ""), "")).strip() or None,
        neighborhood=str(get_nested(row, fields.get("neighborhood", ""), "")).strip() or None,
        district=str(get_nested(row, fields.get("district", ""), "")).strip() or None,
        phone_number=str(get_nested(row, fields.get("phone_number", ""), "")).strip() or None,
        website_url=str(get_nested(row, fields.get("website_url", ""), "")).strip() or None,
        google_maps_link=str(get_nested(row, fields.get("google_maps_link", ""), "")).strip() or None,
        social_media_handles=str(get_nested(row, fields.get("social_media_handles", ""), "")).strip() or None,
        operating_hours=str(get_nested(row, fields.get("operating_hours", ""), "")).strip() or None,
        seating_capacity=optional_int(get_nested(row, fields.get("seating_capacity", ""), "")),
        service_types=str(get_nested(row, fields.get("service_types", ""), "")).strip() or None,
        opening_date=optional_date(get_nested(row, fields.get("opening_date", ""), "")),
        status=str(get_nested(row, fields.get("status", ""), "")).strip() or None,
        annual_revenue=optional_float(get_nested(row, fields.get("annual_revenue", ""), "")),
        average_ticket_size=optional_float(get_nested(row, fields.get("average_ticket_size", ""), "")),
        daily_footfall=optional_int(get_nested(row, fields.get("daily_footfall", ""), "")),
        monthly_footfall=optional_int(get_nested(row, fields.get("monthly_footfall", ""), "")),
        rental_cost=optional_float(get_nested(row, fields.get("rental_cost", ""), "")),
        lease_cost=optional_float(get_nested(row, fields.get("lease_cost", ""), "")),
        population_density=optional_float(get_nested(row, fields.get("population_density", ""), "")),
        average_household_income=optional_float(get_nested(row, fields.get("average_household_income", ""), "")),
        competitor_count=optional_int(get_nested(row, fields.get("competitor_count", ""), "")),
        foot_traffic_score=optional_float(get_nested(row, fields.get("foot_traffic_score", ""), "")),
        parking_availability=str(get_nested(row, fields.get("parking_availability", ""), "")).strip() or None,
    )
