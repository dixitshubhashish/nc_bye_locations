"""CSV file source adapter for parsing comma-separated text into structured row dictionaries.

Handles UTF-8/BOM text decoding, standard CSV DictReader parsing, and preview payload creation.
"""

from __future__ import annotations

import csv
import io

from whitespace_tool.source_adapters.common import preview_payload


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    """Parse CSV content bytes and generate preview metadata.

    Args:
        content: Raw CSV bytes.
        record_path: Optional unused parameter for API compatibility.
        fields_only: If True, returns fields and estimated count without processing rows.

    Returns:
        Preview dictionary containing extracted rows, counts, and field lists.
    """
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # For lightweight field discovery, just get headers without processing rows
    if fields_only:
        # Estimate row count by counting newlines (excludes header)
        estimated_rows = text.count("\n") - 1 if "\n" in text else 0
        return {
            "record_path": record_path or "",
            "record_count": max(0, estimated_rows),
            "fields": [f for f in (reader.fieldnames or []) if f],
            "rows": [],
            "preview_rows": [],
        }

    # For full parsing, load rows efficiently with a batch limit to avoid memory issues
    MAX_ROWS_TO_LOAD = 100000  # Cap at 100k rows for a single preview call
    rows = []
    for idx, row in enumerate(reader):
        if idx >= MAX_ROWS_TO_LOAD:
            break
        rows.append(dict(row))
    return preview_payload(rows, record_path)

