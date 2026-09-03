from __future__ import annotations

import csv
from importlib import import_module
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, utc_now_iso


def _clean_zip(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:5].zfill(5) if digits else ""


def _optional_float(value: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_locations_csv(path: str | Path, source_name: str, column_map: dict[str, str]) -> list[LocationRecord]:
    records: list[LocationRecord] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader, start=1):
            postal_code = _clean_zip(row.get(column_map.get("postal_code", "postal_code"), ""))
            if not postal_code:
                continue
            brand = row.get(column_map.get("brand", "brand"), "").strip()
            if not brand:
                continue
            location_id = row.get(column_map.get("location_id", "location_id"), "").strip()
            if not location_id:
                location_id = f"{brand.lower().replace(' ', '_')}:{postal_code}:{index}"
            records.append(
                LocationRecord(
                    brand=brand,
                    location_id=location_id,
                    name=row.get(column_map.get("name", "name"), "").strip(),
                    address=row.get(column_map.get("address", "address"), "").strip(),
                    city=row.get(column_map.get("city", "city"), "").strip(),
                    state=row.get(column_map.get("state", "state"), "").strip().upper(),
                    postal_code=postal_code,
                    latitude=_optional_float(row.get(column_map.get("latitude", "latitude"), "")),
                    longitude=_optional_float(row.get(column_map.get("longitude", "longitude"), "")),
                    source=source_name,
                    observed_at=row.get(column_map.get("observed_at", "observed_at"), "").strip() or utc_now_iso(),
                    raw=dict(row),
                )
            )
    return records


def load_location_sources(config: dict[str, Any]) -> list[LocationRecord]:
    all_records: list[LocationRecord] = []
    base_dir = Path(config["_config_dir"])
    for source in config["location_sources"]:
        if source["type"] in {"dominos_api", "pizza_hut_kaggle", "little_caesars_json"}:
            module = import_module(f"whitespace_tool.sources.{source['type']}")
            all_records.extend(module.load(source, base_dir))
            continue
        if source["type"] != "csv":
            raise ValueError(f"Unsupported location source type: {source['type']}")
        path = Path(source["path"])
        if not path.is_absolute():
            path = base_dir / path
        all_records.extend(load_locations_csv(path, source["name"], source.get("columns", {})))
    return all_records
