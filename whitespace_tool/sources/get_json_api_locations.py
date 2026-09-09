"""GET JSON API location source - the `api_get_json` source format.

Config-side counterpart of the app's GET JSON API source type
(`whitespace_tool/source_adapters/api_get_source.py`, which serves the mapper
screen). The difference from `json_locations.py` is not the payload - both end
up parsing a JSON document - it is the *request*: a live public endpoint is
called with URL query parameters and request headers, and it has house rules
that a static file does not.

Little Caesars is the GET JSON API demo brand, so `config/demo.json` points its
Little Caesars entry here. Named for the format, not the brand, for the same
reason as `json_locations.py`.

Three things this does that plain JSON fetching does not, all of them required
by the demo endpoint rather than nice-to-have:

  1. An identifying User-Agent. The OSM/Nominatim usage policy blocks anonymous
     and default-library agents outright, so this is a hard requirement.
  2. At most one request per second. The pacing state is module-level rather
     than per-call because the limit is per *client*: two API sources in one
     config run would otherwise each believe they were the only caller and
     burst two requests into the same second.
  3. Clamping `limit` to what the host will actually honour. Measured against
     Nominatim: limit=50 returns 50 rows, limit=200 returns 50, limit=1000
     returns 50 - it accepts the larger number and silently ignores it. Without
     the clamp a config could claim to pull thousands of rows while the demo
     quietly returned 50 and nobody noticed the gap.
"""

from __future__ import annotations

from pathlib import Path
import threading
from time import monotonic, sleep
from typing import Any
import urllib.parse
import urllib.request

from whitespace_tool.models import LocationRecord
from whitespace_tool.sources.json_locations import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    normalize_rows,
    records_from_payload,
    resolve_mapper,
)
import json


HOST_ROW_LIMITS = {
    "nominatim.openstreetmap.org": 50,
}

_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_pace_lock = threading.Lock()
_last_request_at = 0.0


def _pace_request(host: str) -> None:
    global _last_request_at
    if host not in HOST_ROW_LIMITS:
        return
    with _pace_lock:
        elapsed = monotonic() - _last_request_at
        if elapsed < _MIN_REQUEST_INTERVAL_SECONDS:
            sleep(_MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_request_at = monotonic()


def _clean_pairs(pairs: Any) -> dict[str, str]:
    """Accept either a plain mapping or the app's `[{key, value}]` pair-row
    shape, so a config entry can be pasted straight out of what the GET API
    screen builds without a translation step."""
    if isinstance(pairs, dict):
        return {str(key): str(value) for key, value in pairs.items() if str(key).strip()}
    cleaned: dict[str, str] = {}
    for pair in pairs or []:
        if not isinstance(pair, dict):
            continue
        key = str(pair.get("key", "")).strip()
        if key:
            cleaned[key] = str(pair.get("value", "")).strip()
    return cleaned


def build_request_url(url: str, query_params: Any = None) -> str:
    """Merge configured query params into the URL and clamp any row limit to
    what the host will actually honour."""
    parts = urllib.parse.urlsplit(url)
    merged = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    merged.update(_clean_pairs(query_params))
    ceiling = HOST_ROW_LIMITS.get(parts.netloc.lower())
    if ceiling and merged.get("limit"):
        try:
            merged["limit"] = str(max(1, min(int(merged["limit"]), ceiling)))
        except ValueError:
            merged["limit"] = str(ceiling)
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(merged), parts.fragment))


def fetch_payload(source: dict[str, Any]) -> Any:
    request_url = build_request_url(str(source["url"]), source.get("query_params"))
    headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
    headers.update(_clean_pairs(source.get("headers")))
    _pace_request(urllib.parse.urlsplit(request_url).netloc.lower())
    request = urllib.request.Request(request_url, headers=headers)
    with urllib.request.urlopen(request, timeout=int(source.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def load(source: dict[str, Any], config_dir: Path) -> list[LocationRecord]:
    mapper = resolve_mapper(source, config_dir)
    if source.get("sample_path"):
        # Replay a captured payload so an offline or CI run of `analyze` neither
        # depends on the public endpoint being up nor spends its rate budget.
        with (config_dir / source["sample_path"]).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        payload = fetch_payload(source)
    rows = records_from_payload(payload, mapper.get("record_path", ""))
    return normalize_rows(rows, mapper, source["name"])
