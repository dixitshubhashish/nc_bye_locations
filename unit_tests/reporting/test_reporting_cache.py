"""Unit tests for reporting summary caching behavior and SQL query generation rules.

Tests payload caching before warehouse setup, business registry integration, state population deduplication, and filter logic.
"""

from __future__ import annotations

import inspect
import re
import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class ReportingCacheTests(unittest.TestCase):
    """Test suite for reporting cache mechanisms and SQL generation patterns."""

    def test_reporting_returns_cached_payload_before_warehouse_setup(self) -> None:
        """Verify reporting_summary returns cached payload when hit without opening warehouse connection."""
        cached = {
            "source_table": "project.silver.listings_enriched",
            "totals": {"total_locations": 12},
            "top_states": [],
            "top_cities": [],
            "brands": [],
            "gaps": [],
            "map_records": [],
            "filter_options": {"brands": [], "states": [], "counties": [], "cities": [], "zips": []},
            "states_without_locations": [],
            "sample_records": [],
        }

        with patch.object(workflow_server, "get_cached_query", return_value=cached):
            with patch.object(workflow_server, "_refresh_silver_background", return_value=True) as refresh:
                with patch.object(workflow_server, "_medallion_settings", side_effect=AssertionError("warehouse should not be opened")):
                    result = workflow_server.reporting_summary({})

        self.assertEqual(result["reporting_cache"], "hit")
        self.assertTrue(result["refreshing"])
        refresh.assert_called_once()

    def test_reporting_brand_options_include_business_registry(self) -> None:
        """Verify reporting filter options incorporate active business names from bronze businesses table."""
        reporting_source = inspect.getsource(workflow_server.reporting_summary)
        gold_source = inspect.getsource(workflow_server.build_gold_layer)

        self.assertIn("reporting_summary:v3", reporting_source)
        self.assertIn("vw_reporting_filter_options", reporting_source)
        self.assertIn("FROM `{bronze_ref}.businesses`", gold_source)
        self.assertIn("UNION DISTINCT", gold_source)

    def test_state_population_is_deduped_before_summing(self) -> None:
        """Verify state population aggregation deduplicates population values by zip code."""
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("SELECT DISTINCT zip_code, state_code, population FROM {zip_ref}", source)
        self.assertIn("SELECT DISTINCT zip_code, state_code, state_name, city_name, population", source)
        self.assertNotRegex(source, r"SUM\(population\)\s*(AS \w+\s*)?\n\s*FROM \{zip_ref\}")

    def test_total_brands_falls_back_to_catalog_only_when_filtered_count_is_zero(self) -> None:
        """Verify total_brands count falls back to catalog brand count when filtered location count is zero."""
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("COALESCE(NULLIF(COUNT(DISTINCT brand), 0), (SELECT COUNT(DISTINCT brand_name) FROM {gold_brand_ref}))", source)

    def test_data_quality_respects_selected_brands_filter(self) -> None:
        """Verify data quality query applies selected_brands parameter filter."""
        source = inspect.getsource(workflow_server.reporting_summary)
        match = re.search(r'data_quality_query = f"""(.*?)"""', source, re.DOTALL)
        self.assertIsNotNone(match, "data_quality_query definition not found")
        data_quality_block = match.group(1)
        self.assertIn("listings_enriched", data_quality_block)
        self.assertIn("IN UNNEST(@selected_brands)", data_quality_block)


if __name__ == "__main__":
    unittest.main()
