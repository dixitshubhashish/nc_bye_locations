"""Keyless brand-identity enrichment: website, phone, email.

Deliberately no API keys. Everything here uses openly reachable endpoints, so
it works in this deployment as-is rather than waiting on credentials:

  1. OpenStreetMap / Overpass - POIs carry `website`, `phone`, `contact:email`
     tags for a great many brands, and the repo already talks to Overpass for
     Domino's, so the dependency is not new.
  2. DuckDuckGo Instant Answer (no key) - resolves a brand name to its
     official site when OSM has no website tag.

Anything it cannot establish is left blank for the brand owner to fill in.
The point is to raise coverage where a free source genuinely knows the answer,
never to invent a plausible-looking value (INV-15): every field returned here
carries the source that produced it.
"""

from __future__ import annotations

import json
import logging
import re
import socket
from typing import Any
from urllib.parse import quote_plus, urlparse
import urllib.error
import urllib.request

LOGGER = logging.getLogger("whitespace_tool.workflow")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "birdeye-whitespace-tool/1.0 (brand enrichment)"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-z]{2,}$", re.I)
_PHONE_DIGITS = re.compile(r"[^\d+]")

# Hosts that are never a brand's own site, so a search result pointing at one
# is a false positive rather than an answer.
_NON_BRAND_HOSTS = frozenset({
    "wikipedia.org", "en.wikipedia.org", "facebook.com", "www.facebook.com",
    "twitter.com", "x.com", "instagram.com", "linkedin.com", "youtube.com",
    "yelp.com", "tripadvisor.com", "duckduckgo.com", "crunchbase.com",
})


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _clean_website(value: str) -> str:
    """Normalise to a scheme-qualified URL, rejecting aggregator hosts."""
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    if not candidate.lower().startswith(("http://", "https://")):
        candidate = f"https://{candidate}"
    try:
        host = (urlparse(candidate).hostname or "").lower()
    except ValueError:
        return ""
    if not host or "." not in host:
        return ""
    bare = host[4:] if host.startswith("www.") else host
    if host in _NON_BRAND_HOSTS or bare in _NON_BRAND_HOSTS:
        return ""
    return candidate


def _clean_phone(value: str) -> str:
    digits = _PHONE_DIGITS.sub("", str(value or ""))
    plus = digits.startswith("+")
    bare = digits.lstrip("+")
    if not 7 <= len(bare) <= 15:
        return ""
    return f"+{bare}" if plus else bare


def _clean_email(value: str) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if _EMAIL.match(candidate) else ""


def enrich_from_openstreetmap(brand_name: str, country_code: str = "") -> dict[str, Any]:
    """Contact tags OSM already holds for this brand.

    Queried by `brand` / `name` tag rather than by location, so one call
    covers the brand rather than a single store.
    """
    name = str(brand_name or "").strip()
    if not name:
        return {}
    area = f'["ISO3166-1"="{country_code.upper()}"]' if len(str(country_code or "")) == 2 else ""
    scope = f"area{area}->.a;" if area else ""
    within = "(area.a)" if area else ""
    query = (
        "[out:json][timeout:10];"
        f"{scope}"
        f'nwr["brand"~"^{re.escape(name)}$",i]{within};'
        "out tags 25;"
    )
    try:
        payload = _get_json(f"{OVERPASS_URL}?data={quote_plus(query)}")
    except (urllib.error.URLError, socket.timeout, ValueError, TimeoutError) as exc:
        LOGGER.info("brand_enrichment_osm_unavailable brand=%s error=%s", name, exc)
        return {}

    # Take the most frequently agreed value per field: one mistagged POI
    # should not outvote the rest.
    tallies: dict[str, dict[str, int]] = {"website_url": {}, "phone_number": {}, "email": {}}
    for element in (payload or {}).get("elements", []) or []:
        tags = element.get("tags") or {}
        for field, cleaner, keys in (
            ("website_url", _clean_website, ("website", "contact:website", "url")),
            ("phone_number", _clean_phone, ("phone", "contact:phone")),
            ("email", _clean_email, ("email", "contact:email")),
        ):
            for key in keys:
                cleaned = cleaner(tags.get(key, ""))
                if cleaned:
                    tallies[field][cleaned] = tallies[field].get(cleaned, 0) + 1
                    break

    resolved: dict[str, Any] = {}
    for field, counts in tallies.items():
        if counts:
            best = max(counts.items(), key=lambda item: item[1])
            resolved[field] = best[0]
            resolved[f"{field}_source"] = "openstreetmap"
            resolved[f"{field}_agreement"] = best[1]
    return resolved


