from __future__ import annotations

import unittest

from whitespace_tool.source_adapters.python_connector_source import _validate_public_https_url, parse_request


class PythonConnectorTests(unittest.TestCase):
    def test_connector_accepts_single_https_json_get(self) -> None:
        url, params, headers, timeout = parse_request(
            'def fetch():\n    return http.get("https://api.example.com/locations", params={"limit": "100"}).json()\n'
        )
        self.assertEqual(url, "https://api.example.com/locations")
        self.assertEqual(params, {"limit": "100"})
        self.assertEqual(headers, {})
        self.assertEqual(timeout, 15.0)

    def test_connector_rejects_imports_and_file_access(self) -> None:
        with self.assertRaisesRegex(ValueError, "only def fetch"):
            parse_request('import os\ndef fetch():\n    return http.get("https://api.example.com").json()\n')
        with self.assertRaisesRegex(ValueError, "http.get"):
            parse_request('def fetch():\n    return open("secret.txt")\n')

    def test_connector_rejects_authenticated_headers(self) -> None:
        with self.assertRaisesRegex(ValueError, "authenticated"):
            parse_request(
                'def fetch():\n    return http.get("https://api.example.com", headers={"Authorization": "secret"}).json()\n'
            )

    def test_connector_rejects_local_or_non_https_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            _validate_public_https_url("http://example.com")
        with self.assertRaisesRegex(ValueError, "private"):
            _validate_public_https_url("https://127.0.0.1/locations")


if __name__ == "__main__":
    unittest.main()