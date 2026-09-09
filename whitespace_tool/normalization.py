from __future__ import annotations

import dataclasses
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, utc_now_iso

_TRAILING_APOSTROPHE_S = re.compile(r"'S\b")
_DISPLAY_SAFE_TEXT = re.compile(r"[^A-Za-z0-9\s#'\-.]")


def titleize(value: str) -> str:
    """Proper-case a display name regardless of source casing (lower, upper,
    or mixed), fixing the common "'S" contraction artifact left by
    str.title() (e.g. "domino's" / "DOMINO'S" -> "Domino's")."""
    text = value.strip()
    if not text:
        return text
    return _TRAILING_APOSTROPHE_S.sub("'s", text.title())


def clean_display_text(value: Any, proper_case: bool = False) -> str:
    """Normalize human name/address text without changing source keys."""
    text = _DISPLAY_SAFE_TEXT.sub("", str(value or "").replace("_", " "))
    text = re.sub(r"\s+", " ", text).strip()
    return titleize(text) if proper_case else text


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
    # Non-US postal codes can contain letters (e.g. UK "SW1A 1AA", Canada
    # "K1A 0B1") - stripping to digits-only used to silently destroy them
    # (e.g. "SW1A 1AA" -> "11"). Preserve any alphanumeric code as-is
    # (whitespace removed, upper-cased) instead; only the pure-numeric US
    # case still collapses to the 5-digit form everything else assumes.
    text = "".join(str(value or "").split())
    if not text:
        return ""
    if any(ch.isalpha() for ch in text):
        return text.upper()
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) >= 5:
        return digits[:5]
    if len(digits) == 4:
        # Spreadsheet/numeric-formatting sources commonly drop a US ZIP's
        # leading zero (e.g. Massachusetts "02134" -> "2134"). Restoring it
        # lets the enrichment pass still find a valid match instead of
        # treating a truncated real ZIP as unrecognizable.
        return "0" + digits
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
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%m-%d-%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                pass
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


# Cap the passthrough payload so a pathological source (hundreds of wide
# columns) can't blow the 512MB budget one row at a time. Truncation is
# recorded in the payload itself rather than happening silently.
EXTRAS_MAX_KEYS = 60
EXTRAS_MAX_CHARS = 8000


def _collect_extras(row: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any] | None:
    """Source columns this row carried that no mapped/typed field consumed.

    Every parse can present a different column list, so the fixed listings
    schema can never cover them all. Anything the mapper did not consume is
    preserved here instead of being dropped at the bronze write.

    A top-level key counts as consumed only on an exact path match. For a
    dotted mapping ("address.street") the parent object is therefore kept
    here too - duplicating a little is the deliberate trade against losing
    a column, since never losing source data is the point of this field.
    """
    if not isinstance(row, dict):
        return None
    consumed = {str(path) for path in fields.values() if path}
    extras: dict[str, Any] = {}
    for key, value in row.items():
        if key == "__meta" or key in consumed:
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        # Unmapped columns went to the warehouse completely unchecked.
        # Same rule as mapped fields: a value that cannot be what its column
        # means is dropped rather than stored as junk.
        from whitespace_tool.data_validation.semantic_types import clean_field_value
        cleaned_value, action, _kind = clean_field_value(key, value)
        if cleaned_value is None:
            continue
        extras[key] = cleaned_value
        if len(extras) >= EXTRAS_MAX_KEYS:
            extras["__truncated"] = "key limit reached"
            break
    if not extras:
        return None
    # Second guard on serialized size, for few-but-huge values.
    try:
        if len(json.dumps(extras, default=str)) > EXTRAS_MAX_CHARS:
            trimmed: dict[str, Any] = {}
            for key, value in extras.items():
                trimmed[key] = value
                if len(json.dumps(trimmed, default=str)) > EXTRAS_MAX_CHARS:
                    trimmed.pop(key)
                    trimmed["__truncated"] = "size limit reached"
                    break
            return trimmed or None
    except (TypeError, ValueError):
        return None
    return extras


