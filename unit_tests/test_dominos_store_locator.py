from __future__ import annotations

import unittest
from unittest.mock import patch

from whitespace_tool.sources import dominos_store_locator


class DominosStoreLocatorTests(unittest.TestCase):
    def test_fetch_for_zips_dedupes_stores_by_store_id(self) -> None:
        payloads = {
            "10001": {"Stores": [{"StoreID": "10", "StoreName": "First"}, {"StoreID": "11", "StoreName": "Second"}]},
            "10002": {"Stores": [{"StoreID": "12", "StoreName": "Third"}, {"StoreID": "10", "StoreName": "First Duplicate"}]},
        }

        with patch.object(dominos_store_locator, "fetch_zip", side_effect=lambda zip_code, **_: payloads[zip_code]):
            result = dominos_store_locator.fetch_for_zips(["10001", "10002"], order_type="Delivery", stores_per_zip=1)

        self.assertEqual([store["StoreID"] for store in result["Stores"]], ["10", "12"])
        self.assertEqual(len(result["Stores"]), 2)
        self.assertEqual(result["stores_per_zip"], 1)
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
