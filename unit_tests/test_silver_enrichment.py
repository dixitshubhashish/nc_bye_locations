from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _FakeJob:
    def result(self) -> None:
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.created_datasets: list[str] = []

    def create_dataset(self, dataset: object, exists_ok: bool = False) -> None:
        self.created_datasets.append(str(getattr(dataset, "dataset_ref", dataset)))

    def query(self, query: str) -> _FakeJob:
        self.queries.append(query)
        return _FakeJob()

    def get_table(self, table_ref: str) -> SimpleNamespace:
        return SimpleNamespace(num_rows=42)


class SilverEnrichmentTests(unittest.TestCase):
    def test_build_silver_layer_creates_enriched_table_and_views(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    result = workflow_server.build_silver_layer()

        sql = "\n".join(client.queries)
        self.assertEqual(result["rows"], 42)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.listings_enriched`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.silver.vw_brand_location_top10`", sql)
        self.assertIn("CREATE OR REPLACE VIEW `project.silver.vw_brand_zip_income`", sql)
        self.assertIn("REGEXP_EXTRACT(CAST(zip_code AS STRING)", sql)
        self.assertIn("United States", sql)
        self.assertIn("median_household_income", sql)
        self.assertIn("z.income_per_capita", sql)
        self.assertIn("city_geos AS", sql)
        self.assertIn("ANY_VALUE(state_code) AS state_code", sql)
        self.assertIn("COALESCE(l.normalized_state_code, cg.state_code, z.state_code) AS state_code", sql)
        self.assertIn("COALESCE(l.latitude, z.latitude, cg.latitude) AS latitude", sql)
        self.assertIn("EDIT_DISTANCE(l.normalized_city_name, cg.normalized_city_name) <= 2", sql)
        self.assertIn("coordinate_source", sql)
        self.assertIn("coordinate_confidence", sql)
        self.assertIn("geocode_query", sql)
        self.assertIn("state_code", sql)
        self.assertIn("state_name", sql)

    def test_build_silver_layer_creates_zip_reference_and_invalid_split(self) -> None:
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_silver_layer()

        sql = "\n".join(client.queries)
        # A separate, refined zip/income reference table, sourced from
        # bronze (not re-derived by every downstream consumer).
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.zip_reference`", sql)
        self.assertIn("FROM `project.bronze.us_zipcodes`", sql)
        # listings_enriched and listings_invalid are both derived from one
        # staging table, split by the same mandatory-fields check, so a row
        # can't silently vanish or silently keep null coordinates.
        self.assertIn("CREATE OR REPLACE TABLE `project.silver._listings_staging`", sql)
        self.assertIn("CREATE OR REPLACE TABLE `project.silver.listings_invalid`", sql)
        self.assertIn("rejection_reason", sql)
        self.assertIn("latitude IS NOT NULL AND longitude IS NOT NULL", sql)
        self.assertIn("DROP TABLE IF EXISTS `project.silver._listings_staging`", sql)

    def test_build_silver_layer_never_drops_enriched_or_invalid_before_recreating(self) -> None:
        # Regression test for a real incident (2026-09-10): build_silver_layer()
        # used to run `DROP TABLE IF EXISTS` on listings_enriched and
        # listings_invalid at the very START of the build, then only recreate
        # them via `CREATE OR REPLACE TABLE` much later. Any interruption in
        # that window (server restart, killed process) left the tables
        # genuinely not existing, with nothing logged - this silently zeroed
        # out the Needs Review feature and Review Queue counts at least twice
        # before being traced. The fix removed the premature DROPs entirely,
        # since CREATE OR REPLACE TABLE is already atomic in BigQuery. These
        # two tables must only ever be replaced atomically, never
        # dropped-then-recreated-later, so a DROP TABLE targeting either one
        # must never appear anywhere in the generated SQL for a single call.
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_silver_layer()

        for table in ("listings_enriched", "listings_invalid"):
            full_name = f"project.silver.{table}"
            drop_statements = [
                q for q in client.queries
                if "DROP TABLE" in q.upper() and full_name in q
            ]
            self.assertEqual(
                drop_statements, [],
                f"build_silver_layer() must never DROP `{full_name}` - "
                "it is only ever replaced atomically via CREATE OR REPLACE TABLE",
            )
            # And confirm it actually IS (re)created atomically, so this test
            # cannot pass by accident (e.g. the table stopped being built at all).
            self.assertIn(f"CREATE OR REPLACE TABLE `{full_name}`", "\n".join(client.queries))

    def test_build_silver_layer_low_priority_uses_batch_priority(self) -> None:
        class _ClientWithConfig(_FakeClient):
            def __init__(self) -> None:
                super().__init__()
                self.configs: list[object] = []

            def query(self, query: str, job_config: object = None) -> _FakeJob:
                self.queries.append(query)
                self.configs.append(job_config)
                return _FakeJob()

        client = _ClientWithConfig()
        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    with patch.object(workflow_server, "sleep", return_value=None):
                        result = workflow_server.build_silver_layer(low_priority=True)

        self.assertEqual(result["priority"], "batch")
        self.assertTrue(len(client.configs) > 0)
        for cfg in client.configs:
            self.assertIsNotNone(cfg)
            self.assertEqual(getattr(cfg, "priority", None), "BATCH")

    def test_normalized_state_code_rejects_garbage_values(self) -> None:
        # Regression test for the ZIP-in-state-column bug (2026-09-10):
        # normalized_state_code's ELSE branch used to pass a raw, unvalidated
        # state_code straight through (a ZIP like "23518" or a value like
        # "USA" sailed through as a "state"), inflating the live state count
        # from ~51 to 59. Fixed by checking the raw value against an explicit
        # allow-list of real 2-letter US state/territory codes and returning
        # NULL for anything else, and by dropping the outer COALESCE's
        # redundant second fallback that re-used the same unfiltered value.
        client = _FakeClient()

        with patch.object(workflow_server, "_medallion_settings", return_value=("project", "bronze", "silver", "gold", None)):
            with patch.object(workflow_server, "_bigquery_client", return_value=client):
                with patch.object(workflow_server, "_ensure_dataset", side_effect=lambda *_: None):
                    workflow_server.build_silver_layer()

        sql = "\n".join(client.queries)
        # The allow-list of real 2-letter codes a raw state_code value must
        # match to survive - a 5-digit ZIP or "USA" is not in this list.
        self.assertIn("'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA'", sql)
        self.assertIn("VA','WA','WV','WI','WY','DC','PR','GU','VI','MP','AS'", sql)
        self.assertIn("THEN UPPER(TRIM(state_code))", sql)
        self.assertIn("ELSE NULL", sql)
        # The final state_code must fall through to the city/ZIP-based
        # reference matches (cg/z) when the raw value doesn't validate, not
        # repeat the same raw value a second time via a redundant COALESCE arm.
        self.assertIn(
            "COALESCE(l.normalized_state_code, cg.state_code, z.state_code) AS state_code",
            sql,
        )
        self.assertNotIn("NULLIF(UPPER(TRIM(l.state_code)), '')", sql)

    def test_refresh_silver_background_low_priority_thread(self) -> None:
        calls = []

        def fake_invoke(low_priority=False):
            calls.append(low_priority)
            return {"rows": 1}

        with patch.object(workflow_server, "_invoke_silver_layer", side_effect=fake_invoke):
            with patch.object(workflow_server, "_rebuild_gold_and_mirror", return_value={"gold": {}, "mirror": {}}):
                with patch.object(workflow_server, "auto_repair_error_batch", return_value={"attempted": 0, "resolved": 0, "remaining": 0}):
                    workflow_server.REPORTING_REFRESHING = False
                    started = workflow_server._refresh_silver_background(low_priority=True)
                    for thread in workflow_server.threading.enumerate():
                        if thread.name == "reporting-silver-refresh":
                            thread.join(timeout=5)
                    workflow_server.REPORTING_REFRESHING = False

        self.assertTrue(started)
        self.assertEqual(calls, [True])

    def test_a_save_that_arrives_during_a_running_refresh_gets_a_guaranteed_followup_pass(self) -> None:
        # Regression test for a real gap (2026-09-10, user-identified): a
        # save/refresh request that found REPORTING_REFRESHING already True
        # used to just return False and be forgotten - if nothing else
        # triggered a refresh afterward, that save's data would not reach
        # gold/reporting until the next hourly scheduled tick (up to an
        # hour later). "More listing saves" must mean "guaranteed to be
        # picked up soon," not "silently absorbed by whichever save
        # happened to be running first."
        pass_count = []

        def fake_invoke(low_priority=False):
            pass_count.append(1)
            # Simulate a second save arriving WHILE this pass is still the
            # one holding REPORTING_REFRESHING - exactly the race this test
            # is proving gets handled, not just a sequential re-call.
            if len(pass_count) == 1:
                second_call_started = workflow_server._refresh_silver_background(low_priority=True)
                # It must NOT spawn a second concurrent thread (that's
                # BUG-33/34's class of bug) - it should be coalesced instead.
                self.assertFalse(second_call_started)
            return {"rows": 1}

        with patch.object(workflow_server, "_invoke_silver_layer", side_effect=fake_invoke):
            with patch.object(workflow_server, "_rebuild_gold_and_mirror", return_value={"gold": {}, "mirror": {}}):
                with patch.object(workflow_server, "auto_repair_error_batch", return_value={"attempted": 0, "resolved": 0, "remaining": 0}):
                    # Real infra calls otherwise: without mocking these, the
                    # first pass spends several real seconds hitting BigQuery/
                    # SQLite (or failing slowly trying to), which can eat the
                    # thread.join() budget below before the follow-up pass
                    # this test exists to prove ever runs - a flaky-looking
                    # false negative, not a real production bug.
                    with patch.object(workflow_server, "refresh_error_count", return_value=0):
                        with patch.object(workflow_server, "reporting_quality_summary", return_value={}):
                            workflow_server.REPORTING_REFRESHING = False
                            workflow_server.REPORTING_REFRESH_PENDING = False
                            started = workflow_server._refresh_silver_background(low_priority=True)
                            for thread in workflow_server.threading.enumerate():
                                if thread.name == "reporting-silver-refresh":
                                    thread.join(timeout=5)
                            workflow_server.REPORTING_REFRESHING = False
                            workflow_server.REPORTING_REFRESH_PENDING = False

        self.assertTrue(started)
        # Exactly two passes: the original, plus one guaranteed follow-up
        # for the save that arrived mid-flight - not zero (dropped) and not
        # an unbounded loop (which would mean pending never gets cleared).
        self.assertEqual(len(pass_count), 2)


if __name__ == "__main__":
    unittest.main()
