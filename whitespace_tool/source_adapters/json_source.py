from __future__ import annotations

import json
from typing import Any

from whitespace_tool.source_adapters.common import choose_json_records, find_record_arrays, preview_payload


def _is_geojson_feature(row: dict[str, Any]) -> bool:
    return row.get("type") == "Feature" and isinstance(row.get("properties"), dict)


def _geojson_feature_to_row(feature: dict[str, Any]) -> dict[str, Any]:
    row = dict(feature["properties"])
    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
    coordinates = geometry.get("coordinates")
    row["geojson_type"] = feature.get("type")
    row["geometry_type"] = geometry.get("type")
    row["geometry_coordinates"] = coordinates
    if feature.get("id") is not None:
        row["feature_id"] = feature["id"]
    if geometry.get("type") == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        row["longitude"] = coordinates[0]
        row["latitude"] = coordinates[1]
    return row


def _prepare_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if rows and all(_is_geojson_feature(row) for row in rows):
        return [_geojson_feature_to_row(row) for row in rows]
    return rows


def preview(content: bytes, record_path: str | None = None) -> dict:
    payload = json.loads(content.decode("utf-8-sig"))
    rows, resolved_path = choose_json_records(payload, record_path)
    rows = _prepare_rows(rows)
    result = preview_payload(rows, resolved_path)
    if isinstance(payload, list):
        record_paths = [""]
    else:
        record_paths = sorted({path for path, records in find_record_arrays(payload, max_depth=3) if any(isinstance(row, dict) for row in records)})
    result["record_paths"] = record_paths
    return result
