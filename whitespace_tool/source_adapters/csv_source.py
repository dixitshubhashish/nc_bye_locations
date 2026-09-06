from __future__ import annotations

import csv
import io

from whitespace_tool.source_adapters.common import MAPPER_SAMPLE_ROWS, preview_payload


def preview(content: bytes, record_path: str | None = None, fields_only: bool = False) -> dict:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # Keep the mapper fast, but return a small real sample so the UI can render
    # the tabular preview and Save can distinguish a parsed source from a
    # source where only headers were inspected.
    if fields_only:
        # Estimate row count by counting newlines (excludes header)
        estimated_rows = text.count('\n') - 1 if '\n' in text else 0
        sample_rows = [dict(row) for _, row in zip(range(MAPPER_SAMPLE_ROWS), reader)]
        result = preview_payload(sample_rows, record_path, fields_only=True)
        result["record_count"] = max(0, estimated_rows)
        return result

    # For full parsing, load rows efficiently with a batch limit to avoid memory issues
    # (though most real data will come via batched saves, not this endpoint)
    MAX_ROWS_TO_LOAD = 100000  # Cap at 100k rows for a single preview call
    rows = []
    for idx, row in enumerate(reader):
        if idx >= MAX_ROWS_TO_LOAD:
            break
        rows.append(dict(row))
    return preview_payload(rows, record_path)
