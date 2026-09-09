"""Behavioral tests for the custom-field lifecycle and the gold view
definition-drift guard.

The rest of this batch's coverage is source-contract style (asserting on
inspect.getsource), matching the convention in test_reporting_cache.py and
test_mapping_layout_contract.py. These are the cases where a source assertion
is not enough - the behavior only shows up in which statements actually get
issued, so they drive the real functions against a fake BigQuery client.

Both the bigquery *module* and the *client* are faked. Faking only the client
looked sufficient (these tests passed standalone) but failed in a full-suite
run: other suites inject a fake google.cloud.bigquery into sys.modules and
leave the real namespace package degraded on cleanup, so a later
`from google.cloud import bigquery` resolved to a module with no
QueryJobConfig. See _fake_bigquery_modules() below.
"""

from __future__ import annotations

import inspect
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import whitespace_tool.workflow_server as ws


def _fake_bigquery_modules():
    """Other suites here inject a fake google.cloud.bigquery into sys.modules
    and, on cleanup, leave the real namespace package degraded - a later
    `from google.cloud import bigquery` then resolves to a module missing
    QueryJobConfig. These tests passed standalone and failed only in a
    full-suite run because of it. Same fix as
    test_reporting_timeseries_cache.py's _FakeBigQueryModuleMixin: inject our
    own fake so ordering can't reach us."""
    fake_bigquery = types.SimpleNamespace(
        QueryJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
        ArrayQueryParameter=lambda name, type_, value: (name, type_, value),
        ScalarQueryParameter=lambda name, type_, value: (name, type_, value),
        SchemaField=lambda name, field_type, mode="NULLABLE", default_value_expression=None:
            types.SimpleNamespace(name=name, field_type=field_type, mode=mode,
                                  default_value_expression=default_value_expression),
        Table=lambda *a, **k: types.SimpleNamespace(schema=[]),
        LoadJobConfig=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    fake_cloud = types.ModuleType("google.cloud")
    fake_cloud.bigquery = fake_bigquery
    return {
        "google": types.ModuleType("google"),
        "google.cloud": fake_cloud,
        "google.cloud.bigquery": fake_bigquery,
    }


class _FakeBigQueryModuleMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._bq_mods = patch.dict(sys.modules, _fake_bigquery_modules())
        self._bq_mods.start()
        self.addCleanup(self._bq_mods.stop)


class FakeQueryJob:
    def __init__(self, rows=None, affected=0):
        self._rows = rows or []
        self.num_dml_affected_rows = affected

    def result(self):
        return list(self._rows)


class FakeClient:
    """Records every statement issued so a test can assert on what ran."""

    def __init__(self, query_results=None, affected_by_query=None):
        self.queries: list[str] = []
        self._query_results = query_results or {}
        self._affected = affected_by_query or {}
        self.tables: dict[str, object] = {}
        self.updated: list[tuple[str, list[str]]] = []
        self.loaded: list[list[dict]] = []

    def query(self, sql, job_config=None):
        self.queries.append(sql)
        for marker, rows in self._query_results.items():
            if marker in sql:
                return FakeQueryJob(rows)
        for marker, count in self._affected.items():
            if marker in sql:
                return FakeQueryJob(affected=count)
        return FakeQueryJob()

    def get_table(self, ref):
        if str(ref) in self.tables:
            return self.tables[str(ref)]
        raise _NotFound("missing")

    def update_table(self, table, fields):
        self.updated.append((getattr(table, "_ref", ""), list(fields)))
        return table

    def load_table_from_json(self, rows, _ref, job_config=None):
        self.loaded.append(list(rows))
        return FakeQueryJob()

    def create_table(self, table):
        return table


class _NotFound(Exception):
    code = 404


class CustomFieldArchiveTests(_FakeBigQueryModuleMixin):
    """Removing a custom field must archive it, never delete it.

    Listings already saved carry that field's values inside
    listings.custom_fields. Dropping the catalog row strands them with no
    label, type or provenance to interpret them by.
    """

    def _run_delete(self, client):
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "invalidate_cache"):
            return ws.delete_custom_field({
                "field_key": "loyaltyTier", "password": "54321", "business_id": "b1",
            })

    def test_delete_issues_an_archive_update_and_never_a_delete(self) -> None:
        client = FakeClient(query_results={
            "SELECT field_id, label, is_custom": [
                {"field_id": "f1", "label": "Loyalty Tier", "is_custom": True, "business_id": "b1"},
            ],
        })
        result = self._run_delete(client)

        self.assertTrue(result["archived"])
        archive_statements = [q for q in client.queries if "is_archived = TRUE" in q]
        self.assertEqual(len(archive_statements), 1, "expected exactly one archive UPDATE")
        self.assertIn("UPDATE", archive_statements[0])
        self.assertIn("archived_at", archive_statements[0])
        # The whole point: nothing may be destroyed.
        self.assertFalse([q for q in client.queries if "DELETE FROM" in q.upper()],
                         "custom field removal must never issue a DELETE")

    def test_standard_fields_can_never_be_archived(self) -> None:
        client = FakeClient(query_results={
            "SELECT field_id, label, is_custom": [
                {"field_id": "f2", "label": "Address", "is_custom": False, "business_id": "b1"},
            ],
        })
        with self.assertRaisesRegex(ValueError, "Standard fields"):
            self._run_delete(client)
        self.assertFalse([q for q in client.queries if "is_archived = TRUE" in q])

    def test_missing_field_is_rejected_rather_than_silently_succeeding(self) -> None:
        client = FakeClient(query_results={"SELECT field_id, label, is_custom": []})
        with self.assertRaisesRegex(ValueError, "was not found"):
            self._run_delete(client)

    def test_admin_password_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "Administrative password"):
            ws.delete_custom_field({"field_key": "x", "password": "wrong", "business_id": "b1"})


class CustomFieldCreateTests(_FakeBigQueryModuleMixin):
    """Re-creating a previously archived field restores that row instead of
    inserting a second row with the same slug - the archived definition
    already describes the values sitting in listings.custom_fields."""

    def _create(self, client, affected):
        client._affected = affected
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "field_catalog", return_value=[]), \
             patch.object(ws, "_ensure_listings_table"), \
             patch.object(ws, "invalidate_cache"):
            return ws.create_custom_field({
                "label": "Loyalty Tier", "slug": "loyaltyTier",
                "password": "54321", "business_id": "b1", "type": "string",
            })

    def test_recreating_an_archived_field_revives_it_without_duplicating(self) -> None:
        client = FakeClient()
        result = self._create(client, {"SET is_archived = FALSE": 1})

        self.assertTrue(result["restored"])
        self.assertEqual(result["field"]["key"], "loyaltytier")
        # Revived, so no new catalog row may be written.
        self.assertEqual(client.loaded, [], "revive must not insert a duplicate slug")
        revive = [q for q in client.queries if "SET is_archived = FALSE" in q]
        self.assertEqual(len(revive), 1)
        self.assertIn("is_archived IS TRUE", revive[0])

    def test_a_genuinely_new_field_is_inserted(self) -> None:
        client = FakeClient()
        result = self._create(client, {"SET is_archived = FALSE": 0})

        self.assertNotIn("restored", result)
        self.assertEqual(len(client.loaded), 1, "a new field must be written to the catalog")
        self.assertEqual(client.loaded[0][0]["slug"], "loyaltytier")
        self.assertEqual(client.loaded[0][0]["table_name"], "listings")

    def test_creating_a_field_ensures_the_column_that_stores_its_values(self) -> None:
        # The catalog must not advertise somewhere for data to go that the
        # warehouse does not actually have.
        client = FakeClient()
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "field_catalog", return_value=[]), \
             patch.object(ws, "invalidate_cache"), \
             patch.object(ws, "_ensure_listings_table") as ensure:
            client._affected = {"SET is_archived = FALSE": 0}
            ws.create_custom_field({
                "label": "Loyalty Tier", "slug": "loyaltyTier",
                "password": "54321", "business_id": "b1", "type": "string",
            })
        ensure.assert_called_once()

    def test_a_standard_field_name_cannot_be_hijacked(self) -> None:
        client = FakeClient()
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_bigquery_client", return_value=client):
            with self.assertRaisesRegex(ValueError, "standard field"):
                ws.create_custom_field({
                    "label": "Address", "slug": "address",
                    "password": "54321", "business_id": "b1", "type": "string",
                })


