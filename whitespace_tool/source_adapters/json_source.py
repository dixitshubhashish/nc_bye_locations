"""JSON and GeoJSON source adapter for extracting structured record objects.

Supports automatic discovery of record arrays, GeoJSON FeatureCollection parsing,
flattening coordinates/properties, and candidate path extraction.
"""

from __future__ import annotations

import json
from typing import Any

from whitespace_tool.source_adapters.common import choose_json_records, find_record_arrays, preview_payload


def _is_geojson_feature(row: dict[str, Any]) -> bool:
    """Check if a dictionary represents a GeoJSON Feature object.

    Args:
        row: Object dictionary to test.

    Returns:
        True if the dictionary is a GeoJSON Feature, False otherwise.
    """
    return row.get("type") == "Feature" and isinstance(row.get("properties"), dict)


def _geojson_feature_to_row(feature: dict[str, Any]) -> dict[str, Any]:
    """Convert a GeoJSON Feature object into a flat tabular row dictionary.

    Args:
        feature: GeoJSON Feature dictionary.

    Returns:
        Flat dictionary with properties and extracted lat/lon coordinates.
    """
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
    """Transform extracted rows if they represent GeoJSON features.

    Args:
        rows: Raw record dictionary objects.

    Returns:
        Transformed row dictionaries.
    """
    if rows and all(_is_geojson_feature(row) for row in rows):
        return [_geojson_feature_to_row(row) for row in rows]
    return rows


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    """Parse JSON/GeoJSON content bytes and generate preview payload.

    Args:
        content: JSON bytes.
        record_path: Optional explicit dot-notated record array path.
        fields_only: If True, returns fields and sample rows without iterating full record set.

    Returns:
        Preview metadata dictionary including rows, fields, and record paths.
    """
    payload = json.loads(content.decode("utf-8-sig"))
    rows, resolved_path = choose_json_records(payload, record_path)
    rows = _prepare_rows(rows)

    # Cap memory usage: limit to 100k rows even on full preview
    MAX_ROWS_TO_LOAD = 100000
    if len(rows) > MAX_ROWS_TO_LOAD:
        rows = rows[:MAX_ROWS_TO_LOAD]

    # For lightweight field discovery, sample just first 10 rows to extract fields
    if fields_only:
        sample_rows = rows[:min(10, len(rows))]
        result = preview_payload(sample_rows, resolved_path, fields_only=True)
    else:
        result = preview_payload(rows, resolved_path)

    if isinstance(payload, list):
        record_paths = [""]
    else:
        record_paths = sorted({path for path, records in find_record_arrays(payload, max_depth=3) if any(isinstance(row, dict) for row in records)})
    result["record_paths"] = record_paths
    return result

