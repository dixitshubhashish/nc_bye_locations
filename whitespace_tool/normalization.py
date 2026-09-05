from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, utc_now_iso

_TRAILING_APOSTROPHE_S = re.compile(r"'S\b")


def titleize(value: str) -> str:
    """Proper-case a display name regardless of source casing (lower, upper,
    or mixed), fixing the common "'S" contraction artifact left by
    str.title() (e.g. "domino's" / "DOMINO'S" -> "Domino's")."""
    text = value.strip()
    if not text:
        return text
    return _TRAILING_APOSTROPHE_S.sub("'s", text.title())


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
    if not digits:
        return ""
    if len(digits) >= 5:
        return digits[:5]
    return digits


def _text(value: Any) -> str:
    """Coerce a mapped field value to a stripped string, treating None
    (e.g. an explicit JSON null in the source) as empty rather than the
    literal text "None" that plain str(None) would otherwise produce."""
    return "" if value is None else str(value).strip()


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return int(float(cleaned))
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


def optional_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat()


def normalize_location(row: dict[str, Any], mapper: dict[str, Any], source_name: str, index: int) -> LocationRecord | None:
    fields = mapper["fields"]
    brand = titleize(_text(mapper.get("brand")) or _text(get_nested(row, fields.get("brand", "brand"))))
    postal_code = clean_zip(get_nested(row, fields["postal_code"]))
    if not brand or not postal_code:
        return None

    location_id = _text(get_nested(row, fields.get("location_id", ""), ""))
    if not location_id:
        location_id = f"{brand.lower().replace(' ', '_')}:{postal_code}:{index}"

    return LocationRecord(
        brand=brand,
        business_id=str(mapper.get("business_id") or "") or None,
        source_type_id=str(mapper.get("source_type_id") or "") or None,
        location_id=location_id,
        name=titleize(_text(get_nested(row, fields.get("name", ""), ""))),
        address=_text(get_nested(row, fields.get("address", ""), "")),
        city=titleize(_text(get_nested(row, fields.get("city", ""), ""))),
        state=_text(get_nested(row, fields.get("state", ""), "")).upper(),
        postal_code=postal_code,
        latitude=optional_float(get_nested(row, fields.get("latitude", ""), "")),
        longitude=optional_float(get_nested(row, fields.get("longitude", ""), "")),
        source=source_name,
        observed_at=_text(get_nested(row, fields.get("observed_at", ""), "")) or utc_now_iso(),
        raw=dict(row),
        franchise_name=_text(get_nested(row, fields.get("franchise_name", ""), "")) or None,
        concept_type=_text(get_nested(row, fields.get("concept_type", ""), "")) or None,
        cuisine_type=_text(get_nested(row, fields.get("cuisine_type", ""), "")) or None,
        town=_text(get_nested(row, fields.get("town", ""), "")) or None,
        province=_text(get_nested(row, fields.get("province", ""), "")) or None,
        country=_text(get_nested(row, fields.get("country", ""), "")) or None,
        neighborhood=_text(get_nested(row, fields.get("neighborhood", ""), "")) or None,
        district=_text(get_nested(row, fields.get("district", ""), "")) or None,
        phone_number=_text(get_nested(row, fields.get("phone_number", ""), "")) or None,
        website_url=_text(get_nested(row, fields.get("website_url", ""), "")) or None,
        google_maps_link=_text(get_nested(row, fields.get("google_maps_link", ""), "")) or None,
        social_media_handles=_text(get_nested(row, fields.get("social_media_handles", ""), "")) or None,
        operating_hours=_text(get_nested(row, fields.get("operating_hours", ""), "")) or None,
        seating_capacity=optional_int(get_nested(row, fields.get("seating_capacity", ""), "")),
        service_types=_text(get_nested(row, fields.get("service_types", ""), "")) or None,
        opening_date=optional_date(get_nested(row, fields.get("opening_date", ""), "")),
        status=_text(get_nested(row, fields.get("status", ""), "")) or None,
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
        parking_availability=_text(get_nested(row, fields.get("parking_availability", ""), "")) or None,
        ratings=optional_float(get_nested(row, fields.get("ratings", ""), "")),
    )