class GoldViewDefinitionDriftTests(_FakeBigQueryModuleMixin):
    """A gold view whose SELECT list changed in code still EXISTS with its old
    definition. _ensure_gold_reporting_views() used to return early on mere
    existence, so the edited view never reached an already-deployed
    environment and kept serving its old columns forever - live-confirmed
    when bronze and silver picked up custom_fields and gold did not.
    """

    REQUIRED = ("vw_zip_brand_activity", "vw_brand_summary", "vw_reporting_locations",
                "vw_reporting_filter_options", "vw_reporting_gap_base")

    def _client_with_views(self, description):
        client = FakeClient()
        for view in self.REQUIRED:
            client.tables[f"gold.{view}"] = SimpleNamespace(description=description, _ref=view)
        return client

    def test_views_stamped_with_the_current_version_are_left_alone(self) -> None:
        client = self._client_with_views(
            f"birdeye_gold_view_version={ws.GOLD_VIEW_DEFINITION_VERSION}")
        with patch.object(ws, "build_gold_layer", side_effect=AssertionError("must not rebuild")):
            self.assertFalse(ws._ensure_gold_reporting_views(client, "gold"))

    def test_a_stale_version_stamp_triggers_a_rebuild(self) -> None:
        client = self._client_with_views("birdeye_gold_view_version=1999-01-01.old")
        with patch.object(ws, "prepare_zipcodes"), \
             patch.object(ws, "build_silver_layer", return_value={"status": "ok"}), \
             patch.object(ws, "build_gold_layer", return_value={"views": []}) as rebuild, \
             patch.object(ws, "sync_gold_mirror"), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "_ensure_dataset"), \
             patch.object(ws, "_ensure_businesses_table"), \
             patch.object(ws, "_ensure_listings_table"):
            ws._ensure_gold_reporting_views(client, "gold")
        rebuild.assert_called_once()

    def test_an_unstamped_legacy_view_is_treated_as_stale(self) -> None:
        # Views created before versioning existed carry no stamp at all.
        client = self._client_with_views(None)
        with patch.object(ws, "prepare_zipcodes"), \
             patch.object(ws, "build_silver_layer", return_value={"status": "ok"}), \
             patch.object(ws, "build_gold_layer", return_value={"views": []}) as rebuild, \
             patch.object(ws, "sync_gold_mirror"), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "_ensure_dataset"), \
             patch.object(ws, "_ensure_businesses_table"), \
             patch.object(ws, "_ensure_listings_table"):
            ws._ensure_gold_reporting_views(client, "gold")
        rebuild.assert_called_once()

    def test_build_gold_layer_stamps_every_view_it_creates(self) -> None:
        # Without the stamp the drift check above can never pass, so every
        # ensure would rebuild the whole gold layer on every call.
        import inspect

        source = inspect.getsource(ws.build_gold_layer)
        self.assertIn('view_table.description = f"birdeye_gold_view_version={GOLD_VIEW_DEFINITION_VERSION}"', source)
        self.assertIn('client.update_table(view_table, ["description"])', source)
        self.assertIn("for view_ref in views:", source)


class ExtrasCollectionTests(unittest.TestCase):
    """_collect_extras() decides what survives the bronze write, so its edge
    cases are the difference between preserving a source column and losing
    it."""

    def test_mapped_columns_are_not_duplicated_into_extras(self) -> None:
        row = {"Name": "S", "Zip": "78701", "Loyalty": "gold"}
        fields = {"name": "Name", "postal_code": "Zip"}
        self.assertEqual(ws_normalization()._collect_extras(row, fields), {"Loyalty": "gold"})

    def test_internal_meta_key_is_never_exported(self) -> None:
        row = {"Loyalty": "gold", "__meta": {"template_id": "t1"}}
        self.assertEqual(ws_normalization()._collect_extras(row, {}), {"Loyalty": "gold"})

    def test_blank_and_null_values_are_skipped(self) -> None:
        row = {"A": "", "B": "   ", "C": None, "D": "keep"}
        self.assertEqual(ws_normalization()._collect_extras(row, {}), {"D": "keep"})

    def test_no_extras_returns_none_rather_than_an_empty_document(self) -> None:
        # None means the column stays NULL instead of storing a useless "{}".
        self.assertIsNone(ws_normalization()._collect_extras({"Name": "S"}, {"name": "Name"}))
        self.assertIsNone(ws_normalization()._collect_extras("not a dict", {}))

    def test_a_dotted_mapping_keeps_the_parent_object(self) -> None:
        # Deliberate trade: duplicating a little beats losing a column, since
        # never losing source data is the point of this field.
        row = {"address": {"street": "1 Main", "unit": "4B"}}
        self.assertEqual(ws_normalization()._collect_extras(row, {"address": "address.street"}),
                         {"address": {"street": "1 Main", "unit": "4B"}})


def ws_normalization():
    from whitespace_tool import normalization
    return normalization


