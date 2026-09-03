from __future__ import annotations

from typing import Any


def flatten_object(value: Any, prefix: str = "", output: dict[str, Any] | None = None) -> dict[str, Any]:
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


def collect_fields(rows: list[dict[str, Any]], limit: int = 50) -> list[str]:
    fields: set[str] = set()
    for row in rows[:limit]:
        fields.update(flatten_object(row).keys())
    return sorted(fields)


def preview_payload(rows: list[dict[str, Any]], record_path: str | None = None, limit: int = 25) -> dict[str, Any]:
    return {
        "record_path": record_path or "",
        "record_count": len(rows),
        "fields": collect_fields(rows),
        "rows": rows[:limit],
    }


def find_record_arrays(value: Any, prefix: str = "") -> list[tuple[str, list[Any]]]:
    found: list[tuple[str, list[Any]]] = []
    if isinstance(value, list):
        found.append((prefix, value))
    elif isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            found.extend(find_record_arrays(child, path))
    return found


def get_nested(value: Any, path: str) -> Any:
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
