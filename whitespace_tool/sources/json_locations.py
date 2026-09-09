"""JSON document location source - the `json` source format.

This is the config-side counterpart of the app's JSON source type
(`whitespace_tool/source_adapters/json_source.py`, which serves the mapper
screen). It reads one JSON document - from a local file or from a URL - and
normalizes its records through a mapper.

Domino's is the JSON demo brand, so `config/demo.json` points its Domino's
entry here. The module is named for the *format* rather than for Domino's on
purpose: the demo brand for a format can change, and the repo's adapter layer
exists precisely so a brand can move between formats without a code change.
That is also why this module replaced two brand-named predecessors that did
exactly this job under misleading names:

  * `little_caesars_json.py` - a local-JSON-file loader. Little Caesars is now
    the GET JSON API demo, so a "_json" module named after it actively told the
    reader the wrong thing.
  * `dominos_api.py` - a GET-a-JSON-URL loader whose "_api" name pointed at the
    other format entirely, and which had none of the request manners a public
    endpoint needs (see `get_json_api_locations.py`).

Neither had any importer outside the type dispatcher in `csv_locations.py`, so
both were removed rather than left as aliases. Their old `type` strings still
resolve here - see `LOCATION_SOURCE_MODULES` - so existing configs keep working.

The helpers below are shared with `get_json_api_locations.py`: a GET JSON API
response *is* a JSON document, it just arrives with request options attached.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import urllib.request

from whitespace_tool.models import LocationRecord
from whitespace_tool.normalization import load_mapper, normalize_location


DEFAULT_USER_AGENT = "CompetitiveWhitespaceTool/1.0"
DEFAULT_TIMEOUT_SECONDS = 60


def resolve_mapper(source: dict[str, Any], config_dir: Path) -> dict[str, Any]:
    """`mapper` may be a path to a workflow template *or* the mapping written
    inline. Inline exists so a one-off demo entry does not have to spawn a
    template file that nothing else will ever reference; a mapping shared by
    more than one config still belongs in `config/workflow_templates/`."""
    mapper = source["mapper"]
    return mapper if isinstance(mapper, dict) else load_mapper(config_dir / mapper)


def records_from_payload(payload: Any, record_path: str) -> list[dict[str, Any]]:
    """Walk `record_path` to the record array.

    An empty `record_path` is normal, not a fallback: Nominatim answers with a
    bare top-level array while the Domino's document nests under "Stores", and
    the two demos are set up to show exactly that contrast.
    """
    current = payload
    if record_path:
        for part in record_path.split("."):
            current = current[part]
    if not isinstance(current, list):
        raise ValueError("JSON mapper record_path must resolve to a list")
    return [row for row in current if isinstance(row, dict)]


def normalize_rows(rows: list[dict[str, Any]], mapper: dict[str, Any], source_name: str) -> list[LocationRecord]:
    return [
        record
        for index, row in enumerate(rows, start=1)
        if (record := normalize_location(row, mapper, source_name, index)) is not None
    ]


def fetch_json_url(url: str, headers: dict[str, str] | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> Any:
    request_headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def read_json_payload(source: dict[str, Any], config_dir: Path) -> Any:
    """A JSON document reaches us one of three ways, in priority order.

    `sample_path` wins so a CI or offline run of `analyze` can replay a captured
    payload instead of depending on a public endpoint being reachable.
    """
    local = source.get("sample_path") or source.get("path")
    if local:
        with (config_dir / local).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return fetch_json_url(
        str(source["url"]),
        source.get("headers") if isinstance(source.get("headers"), dict) else None,
        int(source.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
    )


def load(source: dict[str, Any], config_dir: Path) -> list[LocationRecord]:
    mapper = resolve_mapper(source, config_dir)
    payload = read_json_payload(source, config_dir)
    rows = records_from_payload(payload, mapper.get("record_path", ""))
    return normalize_rows(rows, mapper, source["name"])