def _apply_semantic_cleaning(record: LocationRecord) -> LocationRecord:
    """Clear/repair any field whose value cannot be what its column means.

    Runs AFTER the record is built, so it sees the same normalized values the
    warehouse would have stored. Geo fields are excluded by
    semantic_types.GEO_OWNED_FIELDS - clean_zip(), normalize_state_code(),
    the cached city<->ZIP lookups and the inverted-coordinate repair are all
    strictly smarter than a generic rule, and running over them would undo
    that work.

    Cleared values become None rather than rejecting the row, matching how
    unparseable numerics already behave: the row's other good fields are
    kept, and the blank field becomes something enrichment can fill.
    """
    # Imported here rather than at module scope: semantic_types imports the
    # optional_* validators from this module, so a top-level import would be
    # circular.
    from whitespace_tool.data_validation.semantic_types import CLEARED, clean_field_value, is_geo_owned

    updates: dict[str, Any] = {}
    cleaned_fields: list[str] = []
    for field in dataclasses.fields(record):
        name = field.name
        if name in ("raw", "extras", "brand", "business_id", "source_type_id", "source", "observed_at"):
            continue
        if is_geo_owned(name):
            continue
        value = getattr(record, name, None)
        if value is None:
            continue
        new_value, action, _kind = clean_field_value(name, value)
        if action != "ok":
            updates[name] = new_value
            if action == CLEARED:
                cleaned_fields.append(name)
    if not updates:
        return record
    record = dataclasses.replace(record, **updates)
    if cleaned_fields:
        # Recorded on the raw payload so review/enrichment can see WHICH
        # fields were dropped and target them, instead of a silent blank.
        raw = dict(record.raw or {})
        meta = dict(raw.get("__meta") or {})
        meta["semantically_cleared_fields"] = sorted(cleaned_fields)
        raw["__meta"] = meta
        record = dataclasses.replace(record, raw=raw)
    return record


def normalize_location(row: dict[str, Any], mapper: dict[str, Any], source_name: str, index: int) -> LocationRecord | None:
    from whitespace_tool.geo_enrichment import detect_and_fix_inverted_coords, normalize_state_code
    from whitespace_tool.sqlite_cache import lookup_cached_city_state

    fields = mapper["fields"]
    brand = clean_display_text(_text(mapper.get("brand")) or _text(get_nested(row, fields.get("brand", "brand"))), proper_case=True)
    postal_code = clean_zip(get_nested(row, fields.get("postal_code", "")))
    if not postal_code and (mapper.get("is_ai_enriched") or mapper.get("auto_enrich")):
        raw_city = clean_display_text(get_nested(row, fields.get("city", "")), proper_case=True)
        raw_state = normalize_state_code(_text(get_nested(row, fields.get("state", ""))))
        if raw_city and raw_state:
            match = lookup_cached_city_state(raw_city, raw_state)
            if match and match.get("zip_code"):
                postal_code = str(match["zip_code"])
    if not brand:
        return None

    location_id = _text(get_nested(row, fields.get("location_id", ""), ""))
    if not location_id:
        location_id = f"{brand.lower().replace(' ', '_')}:{postal_code}:{index}"

    raw_observed = _text(get_nested(row, fields.get("observed_at", ""), ""))
    normalized_observed = optional_timestamp(raw_observed) if raw_observed else None

    raw_lat = optional_float(get_nested(row, fields.get("latitude", ""), ""))
    raw_lon = optional_float(get_nested(row, fields.get("longitude", ""), ""))
    if raw_lat is not None and raw_lon is not None:
        raw_lat, raw_lon, _ = detect_and_fix_inverted_coords(raw_lat, raw_lon)

    record = LocationRecord(
        brand=brand,
        business_id=str(mapper.get("business_id") or "") or None,
        source_type_id=str(mapper.get("source_type_id") or "") or None,
        location_id=location_id,
        name=clean_display_text(get_nested(row, fields.get("name", ""), ""), proper_case=True),
        address=clean_display_text(get_nested(row, fields.get("address", ""), "")),
        city=clean_display_text(get_nested(row, fields.get("city", ""), ""), proper_case=True),
        state=normalize_state_code(_text(get_nested(row, fields.get("state_code", fields.get("state", ""))))) or _text(get_nested(row, fields.get("state_code", fields.get("state", "")))).upper(),
        postal_code=postal_code,
        latitude=raw_lat,
        longitude=raw_lon,
        source=source_name,
        observed_at=normalized_observed or raw_observed or utc_now_iso(),
        raw=dict(row),
        extras=_collect_extras(row, fields),
        franchise_name=_text(get_nested(row, fields.get("franchise_name", ""), "")) or None,
        concept_type=_text(get_nested(row, fields.get("concept_type", ""), "")) or None,
        cuisine_type=_text(get_nested(row, fields.get("cuisine_type", ""), "")) or None,
        town=clean_display_text(get_nested(row, fields.get("town", ""), ""), proper_case=True) or None,
        province=clean_display_text(get_nested(row, fields.get("province", ""), ""), proper_case=True) or None,
        country=_text(get_nested(row, fields.get("country", ""), "")) or None,
        country_code=_text(get_nested(row, fields.get("country_code", ""), "")) or None,
        neighborhood=_text(get_nested(row, fields.get("neighborhood", ""), "")) or None,
        district=_text(get_nested(row, fields.get("district", ""), "")) or None,
        phone_number=_text(get_nested(row, fields.get("phone_number", ""), "")) or None,
        email=_text(get_nested(row, fields.get("email", ""), "")) or None,
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
    return _apply_semantic_cleaning(record)
