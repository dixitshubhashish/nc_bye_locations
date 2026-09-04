from __future__ import annotations

import unittest
from pathlib import Path
import json

from whitespace_tool.workflow_server import predefined_templates, save_mapper
from whitespace_tool.data_validation import validate_normalized_location, validate_source_row
from whitespace_tool.field_registry import load_field_registry
from whitespace_tool.normalization import normalize_location


class DemoDataValidationTests(unittest.TestCase):
    def test_predefined_demo_templates_exist_and_are_valid(self) -> None:
        """Verify all predefined brand templates load successfully."""
        templates_res = predefined_templates()
        templates = templates_res.get("templates", [])
        self.assertGreaterEqual(len(templates), 3, "Should have Domino's, Pizza Hut, and Little Caesars templates")
        
        brands = {t["brand"] for t in templates}
        self.assertTrue({"Domino's", "Pizza Hut", "Little Caesars"} <= brands)

    def test_demo_data_with_bad_rows_routes_to_error_listings(self) -> None:
        """Verify that demo data containing malformed or missing fields correctly routes bad rows to error_listings."""
        template = predefined_templates()["templates"][0]["mapper"]
        
        # Mixed demo batch: 1 good row, 2 bad rows
        demo_rows = [
            # Good row
            {
                "StoreID": "1001",
                "StoreName": "Domino's Pizza Downtown",
                "AddressDescription": "123 Main St",
                "City": "Raleigh",
                "Region": "NC",
                "PostalCode": "27601",
                "Phone": "9195550100"
            },
            # Bad row 1: Malformed ZIP (not 5 digits)
            {
                "StoreID": "1002",
                "StoreName": "Domino's Pizza Bad Zip",
                "AddressDescription": "456 Bad Zip Rd",
                "City": "Durham",
                "Region": "NC",
                "PostalCode": "999",  # Bad ZIP
                "Phone": "9195550200"
            },
            # Bad row 2: Missing postal code entirely
            {
                "StoreID": "1003",
                "StoreName": "Domino's Pizza No Zip",
                "AddressDescription": "789 No Zip Ave",
                "City": "Cary",
                "Region": "NC",
                "PostalCode": ""  # Missing mandatory ZIP
            }
        ]

        field_defs = load_field_registry()
        valid_locations = []
        error_listings = []

        for idx, row in enumerate(demo_rows):
            loc = normalize_location(row, template, "dominos_demo", idx)
            if loc is None:
                error_listings.append({"row": idx + 1, "reason": "missing brand or postal code"})
                continue
            
            errs = validate_normalized_location(loc, field_defs)
            if errs:
                error_listings.append({"row": idx + 1, "errors": errs})
            else:
                valid_locations.append(loc)

        # Assertions
        self.assertEqual(len(valid_locations), 1, "Only row #1 should pass validation")
        self.assertEqual(len(error_listings), 2, "Row #2 (bad zip) and Row #3 (missing zip) must route to error_listings")
        self.assertEqual(error_listings[0]["row"], 2)
        self.assertEqual(error_listings[1]["row"], 3)


if __name__ == "__main__":
    unittest.main()