class MetricExportWorkbookTests(unittest.TestCase):
    """The metrics sheet is computed from the sheet-1 rows, so the two sheets
    can never disagree and the headline figure is reproducible by hand."""

    def _load(self, metric, rows, reason=""):
        import io
        import openpyxl
        data = ws._metric_export_workbook(metric, rows, reason)
        return openpyxl.load_workbook(io.BytesIO(data))

    def test_metrics_sheet_arithmetic_matches_the_entity_rows(self) -> None:
        rows = [
            {"listing_id": "L1", "brand": "A", "has_valid_zip": True},
            {"listing_id": "L2", "brand": "A", "has_valid_zip": False},
            {"listing_id": "L3", "brand": "B", "has_valid_zip": True},
            {"listing_id": "L4", "brand": "B", "has_valid_zip": True},
        ]
        wb = self._load("zip-completeness", rows)
        # Third sheet added: a per-brand competitor breakdown, since
        # whitespace analysis is a competitive question.
        self.assertEqual(wb.sheetnames, ["Listing Data", "Metrics", "Competitors"])
        self.assertEqual(wb["Listing Data"].max_row - 1, 4)

        metrics = {r[0]: (r[1], r[2]) for r in wb["Metrics"].iter_rows(min_row=2, values_only=True)}
        self.assertEqual(metrics["Rows in this export"][0], 4)
        self.assertEqual(metrics["Has Valid ZIP = TRUE"][0], 3)
        self.assertEqual(metrics["Has Valid ZIP = FALSE"][0], 1)
        self.assertIn("75.0%", metrics["Has Valid ZIP = TRUE"][1])
        self.assertEqual(metrics["Distinct Brand"][0], 2)

    def test_an_unavailable_source_is_labelled_not_presented_as_a_zero(self) -> None:
        wb = self._load("uncovered-zips", [], "view missing")
        metrics = [r[0] for r in wb["Metrics"].iter_rows(min_row=2, values_only=True)]
        self.assertIn("DATA UNAVAILABLE", metrics)
        self.assertIn("view missing", str(wb["Listing Data"]["A2"].value))

    def test_a_genuine_zero_does_not_claim_unavailability(self) -> None:
        wb = self._load("uncovered-zips", [])
        metrics = [r[0] for r in wb["Metrics"].iter_rows(min_row=2, values_only=True)]
        self.assertNotIn("DATA UNAVAILABLE", metrics)

    def test_oversized_cells_are_truncated_rather_than_failing_the_export(self) -> None:
        # Excel refuses cells over 32,767 chars; raw_record JSON can exceed
        # that, and a hard failure would lose the whole export over one field.
        wb = self._load("invalid-listings", [{"raw_record": "x" * 40000}])
        value = wb["Listing Data"]["A2"].value
        self.assertLess(len(value), 32767)
        self.assertTrue(value.endswith("...[truncated]"))

    def test_every_row_key_becomes_a_column_even_when_rows_differ(self) -> None:
        # Different parses carry different columns; a union of keys means a
        # row's value is never dropped just because row 1 lacked that key.
        wb = self._load("invalid-listings", [{"a": 1}, {"b": 2}])
        headers = [c.value for c in wb["Listing Data"][1]]
        self.assertEqual(headers, ["A", "B"])


if __name__ == "__main__":
    unittest.main()


class MetricExportSqlShapeTests(unittest.TestCase):
    """Live-caught bug: the ZIP-family export computed `is_covered` in its
    SELECT list and then filtered on it in the WHERE of the SAME query, which
    BigQuery rejects with "Unrecognized name: is_covered". Every ZIP metric
    (Uncovered ZIPs, Covered Markets, Market ZIPs) returned a 400.

    No fake-client test could have caught this - a fake returns rows
    regardless of whether the SQL is valid. That is exactly why the live
    endpoint smoke run matters, and why this asserts on SQL shape.
    """

    def test_is_covered_is_computed_in_its_own_cte_before_being_filtered(self) -> None:
        import inspect
        import re

        source = inspect.getsource(ws.reporting_metric_export)
        self.assertIn("flagged AS (", source)
        self.assertIn("SELECT *, location_count > 0 AS is_covered FROM zips", source)
        self.assertIn("SELECT * FROM flagged", source)

        # The alias must never be defined and filtered inside one SELECT.
        zip_block = source.split("elif metric in _ZIP_METRIC_SLUGS:", 1)[1].split("elif metric in _BRAND_METRIC_SLUGS:", 1)[0]
        same_select = re.search(
            r"SELECT \*, location_count > 0 AS is_covered\s+FROM zips\s+\{coverage_filter\}", zip_block)
        self.assertIsNone(same_select, "is_covered filtered in the same SELECT that defines it")

    def test_every_zip_metric_has_a_coverage_filter_branch(self) -> None:
        import inspect

        source = inspect.getsource(ws.reporting_metric_export)
        self.assertIn('if metric == "uncovered-zips":', source)
        self.assertIn('coverage_filter = "WHERE NOT is_covered"', source)
        self.assertIn('coverage_filter = "WHERE is_covered"', source)
        # The universe metrics export both sides of the ratio.
        self.assertIn('coverage_filter = ""', source)


class MetricExportBundleTests(unittest.TestCase):
    """One click hands over a ZIP: the workbook, normalized CSVs, and a
    README naming the filters that produced it. Excel alone could carry
    neither the normalized copy nor the provenance note."""

    def _bundle(self, rows, reason="", filters=None):
        import io
        import zipfile
        data = ws._metric_export_bundle("zip-completeness", rows, reason, filters or {})
        return zipfile.ZipFile(io.BytesIO(data))

    def _rows(self):
        return [
            {"listing_id": "L1", "brand": "Domino's", "state_code": "TX", "city_name": "Austin",
             "zip_code": "78701", "has_valid_zip": True, "has_valid_coordinates": True},
            {"listing_id": "L2", "brand": "Domino's", "state_code": "CA", "city_name": "LA",
             "zip_code": "90001", "has_valid_zip": True, "has_valid_coordinates": False},
            {"listing_id": "L3", "brand": "Pizza Hut", "state_code": "TX", "city_name": "Dallas",
             "zip_code": "75201", "has_valid_zip": False, "has_valid_coordinates": True},
        ]

    def test_bundle_carries_workbook_normalized_csvs_and_a_readme(self) -> None:
        bundle = self._bundle(self._rows())
        self.assertEqual(
            sorted(bundle.namelist()),
            ["README.txt", "competitors.csv", "listings.csv", "metrics.csv", "zip-completeness.xlsx"])

    def test_readme_records_the_filters_that_produced_the_file(self) -> None:
        # A file with no provenance can't be trusted later - "is this all
        # states or just two?" has to be answerable from the file itself.
        bundle = self._bundle(self._rows(), filters={"state": ["TX", "CA"], "brand": []})
        readme = bundle.read("README.txt").decode()
        self.assertIn("state: TX, CA", readme)
        self.assertIn("Rows in this export: 3", readme)
        self.assertIn("Definition:", readme)

    def test_readme_says_so_when_nothing_was_filtered(self) -> None:
        readme = self._bundle(self._rows(), filters={}).read("README.txt").decode()
        self.assertIn("none (full population)", readme)

    def test_competitor_breakdown_reconciles_with_the_listing_rows(self) -> None:
        rows = self._rows()
        competitors = ws._metric_export_competitors(rows)
        self.assertEqual([c["brand"] for c in competitors], ["Domino's", "Pizza Hut"])
        self.assertEqual(sum(c["listings"] for c in competitors), len(rows))
        self.assertAlmostEqual(sum(c["share_pct"] for c in competitors), 100.0, places=1)
        dominos = competitors[0]
        self.assertEqual(dominos["listings"], 2)
        self.assertEqual(dominos["states"], 2)
        self.assertEqual(dominos["with_coordinates"], 1)

    def test_rows_without_a_brand_produce_no_competitor_sheet(self) -> None:
        # Better an explicit "nothing to compare" than a sheet of blanks.
        self.assertEqual(ws._metric_export_competitors([{"zip_code": "78701"}]), [])
        bundle = self._bundle([{"zip_code": "78701"}])
        self.assertNotIn("competitors.csv", bundle.namelist())

    def test_hitting_the_row_ceiling_is_reported_as_partial_not_unavailable(self) -> None:
        # A truncated file that looks complete is worse than no file.
        summary = ws._metric_export_summary(
            "zip-completeness", [{"a": 1}],
            f"This export reached the {ws.METRIC_EXPORT_ROW_LIMIT:,}-row ceiling, so it is a partial result.")
        labels = [row["metric"] for row in summary]
        self.assertIn("PARTIAL RESULT", labels)
        self.assertNotIn("DATA UNAVAILABLE", labels)

    def test_the_row_ceiling_covers_a_real_analyst_filter(self) -> None:
        # "20 states, up to 200k records" must actually come back.
        self.assertGreaterEqual(ws.METRIC_EXPORT_ROW_LIMIT, 200000)


