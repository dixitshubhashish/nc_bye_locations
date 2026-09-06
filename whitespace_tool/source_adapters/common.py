"""Common utility functions for source adapters in the whitespace analysis tool.

Provides helper routines for flattening nested dictionary/list structures,
collecting field names, extracting nested JSON paths, and selecting record arrays.
"""

from __future__ import annotations

from typing import Any


def flatten_object(value: Any, prefix: str = "", output: dict[str, Any] | None = None) -> dict[str, Any]:
    """Flatten a nested dictionary or list structure into a single-level dictionary.

    Args:
        value: The nested object (dict, list, or primitive) to flatten.
        prefix: Prefix key for recursively flattened paths.
        output: Dictionary accumulator for flattened results.

    Returns:
        A dictionary with dot-separated keys representing the flattened structure.
    """
    if output is None:
        output = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flatten_object(child, path, output)
    elif isinstance(value, list):
        output[prefix] = value
    else:
        output[prefix] = value
    return output


def collect_fields(rows: list[dict[str, Any]]) -> list[str]:
    """Collect all unique field names across a list of row dictionaries.

    Args:
        rows: List of row dictionaries.

    Returns:
        Sorted list of field names.
    """
    fields: set[str] = set()
    for row in rows:
        fields.update(field for field in flatten_object(row).keys() if field and str(field).strip())
    return sorted(fields)


def preview_payload(rows: list[dict[str, Any]], record_path: str | None = None, limit: int = 25, fields_only: bool = False) -> dict[str, Any]:
    """Build a preview response dictionary for a dataset.

    Args:
        rows: List of extracted record dictionaries.
        record_path: Dot-notated path where records were found.
        limit: Max rows for preview.
        fields_only: If True, samples initial rows to extract fields quickly without full payload iteration.

    Returns:
        Preview metadata dictionary containing counts, fields, and preview rows.
    """
    if fields_only and len(rows) > 0:
        sample_rows = rows[:min(10, len(rows))]
        fields = collect_fields(sample_rows)
        return {
            "record_path": record_path or "",
            "record_count": len(rows),
            "fields": fields,
            "rows": sample_rows,
            "preview_rows": sample_rows,
        }
    return {
        "record_path": record_path or "",
        "record_count": len(rows),
        "fields": collect_fields(rows),
        "rows": rows,
        "preview_rows": rows[:limit],
    }


def find_record_arrays(value: Any, prefix: str = "", max_depth: int | None = None) -> list[tuple[str, list[Any]]]:
    """Find candidate record arrays in a nested structure.

    Args:
        value: Nested object to traverse.
        prefix: Current dot-notated key path.
        max_depth: Optional depth limit.

    Returns:
        List of (path, array) tuples.
    """
    found: list[tuple[str, list[Any]]] = []
    if isinstance(value, list):
        found.append((prefix, value))
    elif isinstance(value, dict):
        if max_depth is not None and prefix and len(prefix.split(".")) >= max_depth:
            return found
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(find_record_arrays(child, path, max_depth))
    return found


def get_nested(value: Any, path: str) -> Any:
    """Traverse a nested dictionary path using dot notation.

    Args:
        value: Base dictionary or value.
        path: Dot-separated path string.

    Returns:
        Value at target path.

    Raises:
        KeyError: If path navigation fails.
    """
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def choose_json_records(payload: Any, record_path: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """Select appropriate array of records from a parsed JSON payload.

    Args:
        payload: Parsed JSON structure.
        record_path: Optional explicit dot-notated path to record array.

    Returns:
        Tuple of (list of record dicts, resolved path string).

    Raises:
        ValueError: If record_path does not resolve to an array or no array is found.
    """
    if record_path:
        records = get_nested(payload, record_path)
        if not isinstance(records, list):
            raise ValueError("record_path must resolve to a JSON array")
        return [row for row in records if isinstance(row, dict)], record_path
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], ""

    arrays = find_record_arrays(payload)
    if not arrays:
        raise ValueError("No JSON array of records found")
    arrays.sort(key=lambda item: len(item[1]), reverse=True)
    selected_path, selected_records = arrays[0]
    return [row for row in selected_records if isinstance(row, dict)], selected_path
