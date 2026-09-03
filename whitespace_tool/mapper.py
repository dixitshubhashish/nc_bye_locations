from __future__ import annotations

import json
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
    )
