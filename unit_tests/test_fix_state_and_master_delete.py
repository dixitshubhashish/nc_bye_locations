"""Real-behavior coverage for demo-critical workflow_server.py functions that
previously had only `inspect.getsource(...)` string-assertion tests (which
verify the source code mentions a symbol, not that the function actually
behaves correctly):

- fix_state_counts() / fix_state_counts_by_brand() - the Review Queue
  "Fixed by AI"/"Fixed manually"/etc. state cards and the Quality-by-Brand
  table. AGENT_SYNC.md documents a live 2026-09-10 investigation into these
  cards rendering "-" instead of real numbers, so the underlying aggregation
  logic is directly demo-relevant.
- master_delete_data() - the destructive "wipe everything" admin action;
  previously only had a source-string assertion (test_bigquery_bootstrap.py's
  test_master_delete_reuses_one_client_across_all_three_datasets), never
  actually exercised end to end.
- _dedupe_listings_against_bronze()'s two branches test_content_hash.py does
  not reach: the legacy-content-hash upgrade rewrite, and bumping
  last_observed_at forward on a duplicate.
- template_sample_records() - the template editor's "Source Preview" of real
  saved rows; previously only had inspect.getsource string assertions
  (test_mapping_layout_contract.py). Its custom_fields-expansion / typed-
  column-wins / matched_by (template vs business-fallback vs none) logic is
  real per-request business logic, not route boilerplate.

Follows the FakeClient/query-capture pattern already used in
test_silver_enrichment.py and test_content_hash.py rather than inventing a
new one.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import whitespace_tool.workflow_server as ws


class _FakeRow:
    """A row that supports BOTH row["field"] (dict-style, used by
    fix_state_counts_by_brand and _dedupe_listings_against_bronze) and
    getattr(row, "field") (used by fix_state_counts), matching how a real
    google.cloud.bigquery.table.Row supports both access styles."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getattr__(self, key):
        try:
            return self._data[key]
        except KeyError:
            raise AttributeError(key)

    def keys(self):
        return self._data.keys()


class _FakeQueryJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return list(self._rows)


class _FakeClient:
    def __init__(self, rows_by_call=None, raise_on=None):
        self.rows_by_call = list(rows_by_call or [])
        self.queries: list[str] = []
        self.raise_on = raise_on

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        if self.raise_on is not None:
            raise self.raise_on
        rows = self.rows_by_call.pop(0) if self.rows_by_call else []
        return _FakeQueryJob(rows)


