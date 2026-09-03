from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from whitespace_tool.mapper import load_mapper, normalize_location
from whitespace_tool.models import LocationRecord


def _records_from_payload(payload: Any, record_path: str) -> list[dict[str, Any]]:
    current = payload
    if record_path:
        for part in record_path.split("."):
            current = current[part]
    if not isinstance(current, list):
        raise ValueError("Domino's API mapper record_path must resolve to a list")
    return [row for row in current if isinstance(row, dict)]


def load(source: dict[str, Any], config_dir: Path) -> list[LocationRecord]:
    mapper = load_mapper(config_dir / source["mapper"])
    if source.get("sample_path"):
        with (config_dir / source["sample_path"]).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    else:
        request = urllib.request.Request(source["url"], headers=source.get("headers", {}))
        with urllib.request.urlopen(request, timeout=int(source.get("timeout_seconds", 60))) as response:
            payload = json.loads(response.read().decode("utf-8"))

    rows = _records_from_payload(payload, mapper.get("record_path", ""))
    return [
        record
        for index, row in enumerate(rows, start=1)
        if (record := normalize_location(row, mapper, source["name"], index)) is not None
    ]
