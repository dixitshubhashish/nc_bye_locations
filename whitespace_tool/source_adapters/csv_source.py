from __future__ import annotations

import csv
import io

from whitespace_tool.source_adapters.common import preview_payload


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # For lightweight field discovery, just get headers without processing rows
    if fields_only:
        # Estimate row count by counting newlines (excludes header)
        estimated_rows = text.count('\n') - 1 if '\n' in text else 0
        return {
            "record_path": record_path or "",
            "record_count": max(0, estimated_rows),
            "fields": [f for f in (reader.fieldnames or []) if f],
            "rows": [],
            "preview_rows": [],
        }

    # For full parsing, load rows efficiently with a batch limit to avoid memory issues
    # (though most real data will come via batched saves, not this endpoint)
    MAX_ROWS_TO_LOAD = 100000  # Cap at 100k rows for a single preview call
    rows = []
    for idx, row in enumerate(reader):
        if idx >= MAX_ROWS_TO_LOAD:
            break
        rows.append(dict(row))
    return preview_payload(rows, record_path)