class MetricExportFilterTests(unittest.TestCase):
    """Selecting 20 states used to collapse to a single scalar compared with
    `=`, so the export came back empty instead of covering the selection."""

    def test_filters_accept_repeated_and_comma_separated_values(self) -> None:
        import inspect
        source = inspect.getsource(ws.reporting_metric_export)
        assert 'def _multi(name: str, upper: bool = False)' in source
        assert 'for piece in str(raw or "").split(","):' in source
        assert 'bigquery.ArrayQueryParameter("states", "STRING", states)' in source
        assert 'bigquery.ArrayQueryParameter("brands", "STRING", brands)' in source

    def test_every_filter_uses_array_membership_not_equality(self) -> None:
        import inspect
        import re
        source = inspect.getsource(ws.reporting_metric_export)
        self.assertIn("IN UNNEST(@states)", source)
        self.assertIn("IN UNNEST(@brands)", source)
        # No scalar comparison may survive, or that filter silently matches
        # only the first selected value.
        self.assertEqual(re.findall(r"@(?:brand|state) = ''", source), [])


class EmptyArrayParameterTests(unittest.TestCase):
    """BigQuery converts an EMPTY array parameter to NULL, so
    `ARRAY_LENGTH(@brands) = 0` evaluates to NULL rather than TRUE - the whole
    WHERE clause becomes NULL and EVERY row is filtered out.

    Live-caught: an export with no filters at all returned 0 rows instead of
    37,208. Verified against real BigQuery:
        ARRAY_LENGTH(<empty param>) -> None,  (... = 0) -> None,  IS NULL -> True
    """

    def test_every_array_length_guard_in_the_export_is_null_safe(self) -> None:
        import inspect
        import re

        source = inspect.getsource(ws.reporting_metric_export)
        unguarded = re.findall(r"(?<!COALESCE\()ARRAY_LENGTH\(@(\w+)\) = 0", source)
        # Every occurrence must be wrapped in COALESCE(..., 0).
        bare = [name for name in unguarded
                if f"COALESCE(ARRAY_LENGTH(@{name}), 0) = 0" not in source]
        self.assertEqual(bare, [], f"unguarded empty-array checks: {bare}")
        self.assertIn("COALESCE(ARRAY_LENGTH(@brands), 0) = 0", source)
        self.assertIn("COALESCE(ARRAY_LENGTH(@states), 0) = 0", source)

    def test_no_bare_array_length_equals_zero_remains(self) -> None:
        import inspect
        import re

        source = inspect.getsource(ws.reporting_metric_export)
        # Strip the COALESCE-wrapped ones, then nothing may be left.
        stripped = source.replace("COALESCE(ARRAY_LENGTH(@brands), 0) = 0", "")
        stripped = stripped.replace("COALESCE(ARRAY_LENGTH(@states), 0) = 0", "")
        self.assertEqual(re.findall(r"ARRAY_LENGTH\(@\w+\) = 0", stripped), [])


class SchemaEnsureMemoTests(unittest.TestCase):
    """Table schemas only change when the process deploys new code, but the
    _ensure_*_table() passes re-ran on EVERY save - each a BigQuery get_table
    round trip. Measured live: a round trip floors at ~1.75s, so two ensure
    passes added ~3.6s to every single-record edit before any real work.
    """

    def setUp(self) -> None:
        ws._forget_ensured_tables()

    def tearDown(self) -> None:
        ws._forget_ensured_tables()

    def test_an_ensure_pass_runs_once_per_process_not_once_per_save(self) -> None:
        calls = []
        def fake_ensure(client, project_id, dataset_id):
            calls.append((project_id, dataset_id))
        for _ in range(5):
            ws._ensure_once("listings", fake_ensure, object(), "p", "d")
        self.assertEqual(len(calls), 1, "ensure pass must not repeat per save")

    def test_each_table_and_dataset_is_memoized_separately(self) -> None:
        calls = []
        fake = lambda c, p, d: calls.append((p, d))
        ws._ensure_once("listings", fake, object(), "p", "d")
        ws._ensure_once("error_listings", fake, object(), "p", "d")   # different table
        ws._ensure_once("listings", fake, object(), "p", "other")     # different dataset
        ws._ensure_once("listings", fake, object(), "p", "d")         # repeat -> skipped
        self.assertEqual(len(calls), 3)

    def test_a_failed_ensure_is_retried_rather_than_marked_done(self) -> None:
        # Caching a failure would leave a table permanently un-reconciled.
        attempts = []
        def failing(client, project_id, dataset_id):
            attempts.append(1)
            raise RuntimeError("transient")
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                ws._ensure_once("listings", failing, object(), "p", "d")
        self.assertEqual(len(attempts), 2)

    def test_clearing_data_forgets_the_memo(self) -> None:
        # A master delete drops the tables, so the next write must reconcile
        # them again rather than trusting a stale "already ensured" mark.
        import inspect
        ws._ensure_once("listings", lambda c, p, d: None, object(), "p", "d")
        ws._forget_ensured_tables()
        calls = []
        ws._ensure_once("listings", lambda c, p, d: calls.append(1), object(), "p", "d")
        self.assertEqual(len(calls), 1)
        self.assertIn("_forget_ensured_tables()", inspect.getsource(ws.master_delete_data))


