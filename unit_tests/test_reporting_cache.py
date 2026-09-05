from __future__ import annotations

import unittest
import inspect
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class ReportingCacheTests(unittest.TestCase):
    def test_reporting_returns_cached_payload_before_warehouse_setup(self) -> None:
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
        reporting_source = inspect.getsource(workflow_server.reporting_summary)
        gold_source = inspect.getsource(workflow_server.build_gold_layer)

        self.assertIn("reporting_summary:v3", reporting_source)
        self.assertIn("vw_reporting_filter_options", reporting_source)
        self.assertIn("FROM `{bronze_ref}.businesses`", gold_source)
        self.assertIn("UNION DISTINCT", gold_source)


if __name__ == "__main__":
    unittest.main()
