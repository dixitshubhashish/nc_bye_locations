from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from whitespace_tool.mapper import load_mapper, normalize_location
from whitespace_tool.models import LocationRecord


def load(source: dict[str, Any], config_dir: Path) -> list[LocationRecord]:
    mapper = load_mapper(config_dir / source["mapper"])
    path = config_dir / source["path"]
    records: list[LocationRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader, start=1):
            record = normalize_location(row, mapper, source["name"], index)
            if record:
                records.append(record)
    return records
