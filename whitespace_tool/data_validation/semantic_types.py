"""Semantic type inference and value repair, driven by one table.

The rule this implements, in the user's words: *if a column's name or type is
commonly understandable and the value inside is not what that kind of column
should hold, clear it, fix it, and let enrichment fill it.*

Why this exists: the registry declares 25 of its 41 fields as plain "string",
so a declared type tells us almost nothing. What actually identifies a column
is its NAME - "phone", "website", "annual_revenue", "opening_date" are
understandable to anyone. Before this, only numeric/date fields were checked
(see FIELD_VALIDATORS); junk in a phone/email/URL/percent column flowed
straight through to the warehouse, and unmapped source columns were never
checked at all.

Deliberately one declarative table plus two small functions rather than a
per-column branch: adding a column type is a row here, not new code, and
every caller (mapped fields, unmapped passthrough columns, review repair)
goes through the same path so they cannot disagree.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from whitespace_tool.normalization import optional_date, optional_float, optional_int, optional_timestamp

# Placeholders that mean "no value" in every kind of column. Sources write
# these constantly; stored verbatim they look like real data and defeat every
# completeness metric downstream.
NULL_SENTINELS: frozenset[str] = frozenset({
    "", "-", "--", "---", "n/a", "n.a.", "na", "#n/a", "null", "none", "nil",
    "nan", "unknown", "not available", "not applicable", "tbd", "to be determined",
    "no data", "nodata", "missing", "undefined", "(blank)", "blank", "?", "??",
})

_MONEY_STRIP = re.compile(r"[^\d.\-]")
_DIGITS = re.compile(r"\d")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-z]{2,}$", re.I)
_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z0-9\-]+)+(/.*)?$", re.I)
_TRUE = frozenset({"true", "t", "yes", "y", "1"})
_FALSE = frozenset({"false", "f", "no", "n", "0"})


def _text(value: Any) -> str:
    return str(value).strip()


def _repair_phone(value: str) -> str | None:
    """Keep digits (and a leading +). 7-15 digits is the E.164 range; outside
    it the value is not a phone number, whatever the column is called."""
    digits = re.sub(r"[^\d]", "", value)
    if not 7 <= len(digits) <= 15:
        return None
    return f"+{digits}" if value.strip().startswith("+") else digits


def _repair_email(value: str) -> str | None:
    cleaned = value.strip().lower()
    return cleaned if _EMAIL.match(cleaned) else None


def _repair_url(value: str) -> str | None:
    cleaned = value.strip()
    bare = re.sub(r"^https?://", "", cleaned, flags=re.I)
    if not _DOMAIN.match(bare):
        return None
    return cleaned if re.match(r"^https?://", cleaned, re.I) else f"https://{bare}"


def _repair_money(value: str) -> float | None:
    """Strip currency symbols, thousands separators and stray text. Negative
    money is not a real revenue/cost, so it is cleared rather than stored."""
    stripped = _MONEY_STRIP.sub("", value.replace(",", ""))
    number = optional_float(stripped)
    return number if number is not None and number >= 0 else None


def _repair_count(value: str) -> int | None:
    number = optional_int(_MONEY_STRIP.sub("", value.replace(",", "")))
    return number if number is not None and number >= 0 else None


def _repair_percent(value: str) -> float | None:
    number = optional_float(value.replace("%", "").strip())
    return number if number is not None and 0 <= number <= 100 else None


def _repair_rating(value: str) -> float | None:
    """Ratings are 0-5 or 0-100 depending on the source; anything outside the
    wider band is not a rating."""
    number = optional_float(_MONEY_STRIP.sub("", value))
    return number if number is not None and 0 <= number <= 100 else None


def _repair_latitude(value: str) -> float | None:
    number = optional_float(value)
    return number if number is not None and -90 <= number <= 90 else None


def _repair_longitude(value: str) -> float | None:
    number = optional_float(value)
    return number if number is not None and -180 <= number <= 180 else None


def _repair_boolean(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    return None


def _repair_year(value: str) -> int | None:
    number = optional_int(_MONEY_STRIP.sub("", value))
    return number if number is not None and 1500 <= number <= 2200 else None


def _repair_text(value: str) -> str | None:
    """Free text: everything survives except a value with no letters or
    digits at all (separator noise like "..." or "---")."""
    cleaned = " ".join(value.split())
    return cleaned if re.search(r"[A-Za-z0-9]", cleaned) else None


_BARE_NUMBER = re.compile(r"^-?\d+(\.\d+)?%?$")


def _repair_hours(value: str) -> str | None:
    """Operating hours has no one valid shape ("Mon-Sun: 10:00-23:00",
    "24/7", "9am-5pm" are all legitimate free text), so this does not
    whitelist a format the way phone/email/url do - it only clears the one
    shape that is unambiguously NOT hours: a bare number with nothing else
    (real incident, 2026-09-10 - a Rating column mismapped onto Operating
    Hours put plain values like "3.6" into this field; there is no plausible
    reading of a bare decimal as a schedule, so it is cleared rather than
    kept as free text). Anything with even one letter, a colon, or a
    separator survives untouched.
    """
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    return None if _BARE_NUMBER.match(cleaned) else cleaned


# column-name pattern -> semantic kind. Order matters: the first match wins,
# so put the specific patterns above the general ones (e.g. "postal_code"
# before the generic "code", "average_ticket_size" before "size").
NAME_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(^|_)(lat|latitude)($|_)", "latitude"),
    (r"(^|_)(lon|lng|long|longitude)($|_)", "longitude"),
    (r"(phone|mobile|telephone|contact_number|fax)", "phone"),
    (r"(e_?mail)", "email"),
    (r"(website|url|link|homepage|web_?site|maps_link)", "url"),
    (r"(zip|postal|postcode)", "postal_code"),
    (r"(percent|pct|_rate$|^rate_|share)", "percent"),
    (r"(hours|hrs)", "hours"),
    # Anchored to a whole underscore-separated token (with an optional
    # trailing "s" for a plain plural, e.g. "ratings"), unlike the patterns
    # above: an unanchored "rating" also matches inside "ope-RATING-_hours"
    # (real incident, 2026-09-10 - "Operating Hours" was silently inferred
    # as a rating, so a genuinely numeric-looking value like "3.6" read as a
    # plausible rating and was never cleared, then failed a later, stricter
    # type check as an opaque "does not match required type string" reject,
    # instead of being cleared up front the way this whole module exists to
    # do). `\b` alone does not fix this - Python regex treats "_" as a word
    # character, so "phone" in "phone_number" has no \b between "e" and "_"
    # either, but that pattern isn't anchored to a whole token so it still
    # (correctly) matches; "rating" in "operating" has no separator between
    # "e" and "r" at all, so anchoring to (^|_)...(s)?($|_) rejects it while
    # still matching a leading/trailing/whole-token "rating".
    (r"(^|_)(rating|score|stars)(s)?($|_)", "rating"),
    (r"(revenue|income|cost|price|salary|amount|ticket_size|rent|lease|budget|sales)", "money"),
    # Same anchoring, same reason: an unanchored "count" also matches inside
    # "country"/"country_code" - currently harmless only because
    # is_geo_owned() intercepts those two names first, but not a rule this
    # pattern should depend on holding forever.
    (r"(capacity|footfall|traffic|seats|employees|population|units|households|quantity|qty)|(^|_)count(s)?($|_)", "count"),
    (r"(^|_)(year|founded|established)($|_)", "year"),
    (r"(date|_on$|^opened|opening)", "date"),
    (r"(_at$|timestamp|datetime|observed)", "timestamp"),
    (r"(^is_|^has_|^can_|_flag$|^flag_|enabled|active$|available$|included$)", "boolean"),
)

# semantic kind -> repair function. A kind whose repair returns None means the
# value is not a plausible member of that kind, so it is cleared.
REPAIRERS: dict[str, Callable[[str], Any]] = {
    "latitude": _repair_latitude,
    "longitude": _repair_longitude,
    "phone": _repair_phone,
    "email": _repair_email,
    "url": _repair_url,
    "percent": _repair_percent,
    "rating": _repair_rating,
    "money": _repair_money,
    "count": _repair_count,
    "year": _repair_year,
    "hours": _repair_hours,
    "boolean": _repair_boolean,
    "date": lambda v: optional_date(v),
    "timestamp": lambda v: optional_timestamp(v),
    "postal_code": lambda v: _repair_text(v),
    "text": _repair_text,
}

# Registry "type" values map onto the same kinds, and take priority over a
# name guess only when the name says nothing (see infer_semantic_kind).
TYPE_TO_KIND: dict[str, str] = {
    "float": "money", "integer": "count", "date": "date",
    "timestamp": "timestamp", "string": "text",
}

OK, REPAIRED, CLEARED = "ok", "repaired", "cleared"

# Fields that geo enrichment already owns end to end, and that this generic
# layer must NEVER touch. Each has dedicated logic that is strictly smarter
# than a regex:
#   postal_code  - clean_zip() keeps non-US alphanumeric codes ("SW1A1AA")
#                  that a US-shaped rule would wrongly clear
#   city/state   - lookup_cached_city_state() resolves city<->ZIP<->state
#                  from the cached reference data, and normalize_state_code()
#                  handles names, codes and misspellings
#   lat/long     - detect_and_fix_inverted_coords() SWAPS transposed pairs and
#                  the silver layer snaps offshore points to the nearest
#                  reference city; clearing an out-of-range value here would
#                  destroy the input those repairs work from
#   country      - worldwide reference resolution, not a name/regex question
# Running the generic cleaner over these would silently undo that work, so
# they are excluded by name. This is the "don't forget the older city->zip /
# zip->city features" guard - if a geo field ever needs new behavior, it
# belongs in geo_enrichment.py, not here.
GEO_OWNED_FIELDS: frozenset[str] = frozenset({
    "postal_code", "zip", "zip_code", "zip5", "zipcode", "postcode", "postal",
    "city", "city_name", "town", "district", "neighborhood",
    "state", "state_code", "state_name", "province",
    "country", "country_code", "country_name",
    "latitude", "longitude", "lat", "lon", "lng", "long",
    "county", "location_key", "location_id", "address",
})


def is_geo_owned(column: str) -> bool:
    """True when geo enrichment owns this column and the generic cleaner
    must stand down."""
    return re.sub(r"[^a-z0-9]+", "_", str(column or "").lower()).strip("_") in GEO_OWNED_FIELDS


def infer_semantic_kind(column: str, declared_type: str | None = None) -> str:
    """What kind of value this column is understood to hold.

    The column NAME wins over the declared type: the registry calls 25 of its
    41 fields "string", so "phone_number" declared as a string is still a
    phone number and must be validated as one.
    """
    name = re.sub(r"[^a-z0-9]+", "_", str(column or "").lower()).strip("_")
    for pattern, kind in NAME_PATTERNS:
        if re.search(pattern, name):
            return kind
    mapped = TYPE_TO_KIND.get(str(declared_type or "").lower())
    # A float/integer declaration with an unrecognisable name is still
    # numeric, which is more than "text" tells us.
    return mapped if mapped else "text"


def clean_field_value(column: str, value: Any, declared_type: str | None = None) -> tuple[Any, str, str]:
    """Return (cleaned_value, action, kind).

    action is one of:
      "ok"       - value already valid for this kind, unchanged
      "repaired" - value was reformatted into a valid one (kept)
      "cleared"  - value could not be a member of this kind, dropped to None
                   so enrichment can fill it rather than storing junk

    Clearing is deliberate and matches how numeric fields already behave: a
    value that cannot be what the column means is a mapping mistake, and
    there is nothing to gain by keeping it. Clearing (rather than rejecting
    the row) also keeps the row's other good fields.
    """
    if is_geo_owned(column):
        # Geo enrichment owns this field - hand it back untouched.
        return value, OK, "geo"
    kind = infer_semantic_kind(column, declared_type)
    if value is None:
        return None, OK, kind
    if isinstance(value, bool):
        return (value, OK, kind) if kind == "boolean" else (value, OK, kind)
    if isinstance(value, (int, float)):
        # Already a number: only range-checked kinds can reject it.
        repaired = REPAIRERS.get(kind, _repair_text)(str(value))
        if kind in {"latitude", "longitude", "percent", "rating", "money", "count", "year", "hours", "date", "timestamp"} and repaired is None:
            return None, CLEARED, kind
        return value, OK, kind
    if isinstance(value, (dict, list)):
        return value, OK, kind

    raw = _text(value)
    if raw.lower() in NULL_SENTINELS:
        # A placeholder is an absent value dressed up as a present one.
        return None, (CLEARED if raw else OK), kind

    repaired = REPAIRERS.get(kind, _repair_text)(raw)
    if repaired is None:
        return None, CLEARED, kind
    if isinstance(repaired, str):
        return repaired, (OK if repaired == raw else REPAIRED), kind
    return repaired, REPAIRED, kind


def clean_record(row: dict[str, Any], declared_types: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    """Clean every column of a record. Returns (cleaned_row, actions).

    `actions` maps column -> action for anything that changed, so callers can
    report what was repaired and hand the cleared columns to enrichment
    instead of silently losing them.
    """
    declared_types = declared_types or {}
    cleaned: dict[str, Any] = {}
    actions: dict[str, str] = {}
    for column, value in row.items():
        if column == "__meta":
            cleaned[column] = value
            continue
        new_value, action, _kind = clean_field_value(column, value, declared_types.get(column))
        cleaned[column] = new_value
        if action != OK:
            actions[column] = action
    return cleaned, actions
