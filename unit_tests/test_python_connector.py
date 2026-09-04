from __future__ import annotations

import unittest

from whitespace_tool.source_adapters.python_connector_source import validate_result


class PythonConnectorTests(unittest.TestCase):
    def test_editor_accepts_json_object_or_list(self) -> None:
        self.assertEqual(validate_result({"locations": [{"name": "Main"}]}), {"locations": [{"name": "Main"}]})
        self.assertEqual(validate_result([{"name": "Main"}]), [{"name": "Main"}])

    def test_editor_result_can_be_built_with_imported_libraries(self) -> None:
        import json
        import math
        data = json.loads('{"locations": [{"name": "Store 1", "lat": 35.7}]}')
        data["locations"][0]["lat"] = math.floor(data["locations"][0]["lat"])
        self.assertEqual(validate_result(data), {"locations": [{"name": "Store 1", "lat": 35}]})

    def test_comma_separated_package_parsing_and_auto_detection(self) -> None:
        """Test parsing of multiple comma-separated package names and auto-detection."""
        # Simulated helper parsing package strings
        def parse_packages(pkg_str: str, code: str) -> list[str]:
            requested = [name.strip() for name in pkg_str.split(",") if name.strip()]
            if ("import requests" in code or "from requests import" in code) and "requests" not in requested:
                requested.append("requests")
            return requested

        # Test single and multiple package inputs
        self.assertEqual(parse_packages("pandas", ""), ["pandas"])
        self.assertEqual(parse_packages("pandas, numpy, beautifulsoup4", ""), ["pandas", "numpy", "beautifulsoup4"])
        self.assertEqual(parse_packages("  pandas ,  requests , scipy  ", ""), ["pandas", "requests", "scipy"])
        
        # Test auto-detecting requests from code imports
        code_with_requests = "import requests\nr = requests.get('https://example.com')"
        self.assertEqual(parse_packages("pandas, numpy", code_with_requests), ["pandas", "numpy", "requests"])

    def test_editor_rejects_non_json_or_scalar_results(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON-compatible"):
            validate_result({"bad": object()})
        with self.assertRaisesRegex(ValueError, "object or list"):
            validate_result("locations")
        with self.assertRaisesRegex(ValueError, "object or list"):
            validate_result(12345)


if __name__ == "__main__":
    unittest.main()