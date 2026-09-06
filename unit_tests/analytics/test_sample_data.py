"""Unit tests for synthetic sample brand dataset generation and environment loader flags.

Tests sample brand configuration parameters, generated row attributes, metadata linkage, and environment flags.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from whitespace_tool.analytics.sample_data import (
    SAMPLE_BATCH_ID,
    SAMPLE_BRANDS,
    generate_source_rows,
    mapper_for,
    source_configuration,
    stable_business_id,
    stable_template_id,
)
from whitespace_tool.source_adapters.common import collect_fields
from whitespace_tool.workflow_server import _sample_loader_enabled


class SampleDataTests(unittest.TestCase):
    """Test suite for validating synthetic sample dataset generation logic."""

    def test_sample_config_covers_supported_sources_and_realistic_volume(self) -> None:
        """Verify sample brand configurations cover all source types with realistic row volumes."""
        source_types = {brand.source_type for brand in SAMPLE_BRANDS}
        total_rows = sum(brand.row_count for brand in SAMPLE_BRANDS)

        self.assertEqual({"csv", "json", "excel", "api_get_json", "python_editor", "xml"}, source_types)
        self.assertGreaterEqual(len(SAMPLE_BRANDS), 10)
        self.assertLessEqual(len(SAMPLE_BRANDS), 15)
        self.assertGreaterEqual(total_rows, 8000)
        self.assertLessEqual(total_rows, 10000)
        for brand in SAMPLE_BRANDS:
            self.assertGreaterEqual(brand.row_count, 500)
            self.assertLessEqual(brand.row_count, 1000)
        self.assertGreater(len({brand.row_count for brand in SAMPLE_BRANDS}), 5)

    def test_sample_brands_never_use_the_real_assessment_brand_names(self) -> None:
        """Verify sample dataset brand names are distinct from production assessment brand names."""
        real_brand_names = {"Domino's", "Pizza Hut", "Little Caesars"}
        business_names = {brand.business_name for brand in SAMPLE_BRANDS}
        self.assertTrue(real_brand_names.isdisjoint(business_names))

    def test_generated_rows_are_linked_to_business_template_and_batch(self) -> None:
        """Verify generated sample rows attach proper template_id, business_id, and batch_id metadata."""
        brand = SAMPLE_BRANDS[1]
        source_type_id = "source-json"
        business_id = stable_business_id(brand.key)
        mapper = mapper_for(brand, business_id, source_type_id)
        rows = generate_source_rows(brand, source_type_id, SAMPLE_BATCH_ID)
        fields = collect_fields(rows)

        self.assertEqual(len(rows), brand.row_count)
        self.assertEqual(mapper["business_id"], business_id)
        self.assertEqual(mapper["source_type_id"], source_type_id)
        self.assertEqual(source_configuration(brand)["source_type"], brand.source_type)
        self.assertIn(stable_template_id(brand.key), rows[0]["__meta"]["template_id"])
        self.assertEqual(rows[0]["__meta"]["sample_batch_id"], SAMPLE_BATCH_ID)
        for required_path in mapper["fields"].values():
            self.assertIn(required_path, fields)

    def test_sample_loader_is_disabled_by_default_in_production(self) -> None:
        """Verify sample data loader is disabled by default in production unless explicitly enabled."""
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            self.assertFalse(_sample_loader_enabled())
        with patch.dict("os.environ", {"APP_ENV": "production", "ENABLE_SAMPLE_DATA_LOADER": "true"}, clear=True):
            self.assertTrue(_sample_loader_enabled())


if __name__ == "__main__":
    unittest.main()
