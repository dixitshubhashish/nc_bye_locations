from __future__ import annotations

import unittest
from unittest.mock import patch

from whitespace_tool.sources import dominos_overpass


class DominosOverpassTests(unittest.TestCase):
    def test_fetch_for_zips_outputs_dominos_store_shape(self) -> None:
        elements = {
            "10001": [
                {
                    "type": "node",
                    "id": 10,
                    "lat": 40.1,
                    "lon": -73.9,
                    "tags": {
                        "name": "Domino's Pizza",
                        "addr:housenumber": "1",
                        "addr:street": "Main St",
                        "addr:city": "New York",
                        "addr:state": "NY",
                        "addr:postcode": "10001",
                    },
                },
                {"type": "node", "id": 11, "lat": 40.2, "lon": -73.8, "tags": {"name": "Domino's"}},
            ],
            "10002": [
                {
                    "type": "way",
                    "id": 20,
                    "center": {"lat": 41.1, "lon": -74.2},
                    "tags": {"name": "Domino's Pizza", "addr:city": "New York"},
                }
            ],
        }

        with patch.object(dominos_overpass.OverpassSession, "fetch_zip", side_effect=lambda zip_code: elements[zip_code]):
            result = dominos_overpass.fetch_for_zips(["10001", "10002"], one_per_zip=True, max_workers=1)

        self.assertEqual([store["StoreID"] for store in result["Stores"]], ["osm-node-10", "osm-way-20"])
        self.assertEqual(result["Stores"][0]["AddressDescription"], "1 Main St")
        self.assertEqual(result["Stores"][0]["QueryZip"], "10001")
        self.assertEqual(result["Stores"][1]["PostalCode"], "10002")
        self.assertEqual(result["source"], "openstreetmap_overpass")


if __name__ == "__main__":
    unittest.main()
