"""Unit tests for remote public HTTP source limits and Socrata URL query parameter capping.

Tests payload size limits, automatic Socrata URL row-limiting fallbacks, and error threshold safety.
"""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from whitespace_tool.mapping.sources import (
    MAX_REMOTE_SOURCE_BYTES,
    MIN_REMOTE_SOURCE_ROW_LIMIT,
    REMOTE_SOURCE_ROW_LIMITS,
    REMOTE_SOURCE_TIMEOUT_SECONDS,
    fetch_public_source,
)


class RemoteSourceLimitTests(unittest.TestCase):
    """Test suite for remote public HTTP source limit capping."""

    def test_large_socrata_source_retries_with_largest_safe_row_limit(self) -> None:
        """Verify fetch_public_source retries Socrata URLs with row limits when initial payload exceeds max size."""
        large_payload = b"x" * 1025
        limited_payload = json.dumps({"data": [{"name": "Cafe"}]}).encode("utf-8")
        calls: list[str] = []

        def fake_request(url: str) -> tuple[bytes, str]:
            calls.append(url)
            if len(calls) <= 3:
                return large_payload, "query.json"
            return limited_payload, "query.json"

        with patch("whitespace_tool.mapping.sources.MAX_REMOTE_SOURCE_BYTES", 1024), patch("whitespace_tool.mapping.sources._remote_source_request", side_effect=fake_request):
            result = fetch_public_source({"url": "https://data.lacity.org/api/v3/views/29fd-3paw/query.json"})

        self.assertTrue(result["limited"])
        self.assertEqual(result["limited_rows"], 50000)
        self.assertIn("%24limit=50000", result["limited_url"])
        decoded = base64.b64decode(result["content_base64"])
        self.assertEqual(json.loads(decoded), {"data": [{"name": "Cafe"}]})

    def test_automatic_source_limits_never_drop_below_large_batch_rows(self) -> None:
        """Verify automatic row limits enforce minimum threshold values."""
        self.assertEqual(REMOTE_SOURCE_ROW_LIMITS[-1], MIN_REMOTE_SOURCE_ROW_LIMIT)
        self.assertGreaterEqual(MIN_REMOTE_SOURCE_ROW_LIMIT, 10000)
        self.assertTrue(all(limit >= MIN_REMOTE_SOURCE_ROW_LIMIT for limit in REMOTE_SOURCE_ROW_LIMITS))
        self.assertGreaterEqual(MAX_REMOTE_SOURCE_BYTES, 100 * 1024 * 1024)
        self.assertGreaterEqual(REMOTE_SOURCE_TIMEOUT_SECONDS, 60)

    def test_large_socrata_source_errors_instead_of_loading_tiny_demo(self) -> None:
        """Verify fetch_public_source raises ValueError if payload remains too large after all row limits."""
        large_payload = b"x" * 1025
        with patch("whitespace_tool.mapping.sources.MAX_REMOTE_SOURCE_BYTES", 1024), patch("whitespace_tool.mapping.sources._remote_source_request", return_value=(large_payload, "query.json")):
            with self.assertRaisesRegex(ValueError, "will not load fewer than 10000 rows"):
                fetch_public_source({"url": "https://data.lacity.org/api/v3/views/29fd-3paw/query.json"})

    def test_large_non_socrata_source_still_errors(self) -> None:
        """Verify fetch_public_source raises ValueError for oversized non-Socrata URLs."""
        large_payload = b"x" * 1025
        with patch("whitespace_tool.mapping.sources.MAX_REMOTE_SOURCE_BYTES", 1024), patch("whitespace_tool.mapping.sources._remote_source_request", return_value=(large_payload, "locations.json")):
            with self.assertRaisesRegex(ValueError, "will not load fewer than 10000 rows"):
                fetch_public_source({"url": "https://example.com/locations.json"})


if __name__ == "__main__":
    unittest.main()
