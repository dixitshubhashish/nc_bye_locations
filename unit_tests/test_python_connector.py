from __future__ import annotations

import unittest

from whitespace_tool.source_adapters.python_connector_source import validate_result


class PythonConnectorTests(unittest.TestCase):
    def test_editor_accepts_json_object_or_list(self) -> None:
        self.assertEqual(validate_result({"locations": [{"name": "Main"}]}), {"locations": [{"name": "Main"}]})
        self.assertEqual(validate_result([{"name": "Main"}]), [{"name": "Main"}])

    def test_editor_result_can_be_built_with_imported_libraries(self) -> None:
        import json
        self.assertEqual(validate_result(json.loads('{"ok": true}')), {"ok": True})

    def test_editor_rejects_non_json_or_scalar_results(self) -> None:
        with self.assertRaisesRegex(ValueError, "JSON-compatible"):
            validate_result({"bad": object()})
        with self.assertRaisesRegex(ValueError, "object or list"):
            validate_result("locations")


if __name__ == "__main__":
    unittest.main()