class IdleBrandEnrichmentTests(unittest.TestCase):
    """Enrichment that fills blank brand contact fields from open sources.

    Strictly best-effort background work on a 512MB box: it waits for real
    idle time, takes a handful of brands, and sleeps between each one. It
    must never be the reason the app feels heavy.
    """

    def test_loop_waits_for_genuine_idle_before_each_pass(self) -> None:
        import inspect

        source = inspect.getsource(ws._start_brand_enrichment_background)
        assert "idle_seconds = wall_clock_time() - LAST_FOREGROUND_ACTIVITY_AT" in source
        assert "if idle_seconds < BRAND_ENRICH_IDLE_SECONDS:" in source
        # A full minute of quiet, not the 10s the auto-repair loop uses -
        # this work is lower priority than review repair.
        self.assertGreaterEqual(ws.BRAND_ENRICH_IDLE_SECONDS, 60.0)
        # Backs off hard when there is nothing to do rather than spinning.
        # "attempted" now sums the brand and store passes, which share this
        # thread - a quiet brand pass must not force a 5-minute sleep while
        # store-level enrichment still has work.
        assert 'attempted = result["attempted"] + locations.get("attempted", 0)' in source
        assert "sleep(300.0 if not attempted else 60.0)" in source
        assert "_idle_location_enrichment_pass()" in source

    def test_a_pass_is_small_and_paced(self) -> None:
        import inspect

        self.assertLessEqual(ws.BRAND_ENRICH_BATCH, 5)
        self.assertGreaterEqual(ws.BRAND_ENRICH_PAUSE_SECONDS, 10.0)
        source = inspect.getsource(ws._idle_brand_enrichment_pass)
        assert "_enrichment_checkpoint()" in source  # honours the stop signal
        assert "sleep(BRAND_ENRICH_PAUSE_SECONDS)" in source

    def test_a_brand_is_attempted_once_per_process(self) -> None:
        # Without this, a brand the open sources genuinely cannot resolve
        # would be retried on every single cycle forever.
        import inspect

        source = inspect.getsource(ws._idle_brand_enrichment_pass)
        assert "_BRAND_ENRICH_ATTEMPTED.add(business_id)" in source
        assert "if str(r[\"business_id\"]) not in ws._BRAND_ENRICH_ATTEMPTED" in source.replace("ws.", "") \
            or "not in _BRAND_ENRICH_ATTEMPTED" in source

    def test_only_blank_fields_are_written(self) -> None:
        # A value a person entered outranks anything a public source guessed.
        import inspect

        source = inspect.getsource(ws._idle_brand_enrichment_pass)
        # Candidates are selected on the blank condition, AND the UPDATE
        # re-checks it - so a value written between the two cannot be
        # clobbered by a stale enrichment result.
        self.assertEqual(source.count("(website_url IS NULL OR website_url = '')"), 2)
        # Nothing is written when the sources could not establish a value.
        assert "if not website:" in source and "continue" in source

    def test_the_loop_is_started_with_the_server(self) -> None:
        import inspect

        assert "_start_brand_enrichment_background()" in inspect.getsource(ws.serve)


class CacheObservabilityTests(unittest.TestCase):
    """Only slow calls were recorded, which hid the death-by-a-thousand-cuts
    case: a call that is individually fast but runs thousands of times costs
    more than one slow call."""

    def test_every_action_is_counted_not_only_slow_ones(self) -> None:
        from whitespace_tool import sqlite_cache

        sqlite_cache.init_sqlite_cache()
        before = {row["action"]: row["calls"] for row in sqlite_cache.get_cache_action_stats(200)}
        for _ in range(3):
            sqlite_cache.get_auto_repair_stats()
        after = {row["action"]: row["calls"] for row in sqlite_cache.get_cache_action_stats(200)}
        self.assertGreaterEqual(after.get("get_auto_repair_stats", 0),
                                before.get("get_auto_repair_stats", 0) + 3)

    def test_stats_are_ranked_by_total_time_and_carry_an_average(self) -> None:
        from whitespace_tool import sqlite_cache

        sqlite_cache.init_sqlite_cache()
        sqlite_cache.get_auto_repair_stats()
        rows = sqlite_cache.get_cache_action_stats(50)
        self.assertTrue(rows)
        totals = [row["total_ms"] for row in rows]
        self.assertEqual(totals, sorted(totals, reverse=True))
        for row in rows:
            self.assertIn("avg_ms", row)
            self.assertIn("calls", row)

    def test_counters_are_in_memory_not_a_row_per_cache_read(self) -> None:
        # Persisting a row per cache read would cost more than the reads.
        import inspect
        from whitespace_tool import sqlite_cache

        source = inspect.getsource(sqlite_cache._tally_cache_action)
        assert "_CACHE_ACTION_TALLY" in source
        assert "conn.execute" not in source
        # Slow calls are still persisted, as before.
        wrapper = inspect.getsource(sqlite_cache._timed_cache_action)
        assert "if duration_ms >= SLOW_ACTION_THRESHOLD_MS:" in wrapper
        assert "_record_slow_action(func.__name__, duration_ms)" in wrapper


class BrandLevelFixStateTests(unittest.TestCase):
    """Quality-by-Brand counted is_ai_enriched over the currently-OPEN error
    rows while the headline card counted all-time fix events - two different
    measures under one label, which is why the numbers disagreed."""

    def test_per_brand_counts_use_the_same_cumulative_model(self) -> None:
        import inspect

        source = inspect.getsource(ws.fix_state_counts_by_brand)
        # Same five expressions as the headline query.
        for expression in (
            "COUNTIF(state = 'fixed' AND ai_fixed) AS ai_fixed",
            "COUNTIF(state = 'fixed' AND NOT ai_fixed AND ai_suggested) AS ai_suggested_fixed",
            "COUNTIF(state = 'fixed' AND NOT ai_fixed AND NOT ai_suggested) AS manual_fixed",
        ):
            assert expression in source, expression
        # Counted over soft-deleted rows too, or fixed records vanish.
        assert "IF(e.is_deleted IS TRUE, 'fixed', 'pending')" in source
        assert "GROUP BY brand" in source

    def test_the_brand_table_is_overwritten_with_the_cumulative_counts(self) -> None:
        import inspect

        source = inspect.getsource(ws.reporting_quality_summary)
        assert "cumulative_by_brand = fix_state_counts_by_brand(client=client)" in source
        assert 'bucket["ai_enriched"] = cumulative["ai_fixed"]' in source
        # Best-effort: a failure must leave the open-row counts rendering.
        assert 'LOGGER.warning("fix_state_by_brand_failed error=%s", exc)' in source


class FailingFieldReportingTests(unittest.TestCase):
    """A blanket "check required fields, ZIP Code, and coordinates" made the
    user re-read every input hunting for the one that mattered."""

    def test_save_reports_which_fields_failed(self) -> None:
        import inspect

        source = inspect.getsource(ws.save_mapper)
        assert '"failed_fields": failed_field_names' in source
        # Distinct, order-preserving.
        assert "if field and field not in failed_field_names:" in source

    def test_the_retry_message_names_those_fields(self) -> None:
        from pathlib import Path

        review_js = (Path(__file__).resolve().parents[1] / "ui" / "js" / "review.js").read_text()
        assert "const failed = Array.isArray(result.failed_fields) ? result.failed_fields : [];" in review_js
        assert "need${failed.length === 1 ? \"s\" : \"\"} attention:" in review_js
        # Formatted labels, not raw DB keys.
        assert "formatFieldLabel(f) || f" in review_js
        # The blanket message must not come back.
        assert "Please check required fields, ZIP Code, and coordinates." not in review_js


