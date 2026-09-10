"""Real-behavior tests for the GET JSON API connector.

api_get_source.preview_url() builds a urllib.request.Request (URL + query
params + auth/custom headers) and delegates the response body to
json_source.preview(). Real network access is never exercised here -
urllib.request.urlopen is mocked with a fake response object - but the
request construction (URL, headers, auth encoding) and the JSON handoff are
exercised for real.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from whitespace_tool.source_adapters import api_get_source


class FakeHeaders:
    """Mimics http.client.HTTPMessage's case-insensitive .get()."""

    def __init__(self, headers: dict) -> None:
        self._headers = {key.lower(): value for key, value in headers.items()}

    def get(self, key: str, default=None):
        return self._headers.get(key.lower(), default)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = FakeHeaders({"content-type": content_type})

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class PreviewUrlSuccessTests(unittest.TestCase):
    def test_successful_json_response_is_parsed_into_preview_payload(self) -> None:
        payload = json.dumps([{"name": "Store A", "city": "Austin"}, {"name": "Store B", "city": "Dallas"}]).encode()

        with patch.object(api_get_source.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            result = api_get_source.preview_url("https://example.com/stores")

        self.assertEqual(result["fields"], ["city", "name"])
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["rows"], [{"name": "Store A", "city": "Austin"}, {"name": "Store B", "city": "Dallas"}])

    def test_record_path_is_passed_through_to_json_preview(self) -> None:
        payload = json.dumps({"data": {"stores": [{"name": "Store A"}]}}).encode()

        with patch.object(api_get_source.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            result = api_get_source.preview_url("https://example.com/stores", record_path="data.stores")

        self.assertEqual(result["record_path"], "data.stores")
        self.assertEqual(result["rows"], [{"name": "Store A"}])

    def test_fields_only_is_forwarded_to_json_preview(self) -> None:
        rows = [{"name": f"Store {i}"} for i in range(5)]
        payload = json.dumps(rows).encode()

        with patch.object(api_get_source.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            result = api_get_source.preview_url("https://example.com/stores", fields_only=True)

        self.assertEqual(result["record_count"], 5)
        self.assertEqual(len(result["rows"]), 5)

    def test_content_type_check_is_case_insensitive_and_ignores_charset_suffix(self) -> None:
        payload = json.dumps([{"name": "Store A"}]).encode()
        with patch.object(
            api_get_source.urllib.request,
            "urlopen",
            return_value=FakeResponse(payload, content_type="Application/JSON; charset=utf-8"),
        ):
            result = api_get_source.preview_url("https://example.com/stores")
        self.assertEqual(result["rows"], [{"name": "Store A"}])


class PreviewUrlContentTypeErrorTests(unittest.TestCase):
    def test_non_json_content_type_raises_value_error_naming_the_content_type(self) -> None:
        with patch.object(api_get_source.urllib.request, "urlopen", return_value=FakeResponse(b"<html></html>", content_type="text/html")):
            with self.assertRaisesRegex(ValueError, r"GET API response must be JSON.*text/html"):
                api_get_source.preview_url("https://example.com/stores")

    def test_missing_content_type_header_also_raises(self) -> None:
        with patch.object(api_get_source.urllib.request, "urlopen", return_value=FakeResponse(b"{}", content_type="")):
            with self.assertRaises(ValueError):
                api_get_source.preview_url("https://example.com/stores")


class RequestConstructionTests(unittest.TestCase):
    """Capture the Request object urlopen would receive to assert on it."""

    def _capture_request(self, **kwargs) -> "unittest.mock.Mock":
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(b"[]")

        with patch.object(api_get_source.urllib.request, "urlopen", side_effect=fake_urlopen):
            api_get_source.preview_url(**kwargs)
        return captured["request"]

    def test_default_headers_include_accept_json(self) -> None:
        request = self._capture_request(url="https://example.com/stores")
        self.assertEqual(request.get_header("Accept"), "application/json")

    def test_custom_headers_override_default_accept_header(self) -> None:
        request = self._capture_request(url="https://example.com/stores", headers={"Accept": "application/vnd.custom+json"})
        self.assertEqual(request.get_header("Accept"), "application/vnd.custom+json")

    def test_custom_headers_are_added_alongside_defaults(self) -> None:
        request = self._capture_request(url="https://example.com/stores", headers={"X-Client": "whitespace-tool"})
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("X-client"), "whitespace-tool")

    def test_request_timeout_is_300_seconds(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["timeout"] = timeout
            return FakeResponse(b"[]")

        with patch.object(api_get_source.urllib.request, "urlopen", side_effect=fake_urlopen):
            api_get_source.preview_url("https://example.com/stores")
        self.assertEqual(captured["timeout"], 300)

    def test_query_params_merge_with_existing_url_query_string(self) -> None:
        request = self._capture_request(
            url="https://example.com/stores?existing=keep&page=1",
            query_params=[{"key": "page", "value": "2"}, {"key": "limit", "value": "50"}],
        )
        from urllib.parse import urlsplit, parse_qs

        query = parse_qs(urlsplit(request.full_url).query)
        # "existing" survives untouched, "page" is overridden by the new
        # query_params value, and the new "limit" key is added.
        self.assertEqual(query["existing"], ["keep"])
        self.assertEqual(query["page"], ["2"])
        self.assertEqual(query["limit"], ["50"])

    def test_query_params_are_appended_when_url_has_no_existing_query_string(self) -> None:
        request = self._capture_request(
            url="https://example.com/stores",
            query_params=[{"key": "format", "value": "json"}],
        )
        self.assertIn("format=json", request.full_url)

    def test_empty_query_params_leave_url_unchanged(self) -> None:
        request = self._capture_request(url="https://example.com/stores?a=1", query_params=[])
        self.assertEqual(request.full_url, "https://example.com/stores?a=1")

    def test_query_params_with_blank_key_are_dropped(self) -> None:
        request = self._capture_request(
            url="https://example.com/stores",
            query_params=[{"key": "  ", "value": "ignored"}, {"key": "real", "value": "kept"}],
        )
        self.assertNotIn("ignored", request.full_url)
        self.assertIn("real=kept", request.full_url)

    def test_query_params_keys_and_values_are_stripped_of_whitespace(self) -> None:
        request = self._capture_request(
            url="https://example.com/stores",
            query_params=[{"key": "  page  ", "value": "  2  "}],
        )
        from urllib.parse import urlsplit, parse_qs

        query = parse_qs(urlsplit(request.full_url).query)
        self.assertEqual(query["page"], ["2"])


class AuthHeaderTests(unittest.TestCase):
    def _headers_for(self, auth) -> dict:
        return api_get_source._auth_headers(auth)

    def test_no_auth_produces_no_extra_headers(self) -> None:
        self.assertEqual(self._headers_for(None), {})
        self.assertEqual(self._headers_for({}), {})
        self.assertEqual(self._headers_for({"type": "none"}), {})

    def test_bearer_auth_sets_authorization_header(self) -> None:
        headers = self._headers_for({"type": "bearer", "token": "abc123"})
        self.assertEqual(headers, {"Authorization": "Bearer abc123"})

    def test_bearer_auth_with_blank_token_produces_no_header(self) -> None:
        self.assertEqual(self._headers_for({"type": "bearer", "token": "   "}), {})
        self.assertEqual(self._headers_for({"type": "bearer"}), {})

    def test_basic_auth_base64_encodes_username_and_password(self) -> None:
        import base64

        headers = self._headers_for({"type": "basic", "username": "user", "password": "pass"})
        expected = "Basic " + base64.b64encode(b"user:pass").decode("ascii")
        self.assertEqual(headers, {"Authorization": expected})

    def test_basic_auth_with_empty_credentials_still_sends_a_header(self) -> None:
        # Unlike bearer/api_key_header, basic auth always emits an
        # Authorization header (base64 of ":") - there's no blank-value guard
        # in _auth_headers for the basic branch.
        import base64

        headers = self._headers_for({"type": "basic"})
        expected = "Basic " + base64.b64encode(b":").decode("ascii")
        self.assertEqual(headers, {"Authorization": expected})

    def test_api_key_header_auth_uses_custom_header_name(self) -> None:
        headers = self._headers_for({"type": "api_key_header", "key_name": "X-API-Key", "key_value": "secret"})
        self.assertEqual(headers, {"X-API-Key": "secret"})

    def test_api_key_header_auth_with_missing_name_or_value_produces_no_header(self) -> None:
        self.assertEqual(self._headers_for({"type": "api_key_header", "key_name": "", "key_value": "secret"}), {})
        self.assertEqual(self._headers_for({"type": "api_key_header", "key_name": "X-API-Key", "key_value": ""}), {})

    def test_unknown_auth_type_produces_no_headers(self) -> None:
        self.assertEqual(self._headers_for({"type": "oauth2"}), {})

    def test_auth_headers_are_applied_on_the_actual_request(self) -> None:
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            return FakeResponse(b"[]")

        with patch.object(api_get_source.urllib.request, "urlopen", side_effect=fake_urlopen):
            api_get_source.preview_url(
                "https://example.com/stores",
                auth={"type": "bearer", "token": "xyz"},
            )
        self.assertEqual(captured["request"].get_header("Authorization"), "Bearer xyz")

    def test_auth_headers_can_be_overridden_by_explicit_headers_argument_order(self) -> None:
        # preview_url applies headers first, then auth headers on top - so
        # an explicit "Authorization" header is overwritten by computed auth
        # headers when both are supplied. Document that precedence for real
        # rather than assuming it.
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["request"] = request
            return FakeResponse(b"[]")

        with patch.object(api_get_source.urllib.request, "urlopen", side_effect=fake_urlopen):
            api_get_source.preview_url(
                "https://example.com/stores",
                headers={"Authorization": "Bearer manual-token"},
                auth={"type": "bearer", "token": "computed-token"},
            )
        self.assertEqual(captured["request"].get_header("Authorization"), "Bearer computed-token")


class CleanPairsTests(unittest.TestCase):
    def test_clean_pairs_strips_whitespace_and_drops_blank_keys(self) -> None:
        self.assertEqual(
            api_get_source._clean_pairs([{"key": " a ", "value": " 1 "}, {"key": "  ", "value": "ignored"}]),
            {"a": "1"},
        )

    def test_clean_pairs_handles_none_and_empty_list(self) -> None:
        self.assertEqual(api_get_source._clean_pairs(None), {})
        self.assertEqual(api_get_source._clean_pairs([]), {})

    def test_clean_pairs_later_duplicate_key_wins(self) -> None:
        self.assertEqual(
            api_get_source._clean_pairs([{"key": "a", "value": "first"}, {"key": "a", "value": "second"}]),
            {"a": "second"},
        )


if __name__ == "__main__":
    unittest.main()