class FixStateCountsTests(unittest.TestCase):
    """fix_state_counts(): cumulative, five-mutually-exclusive-state model."""

    def _run(self, row_data, business_id=""):
        client = _FakeClient(rows_by_call=[[_FakeRow(row_data)] if row_data is not None else []])
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "set_fix_state_counts") as set_counts:
            result = ws.fix_state_counts(business_id, client=client)
        return result, set_counts

    def test_states_reconcile_true_when_five_states_sum_to_total(self):
        row = {
            "ai_fixed": 10, "ai_suggested_fixed": 2, "manual_fixed": 5,
            "ai_suggested_pending": 1, "manual_pending": 2,
            "total_ever_invalid": 20,
        }
        result, set_counts = self._run(row)
        self.assertEqual(result["ai_fixed"], 10)
        self.assertEqual(result["total_ever_invalid"], 20)
        self.assertTrue(result["states_reconcile"])
        # The mirror write is a real side effect of a successful computation.
        set_counts.assert_called_once_with(result)

    def test_states_reconcile_false_when_state_model_has_drifted(self):
        # A deliberately inconsistent row: five states sum to 15, but
        # total_ever_invalid says 20 - this is the drift-detection this field
        # exists to catch, so it must come back False, not silently True.
        row = {
            "ai_fixed": 5, "ai_suggested_fixed": 0, "manual_fixed": 5,
            "ai_suggested_pending": 0, "manual_pending": 5,
            "total_ever_invalid": 20,
        }
        result, _ = self._run(row)
        self.assertFalse(result["states_reconcile"])

    def test_no_rows_returns_all_zero_counts_and_reconciles(self):
        result, _ = self._run(None)
        for key in ws.FIX_STATE_KEYS:
            self.assertEqual(result[key], 0)
        self.assertEqual(result["total_ever_invalid"], 0)
        self.assertTrue(result["states_reconcile"])

    def test_table_not_found_is_treated_as_zero_not_an_error(self):
        client = _FakeClient(raise_on=Exception("404 Not found: table error_listings"))
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "set_fix_state_counts"):
            result = ws.fix_state_counts("", client=client)
        self.assertEqual(result["total_ever_invalid"], 0)

    def test_non_404_query_error_propagates(self):
        client = _FakeClient(raise_on=RuntimeError("connection reset"))
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "set_fix_state_counts"):
            with self.assertRaises(RuntimeError):
                ws.fix_state_counts("", client=client)

    def test_mirror_write_failure_does_not_fail_the_call(self):
        # A SQLite mirror-write failure must not take down the cards
        # themselves - it's logged and swallowed, matching the
        # try/except LOGGER.warning shape in the source.
        row = {
            "ai_fixed": 1, "ai_suggested_fixed": 0, "manual_fixed": 0,
            "ai_suggested_pending": 0, "manual_pending": 0,
            "total_ever_invalid": 1,
        }
        client = _FakeClient(rows_by_call=[[_FakeRow(row)]])
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "set_fix_state_counts", side_effect=RuntimeError("disk full")):
            result = ws.fix_state_counts("", client=client)
        self.assertEqual(result["ai_fixed"], 1)


class FixStateCountsByBrandTests(unittest.TestCase):
    """fix_state_counts_by_brand(): same five-state model, grouped by brand -
    exists specifically so the Quality-by-Brand table and the headline cards
    answer the same question (see the function's own docstring)."""

    def test_groups_counts_by_brand_and_casts_to_int(self):
        rows = [
            _FakeRow({
                "brand": "Domino's", "ai_fixed": 3, "ai_suggested_fixed": 1,
                "manual_fixed": 2, "ai_suggested_pending": 0, "manual_pending": 4,
                "total_ever_invalid": 10,
            }),
            _FakeRow({
                "brand": "Pizza Hut", "ai_fixed": 0, "ai_suggested_fixed": 0,
                "manual_fixed": 1, "ai_suggested_pending": 0, "manual_pending": 0,
                "total_ever_invalid": 1,
            }),
        ]
        client = _FakeClient(rows_by_call=[rows])
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"):
            result = ws.fix_state_counts_by_brand(client=client)
        self.assertEqual(set(result.keys()), {"Domino's", "Pizza Hut"})
        self.assertEqual(result["Domino's"]["ai_fixed"], 3)
        self.assertIsInstance(result["Domino's"]["ai_fixed"], int)
        self.assertEqual(result["Pizza Hut"]["total_ever_invalid"], 1)

    def test_table_not_found_returns_empty_dict(self):
        client = _FakeClient(raise_on=Exception("404 Not found: error_listings"))
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"):
            result = ws.fix_state_counts_by_brand(client=client)
        self.assertEqual(result, {})

    def test_no_rows_returns_empty_dict(self):
        client = _FakeClient(rows_by_call=[[]])
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"):
            result = ws.fix_state_counts_by_brand(client=client)
        self.assertEqual(result, {})


def _fake_drop_result(dropped_tables):
    # drop_dataset_tables() returns a dict (result["dropped_tables"] is
    # subscripted in master_delete_data), not an object.
    return {"dropped_tables": dropped_tables}


