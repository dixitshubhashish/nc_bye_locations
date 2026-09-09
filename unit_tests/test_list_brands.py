from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import whitespace_tool.sqlite_cache as sqlite_cache
import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_args, **_kwargs):
        return _FakeJob(self._rows)


class ListBrandsSerializationTests(unittest.TestCase):
    """list_brands reads BigQuery businesses whose created_at/updated_at come
    back as datetime objects. The result is both cached (json.dumps) and sent
    as an HTTP JSON body, so any datetime that survives raises "Object of type
    datetime is not JSON serializable". This is the real-world path the mocked
    suite previously skipped."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_patch = patch.object(sqlite_cache, "DB_PATH", Path(self._tmpdir) / "test.db")
        self._db_patch.start()
        # Inject a minimal fake google.cloud.bigquery so the in-function
        # `from google.cloud import bigquery` resolves without the real SDK.
        fake_bigquery = types.SimpleNamespace(
            QueryJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
            ScalarQueryParameter=lambda *a, **k: ("param", a, k),
        )
        fake_cloud = types.ModuleType("google.cloud")
        fake_cloud.bigquery = fake_bigquery
        self._mods = patch.dict(sys.modules, {
            "google": types.ModuleType("google"),
            "google.cloud": fake_cloud,
            "google.cloud.bigquery": fake_bigquery,
        })
        self._mods.start()

    def tearDown(self) -> None:
        self._mods.stop()
        self._db_patch.stop()

    def _run_list_brands(self, rows):
        with patch.object(workflow_server, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(workflow_server, "_bigquery_client", return_value=_FakeClient(rows)), \
             patch.object(workflow_server, "_ensure_businesses_table", lambda *a, **k: None), \
             patch.object(workflow_server, "_ensure_source_types_table", lambda *a, **k: None), \
             patch.object(workflow_server, "_ensure_workflow_templates_table", lambda *a, **k: None):
            return workflow_server.list_brands("")

    def test_datetime_columns_are_serialized_not_raw_datetimes(self) -> None:
        rows = [{
            "business_id": "b1",
            "name": "Acme Pizza",
            "created_at": datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            "updated_at": datetime(2025, 6, 7, 8, 9, 10, tzinfo=timezone.utc),
            "status": "active",
        }]
        result = self._run_list_brands(rows)
        brand = result["brands"][0]
        # The headline assertion: no raw datetime survives, so the whole
        # payload is JSON-serializable (this is what actually broke on load).
        json.dumps(result)  # must not raise
        self.assertIsInstance(brand["created_at"], str)
        self.assertIsInstance(brand["updated_at"], str)
        self.assertEqual(brand["created_at"], "2025-01-02T03:04:05+00:00")

    def test_result_is_cached_as_valid_json(self) -> None:
        rows = [{
            "business_id": "b2",
            "name": "Rival Co",
            "created_at": datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            "updated_at": None,
        }]
        self._run_list_brands(rows)
        # If a datetime had leaked, set_cached_query's json.dumps would have
        # raised inside list_brands; a readable cache entry proves it didn't.
        cached = sqlite_cache.get_cached_query("list_brands:")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["brands"][0]["business_id"], "b2")


if __name__ == "__main__":
    unittest.main()
