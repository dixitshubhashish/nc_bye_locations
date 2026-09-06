"""Unit tests for official Domino's store locator API integration.

Tests store deduplication, session cookie warming, browser header injection, and Overpass fallback logic.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server
from whitespace_tool.sources import dominos_store_locator


class DominosStoreLocatorTests(unittest.TestCase):
    """Test suite for official Domino's store locator API requests and fallback mechanisms."""

    def test_fetch_for_zips_dedupes_stores_by_store_id(self) -> None:
        """Verify fetch_for_zips deduplicates store records by StoreID attribute."""
        payloads = {
            "10001": {"Stores": [{"StoreID": "10", "StoreName": "First"}, {"StoreID": "11", "StoreName": "Second"}]},
            "10002": {"Stores": [{"StoreID": "12", "StoreName": "Third"}, {"StoreID": "10", "StoreName": "First Duplicate"}]},
        }

        with patch.object(dominos_store_locator, "fetch_zip", side_effect=lambda zip_code, **_: payloads[zip_code]):
            result = dominos_store_locator.fetch_for_zips(["10001", "10002"], order_type="Delivery", one_per_zip=True)

        self.assertEqual([store["StoreID"] for store in result["Stores"]], ["10", "12"])
        self.assertEqual(len(result["Stores"]), 2)
        self.assertEqual(result["stores_per_zip"], 1)
        self.assertEqual({store["QueryZip"] for store in result["Stores"]}, {"10001", "10002"})
        self.assertTrue(result["one_per_zip"])
        self.assertEqual(result["errors"], [])

    def test_locator_session_warms_cookies_and_sends_browser_headers(self) -> None:
        """Verify DominosLocatorSession warms session cookies and attaches browser User-Agent headers."""
        opened = []

        class FakeResponse:
            def __init__(self, body: bytes) -> None:
                self.body = body

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return self.body

        class FakeOpener:
            def open(self, request, timeout=60):
                opened.append(SimpleNamespace(url=request.full_url, headers=dict(request.header_items()), timeout=timeout))
                if request.full_url == dominos_store_locator.ORDER_URL:
                    return FakeResponse(b"<html></html>")
                return FakeResponse(b'{"Stores":[]}')

        opener_handlers = []

        def fake_build_opener(*handlers):
            opener_handlers.extend(handlers)
            return FakeOpener()

        with patch.object(dominos_store_locator.urllib.request, "build_opener", side_effect=fake_build_opener):
            session = dominos_store_locator.DominosLocatorSession(min_interval_seconds=0)
            result = session.fetch_zip("90210", "Delivery")

        self.assertEqual(result, {"Stores": []})
        self.assertEqual([request.url for request in opened], [dominos_store_locator.ORDER_URL, "https://order.dominos.com/power/store-locator?s=&c=90210&type=Delivery"])
        self.assertTrue(any(handler.__class__.__name__ == "HTTPCookieProcessor" for handler in opener_handlers))
        self.assertEqual(opened[1].headers["Referer"], dominos_store_locator.ORDER_URL)
        self.assertIn("Chrome/124.0.0.0", opened[1].headers["User-agent"])
        self.assertEqual(opened[1].headers["Accept-language"], "en-US,en;q=0.9")

    def test_dominos_source_auto_falls_back_to_overpass_when_locator_is_blocked(self) -> None:
        """Verify dominos_source falls back to Overpass API when primary locator endpoint is blocked with 403."""
        with patch.object(workflow_server, "prepare_zipcodes", return_value={"status": "ready"}):
            with patch.object(workflow_server, "_warehouse_settings", return_value=("project", "bronze", None)):
                with patch.object(workflow_server, "_bigquery_client", return_value=object()):
                    with patch.object(workflow_server, "_dominos_zip_codes", return_value=["10001"]):
                        with patch.object(workflow_server, "fetch_for_zips", return_value={"Stores": [], "errors": [{"zip_code": "10001", "error": "HTTP Error 403: Forbidden"}]}):
                            with patch.object(workflow_server, "fetch_dominos_from_overpass", return_value={"source": "openstreetmap_overpass", "Stores": [{"StoreID": "osm-node-1"}], "errors": []}):
                                result = workflow_server.dominos_source(provider="auto", one_per_zip=True)

        self.assertEqual(result["source"], "openstreetmap_overpass")
        self.assertEqual(result["primary_errors"][0]["error"], "HTTP Error 403: Forbidden")
        self.assertEqual(result["requested_provider"], "auto")


if __name__ == "__main__":
    unittest.main()