class MetricExportExecutionTests(_FakeBigQueryModuleMixin):
    """reporting_metric_export() is ~240 lines that no test actually EXECUTED -
    every existing test asserted on its source text. That is exactly how the
    empty-array NULL bug and the `is_covered` SQL error reached a live server:
    source assertions cannot run a query. These drive the real function.
    """

    class _Job:
        def __init__(self, rows):
            self._rows = rows

        def result(self):
            return self._rows

    class _Client:
        """Returns rows for any query and records the SQL it was given."""

        def __init__(self, rows=None):
            self.queries = []
            self._rows = rows if rows is not None else [
                {"listing_id": "L1", "brand": "Acme", "state_code": "TX",
                 "city_name": "Austin", "zip_code": "78701",
                 "has_valid_zip": True, "has_valid_coordinates": True,
                 "is_stale": False, "duplicate_group_count": 1, "is_duplicate": False},
            ]

        def query(self, sql, job_config=None):
            self.queries.append(sql)
            return MetricExportExecutionTests._Job(self._rows)

    def _run(self, params, rows=None):
        client = self._Client(rows)
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "get_stale_after_days", return_value=90):
            payload, filename = ws.reporting_metric_export(params)
        return payload, filename, client

    def test_a_listing_metric_produces_a_real_zip_bundle(self) -> None:
        import io
        import zipfile

        payload, filename, _ = self._run({"metric": ["zip-completeness"]})
        self.assertTrue(filename.endswith(".zip"))
        bundle = zipfile.ZipFile(io.BytesIO(payload))
        self.assertIn("zip-completeness.xlsx", bundle.namelist())
        self.assertIn("listings.csv", bundle.namelist())
        self.assertIn("README.txt", bundle.namelist())

    def test_every_registered_metric_slug_actually_runs(self) -> None:
        # Catches a slug that is registered but whose branch raises - the
        # class of bug that made uncovered-zips 400 in production.
        known = (set(ws._ERROR_METRIC_PREDICATES) | set(ws._FIX_EVENT_METRIC_TYPES)
                 | set(ws._LISTING_METRIC_SLUGS) | set(ws._LOCATION_VIEW_METRIC_SLUGS)
                 | set(ws._ZIP_METRIC_SLUGS) | set(ws._BRAND_METRIC_SLUGS))
        for slug in sorted(known):
            with self.subTest(metric=slug):
                payload, filename, _ = self._run({"metric": [slug]})
                self.assertTrue(payload)
                self.assertTrue(filename.startswith(slug))

    def test_multi_value_filters_reach_the_query_as_arrays(self) -> None:
        _, _, client = self._run({"metric": ["zip-completeness"], "state": ["TX", "CA"]})
        sql = "\n".join(client.queries)
        self.assertIn("IN UNNEST(@states)", sql)
        # And the empty-array NULL trap stays guarded.
        self.assertIn("COALESCE(ARRAY_LENGTH(@states), 0) = 0", sql)

    def test_comma_separated_filters_are_split(self) -> None:
        _, _, client = self._run({"metric": ["zip-completeness"], "state": ["TX,CA,NY"]})
        self.assertTrue(client.queries)  # ran without error

    def test_an_unknown_metric_raises_rather_than_returning_an_empty_file(self) -> None:
        with self.assertRaises(ValueError):
            self._run({"metric": ["not-a-real-metric"]})
        with self.assertRaises(ValueError):
            self._run({"metric": [""]})

    def test_a_missing_table_is_labelled_unavailable_not_reported_as_zero(self) -> None:
        import io
        import zipfile

        class _NotFound(Exception):
            code = 404

        class _MissingClient(MetricExportExecutionTests._Client):
            def query(self, sql, job_config=None):
                raise _NotFound("Not found: Table")

        client = _MissingClient()
        with patch.object(ws, "_warehouse_settings", return_value=("p", "d", None)), \
             patch.object(ws, "_medallion_settings", return_value=("p", "b", "s", "g", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_once"), \
             patch.object(ws, "get_stale_after_days", return_value=90):
            payload, _ = ws.reporting_metric_export({"metric": ["zip-completeness"]})
        readme = zipfile.ZipFile(io.BytesIO(payload)).read("README.txt").decode()
        self.assertIn("does not exist yet", readme)


class TableExportExecutionTests(_FakeBigQueryModuleMixin):
    """Same reasoning for the per-table exports."""

    def test_each_table_export_runs_and_carries_its_own_columns(self) -> None:
        import csv
        import io
        import zipfile

        summary = {
            "gaps": [{"zip_code": "78701", "state": "TX", "population": 100}],
            "brands": [{"brand": "Acme", "locations": 3}],
            "top_states": [{"state": "TX", "locations": 5}],
            "top_cities": [{"city": "Austin", "locations": 2}],
        }
        for table, expected_column in (("market-gaps", "zip_code"), ("brand-comparison", "brand"),
                                       ("top-states", "state"), ("top-cities", "city")):
            with self.subTest(table=table):
                with patch.object(ws, "reporting_summary", return_value=summary):
                    payload, filename = ws.reporting_table_export({"table": [table]})
                self.assertTrue(filename.startswith(table))
                bundle = zipfile.ZipFile(io.BytesIO(payload))
                rows = list(csv.DictReader(io.StringIO(bundle.read("listings.csv").decode())))
                self.assertIn(expected_column, rows[0])

    def test_an_unknown_table_raises(self) -> None:
        with self.assertRaises(ValueError):
            ws.reporting_table_export({"table": ["nope"]})
        with self.assertRaises(ValueError):
            ws.reporting_table_export({})


class GenericSqlHelperTests(unittest.TestCase):
    """91 call sites issued client.query() directly, each re-deriving its own
    parameter plumbing and error handling. That is how a scalar filter
    survived in one query while its siblings moved to arrays."""

    def setUp(self) -> None:
        self._bq = patch.dict(sys.modules, _fake_bigquery_modules())
        self._bq.start()
        self.addCleanup(self._bq.stop)

    def test_parameters_are_inferred_from_plain_python_values(self) -> None:
        # The fake builds (name, type, value) for both scalar and array.
        built = {p[0]: p[1] for p in ws._sql_params(
            {"s": "TX", "n": 5, "f": 1.5, "b": True, "arr": ["TX", "CA"]})}
        self.assertEqual(built["s"], "STRING")
        self.assertEqual(built["n"], "INT64")
        self.assertEqual(built["f"], "FLOAT64")
        self.assertEqual(built["b"], "BOOL")
        self.assertEqual(built["arr"], "STRING")  # element type

    def test_bool_is_not_mistaken_for_an_int(self) -> None:
        # bool is a subclass of int in Python; checking int first would type
        # every flag as INT64 and break the comparison in BigQuery.
        self.assertEqual(ws._sql_params({"b": True})[0][1], "BOOL")

    def test_an_empty_list_still_produces_an_array_parameter(self) -> None:
        # It must stay an ARRAY (BigQuery turns it into NULL, which is why
        # every ARRAY_LENGTH check is COALESCE-guarded) - not a scalar.
        built = ws._sql_params({"x": []})[0]
        self.assertEqual(built[2], [])          # value kept as a list
        self.assertEqual(built[1], "STRING")    # default element type

    def test_no_parameters_is_an_empty_list_not_none(self) -> None:
        self.assertEqual(ws._sql_params(None), [])
        self.assertEqual(ws._sql_params({}), [])

    def test_dml_returns_the_rows_it_actually_affected(self) -> None:
        class _Job:
            num_dml_affected_rows = 7
            def result(self): return []
        class _Client:
            def query(self, sql, job_config=None): return _Job()
        self.assertEqual(ws.run_sql_dml(_Client(), "UPDATE x SET a=1"), 7)

    def test_dml_reports_zero_rather_than_none_when_nothing_matched(self) -> None:
        # A no-op must be distinguishable from a real change, not None.
        class _Job:
            num_dml_affected_rows = None
            def result(self): return []
        class _Client:
            def query(self, sql, job_config=None): return _Job()
        self.assertEqual(ws.run_sql_dml(_Client(), "UPDATE x SET a=1"), 0)

    def test_rows_come_back_as_plain_dicts(self) -> None:
        class _Job:
            def result(self): return [{"a": 1}, {"a": 2}]
        class _Client:
            def query(self, sql, job_config=None): return _Job()
        self.assertEqual(ws.run_sql_rows(_Client(), "SELECT a FROM x"), [{"a": 1}, {"a": 2}])

    def test_statements_are_labelled_for_logging(self) -> None:
        self.assertEqual(ws._sql_label("  update  `p.d.t`  set a=1 "), "UPDATE `P.D.T`")
        self.assertEqual(ws._sql_label(""), "")


class DeferredReviewSaveTests(unittest.TestCase):
    """A record the user edited is kept even when it still fails validation:
    saved as user_reviewed and re-checked at enrichment, rather than bounced
    back for a value the system may not be able to confirm yet."""

    def test_the_columns_exist(self) -> None:
        from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

        columns = {f["name"] for f in TABLE_SCHEMAS["error_listings"]}
        self.assertTrue({"user_reviewed", "user_reviewed_at"} <= columns)

    def test_the_path_is_opt_in_and_keeps_the_users_input(self) -> None:
        import inspect

        source = inspect.getsource(ws.reprocess_rejected)
        # Opt-in only: a normal retry must still validate.
        assert 'str(data.get("accept_as_reviewed", "")).lower() in {"1", "true", "yes"}' in source
        # Their edited values are stored, not discarded in favour of the old row.
        assert "raw_record = @raw_record" in source
        assert "SET user_reviewed = TRUE" in source
        assert "attempt_count = COALESCE(attempt_count, 0) + 1" in source
        # Routed through the shared helper like every other mutation.
        assert 'label="reprocess:accept_as_reviewed"' in source

    def test_the_button_appears_only_after_a_retry_has_failed(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        html = (root / "ui" / "integrations.html").read_text()
        review_js = (root / "ui" / "js" / "review.js").read_text()
        # Hidden by default - offering it up front would invite skipping
        # validation that would have passed.
        assert 'id="acceptAsReviewedBtn" class="secondary hidden"' in html
        assert 'if (acceptBtn) acceptBtn.classList.remove("hidden");' in review_js
        # Reuses the normal submit path so the two cannot diverge.
        assert 'el("submitEditRecordBtn")?.click();' in review_js
        assert "accept_as_reviewed: window.__acceptAsReviewed === true," in review_js
        # The flag must never leak into the next retry.
        assert "window.__acceptAsReviewed = false;" in review_js


class MergeBrandsPreviewTests(_FakeBigQueryModuleMixin):
    """Combining brands is irreversible from the UI, so the confirm step needs
    real counts. Preview mode must COUNT and must never mutate."""

    def _run(self, client, **extra):
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "_ensure_businesses_table", lambda *a, **k: None), \
             patch.object(ws, "invalidate_cache", lambda *a, **k: None), \
             patch.object(ws, "_sync_gold_mirror_best_effort", lambda *a, **k: None):
            return ws.merge_brands({
                "target_business_id": "keep-1",
                "source_business_ids": ["dupe-1", "dupe-2"],
                **extra,
            })

    def test_preview_counts_rows_and_issues_no_mutation(self):
        client = FakeClient(query_results={
            "ds.listings`": [{"row_count": 1240}],
            "ds.workflow_templates`": [{"row_count": 3}],
            "ds.error_listings`": [{"row_count": 38}],
        })
        result = self._run(client, preview=True)

        self.assertTrue(result["preview"])
        self.assertEqual(result["listings_moved"], 1240)
        self.assertEqual(result["templates_moved"], 3)
        self.assertEqual(result["review_rows_moved"], 38)
        self.assertEqual(result["moved_total"], 1281)
        self.assertTrue(result["counts_complete"])
        # Nothing may be written, and the source brands must stay live.
        statements = " ".join(client.queries).upper()
        self.assertNotIn("UPDATE ", statements)
        self.assertNotIn("DELETE ", statements)
        self.assertNotIn("IS_DELETED = TRUE", statements)
        self.assertEqual(len(client.queries), 3)

    def test_unreadable_table_reports_unknown_not_zero(self):
        # Reporting a table we could not read as 0 would let the dialog claim
        # "nothing will move" about data that is actually there.
        class HalfBrokenClient(FakeClient):
            def query(self, sql, job_config=None):
                if "ds.error_listings`" in sql:
                    raise RuntimeError("table unavailable")
                return super().query(sql, job_config)

        client = HalfBrokenClient(query_results={
            "ds.listings`": [{"row_count": 5}],
            "ds.workflow_templates`": [{"row_count": 0}],
        })
        result = self._run(client, preview=True)

        self.assertIsNone(result["review_rows_moved"])
        self.assertFalse(result["counts_complete"])
        self.assertEqual(result["listings_moved"], 5)

    def test_without_preview_the_merge_still_mutates(self):
        client = FakeClient(affected_by_query={
            "ds.listings`": 7, "ds.workflow_templates`": 1, "ds.error_listings`": 2,
        })
        result = self._run(client)

        self.assertNotIn("preview", result)
        statements = " ".join(client.queries).upper()
        self.assertIn("UPDATE ", statements)
        self.assertIn("IS_DELETED = TRUE", statements)


class LocationContactEnrichmentTests(unittest.TestCase):
    """Store-level OSM lookup. The whole value of this is that it answers for
    ONE store, so the name check and the tag check both have to hold."""

    def _payload(self, elements):
        return {"elements": elements}

    def _lookup(self, elements, **kwargs):
        from whitespace_tool import brand_enrichment
        with patch.object(brand_enrichment, "_get_json", return_value=self._payload(elements)):
            return brand_enrichment.enrich_location_contact(
                kwargs.pop("name", "Domino's Pizza #4412"),
                kwargs.pop("lat", 30.2672), kwargs.pop("lon", -97.7431), **kwargs)

    def test_returns_contact_tags_from_the_matching_poi(self):
        result = self._lookup([{"tags": {
            "name": "Dominos Pizza",
            "phone": "+1 512-555-1234",
            "contact:website": "dominos.com",
            "contact:email": "store4412@dominos.com",
        }}])
        self.assertEqual(result["phone_number"], "+15125551234")
        self.assertEqual(result["website_url"], "https://dominos.com")
        self.assertEqual(result["email"], "store4412@dominos.com")
        self.assertEqual(result["website_url_source"], "openstreetmap")
        self.assertEqual(result["matched_name"], "Dominos Pizza")

    def test_an_unrelated_neighbour_never_donates_its_contact_details(self):
        # The whole point of the name check: a POI 40m away is not this store.
        result = self._lookup([{"tags": {"name": "Blue Owl Coffee", "phone": "+1 512-555-9999"}}])
        self.assertEqual(result, {})

    def test_name_matched_poi_with_no_contact_tags_is_not_an_answer(self):
        result = self._lookup([{"tags": {"name": "Dominos Pizza", "cuisine": "pizza"}}])
        self.assertEqual(result, {})

    def test_out_of_range_or_missing_coordinates_do_not_call_out(self):
        from whitespace_tool import brand_enrichment
        with patch.object(brand_enrichment, "_get_json") as fetch:
            self.assertEqual(brand_enrichment.enrich_location_contact("Store", None, None), {})
            self.assertEqual(brand_enrichment.enrich_location_contact("Store", 91.0, 0.0), {})
            self.assertEqual(brand_enrichment.enrich_location_contact("", 30.0, -97.0), {})
        fetch.assert_not_called()

    def test_an_unreachable_overpass_returns_nothing_rather_than_raising(self):
        import urllib.error
        from whitespace_tool import brand_enrichment
        with patch.object(brand_enrichment, "_get_json", side_effect=urllib.error.URLError("down")):
            self.assertEqual(brand_enrichment.enrich_location_contact("Store", 30.0, -97.0), {})

    def test_radius_is_clamped_so_a_caller_cannot_widen_it_to_the_whole_city(self):
        from whitespace_tool import brand_enrichment
        seen = {}

        def capture(url):
            seen["url"] = url
            return {"elements": []}

        with patch.object(brand_enrichment, "_get_json", side_effect=capture):
            brand_enrichment.enrich_location_contact("Store", 30.0, -97.0, radius_m=50000)
        self.assertIn("around%3A500%2C", seen["url"])


class IdleLocationEnrichmentPassTests(_FakeBigQueryModuleMixin):
    """The background pass must only ever fill blanks, and must re-assert that
    in SQL - the row was read a moment earlier, so a concurrent user edit has
    to win."""

    def setUp(self):
        super().setUp()
        ws._LOCATION_ENRICH_ATTEMPTED.clear()
        self.addCleanup(ws._LOCATION_ENRICH_ATTEMPTED.clear)

    def _run(self, client, resolved):
        from whitespace_tool import brand_enrichment
        with patch.object(ws, "_warehouse_settings", return_value=("proj", "ds", None)), \
             patch.object(ws, "_bigquery_client", return_value=client), \
             patch.object(ws, "invalidate_cache", lambda *a, **k: None), \
             patch.object(ws, "sleep", lambda *a, **k: None), \
             patch.object(brand_enrichment, "enrich_location_contact", return_value=resolved):
            return ws._idle_location_enrichment_pass()

    def _client(self, rows):
        return FakeClient(query_results={"FROM `proj.ds.listings`": rows})

    def test_fills_only_the_blank_columns_and_guards_them_again_in_sql(self):
        client = self._client([{
            "listing_id": "L1", "name": "Dominos Pizza", "latitude": 30.0, "longitude": -97.0,
            "phone_number": "", "website_url": "https://already-set.example", "email": None,
        }])
        result = self._run(client, {
            "phone_number": "+15125551234",
            "website_url": "https://osm-would-have-said-this.example",
            "email": "store@example.com",
        })

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["fields_filled"], 2)
        update = next(q for q in client.queries if q.strip().upper().startswith("UPDATE"))
        self.assertIn("phone_number = @phone_number", update)
        self.assertIn("email = @email", update)
        # website_url already had a value, so it is neither set nor guarded.
        self.assertNotIn("website_url = @website_url", update)
        self.assertIn("(phone_number IS NULL OR phone_number = '')", update)
        self.assertIn("(email IS NULL OR email = '')", update)

    def test_a_listing_osm_does_not_know_is_left_blank_not_written(self):
        client = self._client([{
            "listing_id": "L1", "name": "Unknown Store", "latitude": 30.0, "longitude": -97.0,
            "phone_number": None, "website_url": None, "email": None,
        }])
        result = self._run(client, {})
        self.assertEqual(result["updated"], 0)
        self.assertFalse([q for q in client.queries if q.strip().upper().startswith("UPDATE")])

    def test_a_listing_is_attempted_once_so_the_loop_moves_on(self):
        rows = [{
            "listing_id": "L1", "name": "Unknown Store", "latitude": 30.0, "longitude": -97.0,
            "phone_number": None, "website_url": None, "email": None,
        }]
        self.assertEqual(self._run(self._client(rows), {})["attempted"], 1)
        self.assertEqual(self._run(self._client(rows), {})["attempted"], 0)


class BackgroundCacheInvalidationTests(unittest.TestCase):
    """User-reported: "is clear cache happening always... more frequent 0 data".

    It was. invalidate_cache() is a blanket DELETE of every cached payload
    except reporting_quality:*, and the background loops called it on every
    pass - auto-repair fixes ten rows a cycle, the enrichment passes fill a
    field at a time. Measured on the live mirror: query_cache held ONLY the
    exempt reporting_quality:* keys; every reporting_summary:* entry was gone,
    so each dashboard load paid a full recompute.
    """

    def setUp(self):
        ws._LAST_BACKGROUND_INVALIDATION_AT = 0.0
        self.addCleanup(setattr, ws, "_LAST_BACKGROUND_INVALIDATION_AT", 0.0)

    def test_repeated_background_passes_clear_the_cache_at_most_once_per_window(self):
        calls = []
        clock = [1000.0]
        with patch.object(ws, "invalidate_cache", lambda *a, **k: calls.append(1)), \
             patch.object(ws, "wall_clock_time", lambda: clock[0]):
            self.assertTrue(ws._invalidate_cache_background())
            # Five more passes inside the window must all be skipped.
            for _ in range(5):
                self.assertFalse(ws._invalidate_cache_background())
            self.assertEqual(len(calls), 1)
            # Past the window, one more is allowed through.
            clock[0] += ws.BACKGROUND_INVALIDATION_MIN_INTERVAL_SECONDS + 1
            self.assertTrue(ws._invalidate_cache_background())
            self.assertEqual(len(calls), 2)

    def test_user_actions_still_clear_immediately(self):
        # A save or a brand merge has to be visible at once - only the
        # background loops are throttled.
        for function in (ws.merge_brands, ws.create_brand, ws.update_brand, ws.clear_saved_data):
            source = inspect.getsource(function)
            self.assertIn("invalidate_cache()", source, function.__name__)
            self.assertNotIn("_invalidate_cache_background()", source, function.__name__)

    def test_every_background_loop_uses_the_throttled_path(self):
        for function in (ws.auto_repair_error_batch, ws.start_auto_repair,
                         ws._idle_brand_enrichment_pass, ws._idle_location_enrichment_pass):
            source = inspect.getsource(function)
            if "invalidate_cache" not in source:
                continue
            self.assertIn("_invalidate_cache_background()", source, function.__name__)
            # No bare blanket call may survive alongside it.
            self.assertNotIn("\n        invalidate_cache()", source, function.__name__)