def enrich_website_from_search(brand_name: str) -> dict[str, Any]:
    """Official site via DuckDuckGo's keyless Instant Answer endpoint."""
    name = str(brand_name or "").strip()
    if not name:
        return {}
    url = f"{DUCKDUCKGO_URL}?q={quote_plus(name)}&format=json&no_html=1&skip_disambig=1"
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, socket.timeout, ValueError, TimeoutError) as exc:
        LOGGER.info("brand_enrichment_search_unavailable brand=%s error=%s", name, exc)
        return {}
    for key in ("AbstractURL", "OfficialWebsite"):
        website = _clean_website((payload or {}).get(key, ""))
        if website:
            return {"website_url": website, "website_url_source": "duckduckgo"}
    for result in ((payload or {}).get("Results") or [])[:3]:
        website = _clean_website(result.get("FirstURL", ""))
        if website:
            return {"website_url": website, "website_url_source": "duckduckgo"}
    return {}


def enrich_brand_identity(brand_name: str, country_code: str = "",
                          existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill only the contact fields that are currently blank.

    Never overwrites a value a human already supplied - an owner-entered phone
    number outranks anything a public source guessed. Returns only the fields
    it could actually establish, each tagged with where it came from, so an
    unresolved field stays visibly unresolved instead of being filled with a
    plausible-looking placeholder.
    """
    existing = existing or {}
    wanted = [field for field in ("website_url", "phone_number", "email")
              if not str(existing.get(field) or "").strip()]
    if not wanted:
        return {}

    resolved: dict[str, Any] = {}
    osm = enrich_from_openstreetmap(brand_name, country_code)
    for field in wanted:
        if osm.get(field):
            resolved[field] = osm[field]
            resolved[f"{field}_source"] = osm.get(f"{field}_source", "openstreetmap")

    if "website_url" in wanted and not resolved.get("website_url"):
        resolved.update(enrich_website_from_search(brand_name))

    resolved["unresolved_fields"] = [f for f in wanted if not resolved.get(f)]
    return resolved


def _name_tokens(value: str) -> set[str]:
    """Lowercased alphanumeric words, for loose store-name matching."""
    return {token for token in re.split(r"[^a-z0-9]+", str(value or "").lower()) if len(token) > 2}


def _names_match(wanted: str, candidate: str) -> bool:
    """True when an OSM POI plausibly IS this store.

    Deliberately loose on formatting ("Domino's Pizza #4412" vs "Dominos
    Pizza") but strict on identity: at least one meaningful word has to be
    shared, so the pizza place next door does not donate its phone number to
    a coffee shop.
    """
    wanted_tokens = _name_tokens(wanted)
    if not wanted_tokens:
        return False
    return bool(wanted_tokens & _name_tokens(candidate))


def enrich_location_contact(store_name: str, latitude: float, longitude: float,
                            radius_m: int = 150) -> dict[str, Any]:
    """Contact tags OSM holds for the POI standing at these coordinates.

    Unlike enrich_from_openstreetmap(), which answers for a whole brand, this
    answers for ONE store - so a phone number it returns is that store's own,
    not a corporate line copied onto every listing. The name check is what
    keeps it honest: an unnamed or unrelated POI inside the radius is ignored
    rather than harvested, and a store OSM has never heard of returns {}.
    """
    name = str(store_name or "").strip()
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return {}
    if not name or not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return {}
    radius = max(25, min(int(radius_m or 150), 500))
    query = (
        "[out:json][timeout:10];"
        f"nwr(around:{radius},{lat:.6f},{lon:.6f});"
        "out tags 40;"
    )
    try:
        payload = _get_json(f"{OVERPASS_URL}?data={quote_plus(query)}")
    except (urllib.error.URLError, socket.timeout, ValueError, TimeoutError) as exc:
        LOGGER.info("location_enrichment_osm_unavailable name=%s error=%s", name, exc)
        return {}

    for element in (payload or {}).get("elements", []) or []:
        tags = element.get("tags") or {}
        candidate = tags.get("name") or tags.get("brand") or ""
        if not _names_match(name, candidate):
            continue
        resolved: dict[str, Any] = {}
        for field, cleaner, keys in (
            ("website_url", _clean_website, ("website", "contact:website", "url")),
            ("phone_number", _clean_phone, ("phone", "contact:phone")),
            ("email", _clean_email, ("email", "contact:email")),
        ):
            for key in keys:
                cleaned = cleaner(tags.get(key, ""))
                if cleaned:
                    resolved[field] = cleaned
                    resolved[f"{field}_source"] = "openstreetmap"
                    break
        # Only a POI that actually carried a contact tag is an answer; a
        # name match with nothing on it is not worth returning.
        if resolved:
            resolved["matched_name"] = candidate
            return resolved
    return {}