class MasterDeleteDataTests(unittest.TestCase):
    """master_delete_data(): the destructive full-wipe admin action.
    Previously only asserted (via inspect.getsource) that the source text
    mentions reusing one client - never actually run."""

    def setUp(self):
        # authenticate() reads WORKFLOW_LOGIN_USER/PASSWORD from the
        # environment; pin both so this test doesn't depend on the local
        # .env and doesn't accidentally accept/reject based on it.
        self._env_patch = patch.dict(
            "os.environ",
            {"WORKFLOW_LOGIN_USER": "admin", "WORKFLOW_LOGIN_PASSWORD": "secret"},
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def test_wrong_confirmation_text_raises_without_touching_bigquery(self):
        with patch.object(ws, "_bigquery_client") as client_factory:
            with self.assertRaisesRegex(ValueError, "DELETE ALL DATA"):
                ws.master_delete_data({
                    "username": "admin", "password": "secret",
                    "confirmation": "delete everything please",
                })
        client_factory.assert_not_called()

    def test_bad_credentials_raise_before_any_deletion(self):
        with patch.object(ws, "_bigquery_client") as client_factory:
            with self.assertRaises(ValueError):
                ws.master_delete_data({
                    "username": "admin", "password": "wrong",
                    "confirmation": "DELETE ALL DATA",
                })
        client_factory.assert_not_called()

    def test_successful_wipe_drops_all_three_datasets_with_one_shared_client(self):
        client = object()
        drop_calls = []

        def fake_drop(project_id, dataset_id, credentials_json, *, client=None):
            drop_calls.append((dataset_id, client))
            return _fake_drop_result([f"{dataset_id}_table1", f"{dataset_id}_table2"])

        with patch.object(ws, "_medallion_settings",
                           return_value=("proj", "bronze", "silver", "gold", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "drop_dataset_tables", side_effect=fake_drop), \
             patch.object(ws, "_forget_ensured_tables") as forget, \
             patch.object(ws, "invalidate_cache") as invalidate, \
             patch.object(ws, "invalidate_brand_cache") as invalidate_brand, \
             patch.object(ws, "invalidate_quality_cache") as invalidate_quality, \
             patch.object(ws, "clear_local_cache_db") as clear_local, \
             patch.object(ws, "set_error_count") as set_error, \
             patch.object(ws, "set_auto_repair_stats") as set_stats:
            result = ws.master_delete_data({
                "username": "admin", "password": "secret",
                "confirmation": "DELETE ALL DATA",
            })

        # All three medallion datasets were dropped, using the SAME client
        # instance (the whole point of the fix this function's comment
        # describes - one client, not one per dataset).
        self.assertEqual([d for d, _ in drop_calls], ["bronze", "silver", "gold"])
        self.assertTrue(all(c is client for _, c in drop_calls))
        self.assertEqual(result["dropped_count"], 6)
        self.assertIn("bronze.bronze_table1", result["dropped_tables"])
        self.assertIn("gold.gold_table2", result["dropped_tables"])
        self.assertEqual(len(result["datasets"]), 3)

        # Every cache/counter reset the function promises actually ran.
        forget.assert_called_once()
        invalidate.assert_called_once()
        invalidate_brand.assert_called_once()
        invalidate_quality.assert_called_once()
        clear_local.assert_called_once()
        set_error.assert_called_once_with("", 0)
        set_stats.assert_called_once_with(0, 0, 0, 0)

    def test_zip_reference_cache_is_cleared_after_a_successful_wipe(self):
        ws.ZIP_REFERENCE_CACHE[("proj", "bronze")] = {"stale": True}
        try:
            with patch.object(ws, "_medallion_settings",
                               return_value=("proj", "bronze", "silver", "gold", None)), \
                 patch.object(ws, "_bigquery_client", return_value=object()), \
                 patch.object(ws, "drop_dataset_tables", return_value=_fake_drop_result([])), \
                 patch.object(ws, "_forget_ensured_tables"), \
                 patch.object(ws, "invalidate_cache"), \
                 patch.object(ws, "invalidate_brand_cache"), \
                 patch.object(ws, "invalidate_quality_cache"), \
                 patch.object(ws, "clear_local_cache_db"), \
                 patch.object(ws, "set_error_count"), \
                 patch.object(ws, "set_auto_repair_stats"):
                ws.master_delete_data({
                    "username": "admin", "password": "secret",
                    "confirmation": "DELETE ALL DATA",
                })
            self.assertEqual(ws.ZIP_REFERENCE_CACHE, {})
        finally:
            ws.ZIP_REFERENCE_CACHE.clear()


class DedupeListingsAgainstBronzeExtraBranchesTests(unittest.TestCase):
    """Branches of _dedupe_listings_against_bronze() not reached by
    test_content_hash.py: the legacy-hash upgrade rewrite and bumping
    last_observed_at forward on a re-observed duplicate."""

    def test_legacy_hash_match_triggers_a_content_hash_rewrite(self):
        from whitespace_tool.warehouse_bigquery import legacy_content_hash

        new_row = {
            "business_id": "biz-1", "content_hash": "new-hash-abc",
            "last_observed_at": None, "name": "Store 1", "address": "123 Main St",
        }
        legacy_hash = legacy_content_hash(new_row)
        existing_row = _FakeRow({
            "listing_id": "listing-1", "business_id": "biz-1",
            "content_hash": legacy_hash, "last_observed_at": None,
        })

        update_queries = []

        class Client:
            def query(self, sql, job_config=None):
                if sql.strip().startswith("SELECT"):
                    return _FakeQueryJob([existing_row])
                update_queries.append(sql)
                return _FakeQueryJob([])

        rows, duplicate_count = ws._dedupe_listings_against_bronze(
            Client(), "proj", "ds", [new_row]
        )
        # The old-hash row is recognized as the same listing: it must be
        # skipped from re-insertion (duplicate) and its content_hash rewritten
        # in place, not left stuck on the legacy definition forever.
        self.assertEqual(rows, [])
        self.assertEqual(duplicate_count, 1)
        self.assertTrue(any("UPDATE" in q and "content_hash" in q for q in update_queries))

    def test_duplicate_with_newer_last_observed_at_bumps_the_stored_row(self):
        new_row = {
            "business_id": "biz-1", "content_hash": "hash-x",
            "last_observed_at": "2026-09-10T12:00:00",
        }
        existing_row = _FakeRow({
            "listing_id": "listing-1", "business_id": "biz-1",
            "content_hash": "hash-x", "last_observed_at": "2026-01-01T00:00:00",
        })

        update_queries = []

        class Client:
            def query(self, sql, job_config=None):
                if sql.strip().startswith("SELECT"):
                    return _FakeQueryJob([existing_row])
                update_queries.append(sql)
                return _FakeQueryJob([])

        rows, duplicate_count = ws._dedupe_listings_against_bronze(
            Client(), "proj", "ds", [new_row]
        )
        self.assertEqual(rows, [])
        self.assertEqual(duplicate_count, 1)
        self.assertTrue(any("last_observed_at" in q for q in update_queries))

    def test_duplicate_with_older_last_observed_at_does_not_issue_an_update(self):
        new_row = {
            "business_id": "biz-1", "content_hash": "hash-x",
            "last_observed_at": "2020-01-01T00:00:00",
        }
        existing_row = _FakeRow({
            "listing_id": "listing-1", "business_id": "biz-1",
            "content_hash": "hash-x", "last_observed_at": "2026-01-01T00:00:00",
        })

        class Client:
            def __init__(self):
                self.update_called = False

            def query(self, sql, job_config=None):
                if sql.strip().startswith("SELECT"):
                    return _FakeQueryJob([existing_row])
                self.update_called = True
                return _FakeQueryJob([])

        client = Client()
        rows, duplicate_count = ws._dedupe_listings_against_bronze(
            client, "proj", "ds", [new_row]
        )
        self.assertEqual(rows, [])
        self.assertEqual(duplicate_count, 1)
        self.assertFalse(client.update_called)


class TemplateSampleRecordsTests(unittest.TestCase):
    """template_sample_records(): real saved-row preview for the template
    editor, including its custom_fields expansion and match-source labeling."""

    def _run(self, params, rows):
        client = _FakeClient(rows_by_call=[rows])
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_listings_table"):
            return ws.template_sample_records(params)

    def test_missing_template_id_raises(self):
        with self.assertRaisesRegex(ValueError, "template_id is required"):
            ws.template_sample_records({"business_id": ["biz-1"]})

    def test_custom_fields_are_expanded_but_a_typed_column_always_wins(self):
        row = {
            "listing_id": "l1", "name": "Store 1", "address": "1 Main St",
            "city_name": "Austin", "state_code": "TX", "zip_code": "78701",
            "country": "US", "latitude": 30.1, "longitude": -97.7,
            "phone_number": "", "website_url": "", "last_observed_at": None,
            # "name" duplicated as an extra should NOT override the typed
            # column; "loyalty_tier" is genuinely unmapped and should surface.
            "custom_fields": '{"name": "raw-unnormalized-name", "loyalty_tier": "gold"}',
            "match_rank": 0,
        }
        result = self._run({"template_id": ["tmpl-1"]}, [row])
        self.assertEqual(result["records"][0]["name"], "Store 1")
        self.assertEqual(result["records"][0]["loyalty_tier"], "gold")
        self.assertEqual(result["unmapped_columns"], ["loyalty_tier"])
        self.assertNotIn("custom_fields", result["records"][0])
        self.assertNotIn("match_rank", result["records"][0])

    def test_matched_by_template_when_an_exact_match_rank_zero_row_exists(self):
        row = {"listing_id": "l1", "custom_fields": None, "match_rank": 0}
        result = self._run({"template_id": ["tmpl-1"]}, [row])
        self.assertEqual(result["matched_by"], "template")

    def test_matched_by_business_when_only_fallback_rows_exist(self):
        row = {"listing_id": "l1", "custom_fields": None, "match_rank": 1}
        result = self._run({"template_id": ["tmpl-1"], "business_id": ["biz-1"]}, [row])
        self.assertEqual(result["matched_by"], "business")

    def test_matched_by_none_when_no_rows_at_all(self):
        result = self._run({"template_id": ["tmpl-1"]}, [])
        self.assertEqual(result["matched_by"], "none")
        self.assertEqual(result["records"], [])

    def test_malformed_custom_fields_json_is_ignored_not_fatal(self):
        row = {"listing_id": "l1", "custom_fields": "{not valid json", "match_rank": 0}
        result = self._run({"template_id": ["tmpl-1"]}, [row])
        self.assertEqual(result["records"][0]["listing_id"], "l1")
        self.assertEqual(result["unmapped_columns"], [])

    def test_limit_out_of_range_clamps_between_one_and_fifty(self):
        captured = {}

        class Client:
            def query(self, sql, job_config=None):
                captured["sql"] = sql
                return _FakeQueryJob([])

        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=Client()), \
             patch.object(ws, "_ensure_listings_table"):
            ws.template_sample_records({"template_id": ["tmpl-1"], "limit": ["9999"]})
        self.assertIn("LIMIT 50", captured["sql"])

    def test_non_numeric_limit_falls_back_to_ten(self):
        captured = {}

        class Client:
            def query(self, sql, job_config=None):
                captured["sql"] = sql
                return _FakeQueryJob([])

        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=Client()), \
             patch.object(ws, "_ensure_listings_table"):
            ws.template_sample_records({"template_id": ["tmpl-1"], "limit": ["not-a-number"]})
        self.assertIn("LIMIT 10", captured["sql"])

    def test_missing_listings_table_returns_empty_with_warning_not_an_error(self):
        client = _FakeClient(raise_on=Exception("404 Not found: listings"))
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_listings_table"):
            result = ws.template_sample_records({"template_id": ["tmpl-1"]})
        self.assertEqual(result["records"], [])
        self.assertIn("warning", result)


if __name__ == "__main__":
    unittest.main()
