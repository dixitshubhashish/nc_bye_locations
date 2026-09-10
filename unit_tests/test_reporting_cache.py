from __future__ import annotations

import unittest
import inspect
import json
import re
import threading
from unittest.mock import patch

import whitespace_tool.workflow_server as workflow_server


class _RecordedThreads:
    """Stand-in for workflow_server's `threading` module.

    _cumulative_fix_states() kicks off a BigQuery recount in a daemon thread
    on every call. That recount is not what these tests are about, and letting
    it run would open a real warehouse connection from a thread that outlives
    the patch context - so threads are recorded by name and never started.
    """

    def __init__(self) -> None:
        self.started: list[str] = []
        # workflow_server also reads threading.Lock/Event off this module.
        self.Lock = threading.Lock
        self.Event = threading.Event

    def Thread(self, *args, target=None, name="", **kwargs):
        recorder = self

        class _Fake:
            daemon = True

            def start(self) -> None:
                recorder.started.append(name)

        return _Fake()


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

        self.assertIn("reporting_summary:v4", reporting_source)
        self.assertIn("vw_reporting_filter_options", reporting_source)
        self.assertIn("FROM `{bronze_ref}.businesses`", gold_source)
        self.assertIn("UNION DISTINCT", gold_source)

    def test_state_population_is_deduped_before_summing(self) -> None:
        # vw_zip_brand_activity's grain is (zip_code, brand_name): a zip with
        # N brands present carries its population in N rows. Both places that
        # sum population from it must dedupe to one row per zip first, or a
        # zip with several brands gets its population counted once per brand.
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("SELECT DISTINCT zip_code, state_code, population, median_household_income FROM {zip_ref}", source)
        self.assertIn("SELECT DISTINCT zip_code, state_code, state_name, city_name, population", source)
        # The old, unguarded "SUM(population) ... FROM {zip_ref}" pattern
        # (no DISTINCT dedup beforehand) must not reappear.
        self.assertNotRegex(source, r"SUM\(population\)\s*(AS \w+\s*)?\n\s*FROM \{zip_ref\}")

    def test_total_brands_falls_back_to_catalog_only_when_filtered_count_is_zero(self) -> None:
        source = inspect.getsource(workflow_server.reporting_summary)
        self.assertIn("COALESCE(NULLIF(COUNT(DISTINCT brand), 0), (SELECT COUNT(DISTINCT brand_name) FROM {gold_brand_ref}))", source)

    def test_map_query_selects_country_for_non_us_marker_coloring(self) -> None:
        # 2026-09-10: non-US marker coloring (ui/js/reporting.js) colors a
        # marker state-primary/country-secondary, which only works if the
        # BigQuery-path map_query actually selects `country` in the first
        # place - the SQLite-mirror path is covered separately in
        # test_gold_mirror.py's test_map_records_include_country_for_non_us_marker_coloring.
        source = inspect.getsource(workflow_server.reporting_summary)
        map_query_start = source.index("map_query = f\"\"\"")
        map_query_select = source[map_query_start:source.index("FROM {gold_location_ref}", map_query_start)]
        self.assertIn("country", map_query_select)

    def test_data_quality_respects_selected_brands_filter(self) -> None:
        source = inspect.getsource(workflow_server.reporting_summary)
        match = re.search(r'data_quality_query = f"""(.*?)"""', source, re.DOTALL)
        self.assertIsNotNone(match, "data_quality_query definition not found")
        data_quality_block = match.group(1)
        self.assertIn("listings_enriched", data_quality_block)
        self.assertIn("IN UNNEST(@selected_brands)", data_quality_block)

    def test_cold_quality_cache_warms_in_background_instead_of_blocking(self) -> None:
        # Live-verified regression: a genuinely cold cache blocked the
        # request for 30+ seconds against a 21k-row review queue (full
        # errors/raw_record JSON fetch + Python aggregation). Cold loads
        # must hand back an immediate placeholder and warm the real result
        # in a background thread instead - explicit refreshes are the one
        # exception, since those already show their own progress UI and are
        # expected to wait.
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        cold_branch = source.split("if not cached_quality and not _skip_cache and not force_refresh:", 1)[1].split("\n    project_id, dataset_id, credentials_json = _warehouse_settings()", 1)[0]
        self.assertIn('"quality_cache": "warming"', cold_branch)
        self.assertIn('threading.Thread(target=warm_cold_quality, name="quality-mirror-cold-warm", daemon=True).start()', cold_branch)
        self.assertIn('reporting_quality_summary(params, _skip_cache=True)', cold_branch)
        # The placeholder must be an honest empty shape, not fabricated data.
        self.assertIn('"reasons": [], "brands": [], "states": [], "cities": [], "countries": [], "history": []', cold_branch)

    def test_explicit_refresh_is_excluded_from_the_cold_cache_placeholder(self) -> None:
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        self.assertIn("if not cached_quality and not _skip_cache and not force_refresh:", source)

    def test_a_stale_cached_payload_cannot_pin_the_fix_state_cards_to_dashes(self) -> None:
        """Live-reported: "critical bug - no data showing on chart on left side".

        The five fix-state cards ("Fixed by AI", "Fixed from AI suggestion",
        "Fixed manually", "AI suggestion awaiting review", "Awaiting manual
        review") plus "Ever invalid (all time)" all rendered as "-" while the
        donut and brand table beside them showed real data.

        fix_states is a GLOBAL, mirror-backed figure - it counts every listing
        that was ever invalid, across all brands - and does NOT vary with the
        filter params that key this cache. Baking it into the per-filter
        cached payload meant any filter combination whose payload happened to
        be built while the fix-state mirror was still cold (the first page
        load after a restart, say) cached {"computed": false} and then served
        that FOREVER. The counts were correct in the mirror and correct for an
        unfiltered request - wrong only on the specific cached view the user
        was sitting on, which is why it looked like a mapping failure.

        So: a cache HIT must re-read fix_states on the way out.
        """
        params = {"status": ["all"]}
        cache_key = f"reporting_quality:v2:{json.dumps(params, sort_keys=True)}"
        # The poisoned entry, exactly as the cold mirror wrote it.
        cached = {
            "scope": "invalid_listings",
            "metrics": {"invalid_listings": 50, "needs_manual_review": 50},
            "reasons": [{"reason": "missing_zip", "count": 50}],
            "brands": [{"brand": "Acme", "count": 50}],
            "states": [], "cities": [], "history": [],
            "fix_states": {"computed": False, "refreshing": True},
        }
        # ...and what the mirror actually holds by the time the user looks.
        mirror = {
            "ai_fixed": 172, "ai_suggested_fixed": 7, "manual_fixed": 160,
            "ai_suggested_pending": 21, "manual_pending": 109,
            "total_ever_invalid": 469, "updated_at": "2026-09-10 00:00:00",
        }
        threads = _RecordedThreads()

        # Pre-claim the key so the cache-hit path does not also schedule the
        # quality recount - the fix-state thread is then the only one, which
        # makes "_cumulative_fix_states() really ran" unambiguous.
        with workflow_server._QUALITY_REFRESH_LOCK:
            workflow_server._QUALITY_REFRESH_KEYS.add(cache_key)
        try:
            with patch.object(workflow_server, "get_cached_query", return_value=cached), \
                    patch.object(workflow_server, "get_fix_state_counts", return_value=mirror), \
                    patch.object(workflow_server, "threading", threads), \
                    patch.object(workflow_server, "_warehouse_settings",
                                 side_effect=AssertionError("a cache hit must not open the warehouse")):
                result = workflow_server.reporting_quality_summary(params)
        finally:
            with workflow_server._QUALITY_REFRESH_LOCK:
                workflow_server._QUALITY_REFRESH_KEYS.discard(cache_key)

        # It really was the stale cached entry that got served - otherwise
        # this test would be proving nothing about the cache path.
        self.assertEqual(result["quality_cache"], "sqlite")
        self.assertEqual(result["metrics"]["invalid_listings"], 50)
        # ...but the fix states came from the CURRENT mirror, not the stub.
        self.assertTrue(
            result["fix_states"]["computed"],
            "a stale cached payload still pins the fix-state cards to '-'",
        )
        self.assertEqual(result["fix_states"]["ai_fixed"], 172)
        self.assertEqual(result["fix_states"]["manual_fixed"], 160)
        self.assertEqual(result["fix_states"]["total_ever_invalid"], 469)
        # Every card the UI reads has a real number behind it.
        for key in workflow_server.FIX_STATE_KEYS:
            self.assertEqual(result["fix_states"][key], mirror[key], key)
        # And the recount was still scheduled, so the mirror keeps moving.
        self.assertIn("fix-state-refresh", threads.started)

    def test_the_cold_warming_placeholder_still_carries_real_fix_state_counts(self) -> None:
        # This replaces an earlier assertion that the warming placeholder must
        # carry NO fix_states at all. That rule was written to stop the
        # placeholder being mistaken for a finished answer - a good instinct,
        # but aimed at the wrong field.
        #
        # fix_states is not part of what this placeholder is standing in for.
        # It counts every listing that was ever invalid, across all brands,
        # and is read from the SQLite mirror; it does not depend on the
        # per-filter aggregation being computed in the background. Withholding
        # it was the last remaining path that could hand the UI a payload with
        # no fix_states, which renders the five cards as "-" next to a donut
        # showing real data - the exact bug reported.
        #
        # "quality_cache": "warming" is still what tells the UI the FILTERED
        # numbers are not final, so nothing is lost by including counts that
        # were never filtered in the first place.
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        cold_branch = source.split("if not cached_quality and not _skip_cache and not force_refresh:", 1)[1].split(
            "\n    project_id, dataset_id, credentials_json = _warehouse_settings()", 1)[0]
        self.assertIn('"quality_cache": "warming"', cold_branch)
        # The real mirror read, not a {"computed": false} stub.
        self.assertIn("_cumulative_fix_states()", cold_branch)
        self.assertNotIn('"computed": False', cold_branch)

    def test_coverage_query_only_references_columns_that_exist_on_listings(self) -> None:
        # Live-verified bug: the coverage query selected event_id,
        # coordinate_source, coordinate_confidence and state - none of which
        # are columns on `listings` - so BigQuery raised "Unrecognized name:
        # event_id" on every run, the broad except swallowed it, and
        # coverage_metrics stayed all-zero. That is why ZIP/coordinate
        # completeness, duplicate rate, stale records and the overall DQ
        # score all read 0 no matter what the real data said. Same class of
        # bug as the timeseries brand_name/qf.business_id regressions.
        from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

        source = inspect.getsource(workflow_server.reporting_quality_summary)
        match = re.search(r'coverage_query = f"""(.*?)"""', source, re.DOTALL)
        self.assertIsNotNone(match, "coverage_query definition not found")
        base_select = match.group(1).split("FROM `{project_id}.{dataset_id}.listings`", 1)[0]
        # Strip SQL comments first - the explanatory comment above this
        # SELECT names the very columns being asserted absent.
        base_select = "\n".join(
            line for line in base_select.split("\n") if not line.strip().startswith("--")
        )

        listing_columns = {field["name"] for field in TABLE_SCHEMAS["listings"]}
        for missing in ("event_id", "coordinate_source", "coordinate_confidence"):
            self.assertNotIn(missing, listing_columns, f"{missing} unexpectedly exists now - revisit this test")
            self.assertNotIn(missing, base_select, f"coverage query still selects nonexistent column {missing}")
        # `state` is state_code on this table.
        self.assertIn("state_code", base_select)
        self.assertNotRegex(base_select, r"(?<![_a-z])state(?![_a-z])")
        # The replacements it uses instead must be real columns.
        for present in ("ingestion_id", "enriched_at", "content_hash"):
            self.assertIn(present, listing_columns)
            self.assertIn(present, base_select)

    def test_clear_paths_resync_the_mirror_so_reporting_drops_cleared_rows(self) -> None:
        # Live-reported: after clearing saved/sample data, reporting still
        # showed the cleared rows. Both clear paths only called
        # invalidate_cache() + refresh_error_count() - they never rebuilt
        # gold or re-synced the SQLite mirror, and reporting reads the
        # mirror before BigQuery. They must also clear the quality cache,
        # which invalidate_cache() now deliberately spares.
        for fn in (workflow_server.clear_saved_data, workflow_server.clear_sample_dataset):
            source = inspect.getsource(fn)
            self.assertIn("invalidate_quality_cache()", source, fn.__name__)
            self.assertIn("_rebuild_gold_and_mirror(force_mirror=True)", source, fn.__name__)
            self.assertIn("_invoke_silver_layer(low_priority=True)", source, fn.__name__)
            # RULE (explicit): no metric anywhere in the app may read stale
            # after a clear. The AI/manual fix counters are a persisted
            # SQLite tally rather than a derived read, so re-mirroring alone
            # does not correct them - they kept displaying fixes for rows
            # that had just been deleted until this forced recount.
            self.assertIn("_schedule_quality_fix_metrics_refresh(force=True)", source, fn.__name__)

    def test_forced_mirror_sync_bypasses_the_empty_swap_guard(self) -> None:
        # sync_gold_mirror() refuses to swap an empty result over a
        # previously-populated mirror (that guard fixed a real data-wipe
        # bug). After a deliberate clear, though, empty IS the new truth -
        # without a bypass the guard keeps the just-deleted rows visible.
        source = inspect.getsource(workflow_server.sync_gold_mirror)
        self.assertIn("def sync_gold_mirror(force: bool = False)", source)
        # The guard now judges each collection's own collapse rather than
        # requiring both to be empty - see
        # test_a_collapse_in_either_collection_blocks_the_swap in
        # test_gold_mirror.py for why the old conjunction was unreachable.
        self.assertIn("if had_real_data and not force and collapsed:", source)
        rebuild = inspect.getsource(workflow_server._rebuild_gold_and_mirror)
        self.assertIn("sync_gold_mirror(force=force_mirror)", rebuild)

    def test_zip_regex_quantifiers_survive_fstring_interpolation(self) -> None:
        # The coverage query is an f-string, so a regex quantifier written
        # as {5} is consumed as a format field and the pattern silently
        # becomes '^[0-9]5$' - matching almost nothing, which is why ZIP
        # completeness read 0.0% while the same query run with escaped
        # braces reported 12,729/12,815. They must be written {{5}}/{{2,9}}.
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        match = re.search(r'coverage_query = f"""(.*?)"""', source, re.DOTALL)
        raw = match.group(1)
        self.assertIn(r"r'^[0-9]{{5}}$'", raw)
        self.assertIn(r"r'^[A-Z0-9][A-Z0-9 -]{{2,9}}$'", raw)
        # And the rendered SQL must carry the real quantifiers.
        rendered = raw.replace("{project_id}", "p").replace("{dataset_id}", "d").replace("{stale_after_days}", "90")
        rendered = rendered.replace("{{", "{").replace("}}", "}")
        self.assertIn(r"r'^[0-9]{5}$'", rendered)

    def test_rates_cannot_exceed_one_hundred_percent(self) -> None:
        # invalid rows (error_listings) and valid rows (listings) are two
        # different populations - dividing one by the other produced a
        # 280% "invalid record rate" and a bogus 100% valid rate that
        # inflated the overall DQ score. Denominator is everything ingested.
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        self.assertIn("ingested_total = tr + invalid_total", source)
        self.assertIn("valid_pct = pct(tr, ingested_total)", source)
        self.assertIn('round(total * 100 / (coverage_metrics["total_records"] + total), 2)', source)
        self.assertNotIn("if tr >= invalid_total else 100.0", source)

    def test_invalid_record_rate_does_not_fabricate_a_number_when_total_records_is_zero(self) -> None:
        # Live-reported regression: coverage_metrics["total_records"] can be
        # a real, legitimate 0 (its own BigQuery query returned nothing) -
        # the old `max(coverage_metrics.get("total_records", 1), 1)` denominator
        # trick never actually triggers its own "1" default because the key
        # is always present (just possibly 0), so 28,665 invalid records / 1
        # rendered as a nonsensical 2,866,500% instead of an honest 0.0.
        source = inspect.getsource(workflow_server.reporting_quality_summary)
        self.assertIn(
            '"invalid_record_rate_pct": round(total * 100 / (coverage_metrics["total_records"] + total), 2) if (coverage_metrics.get("total_records") or total) else 0.0,',
            source,
        )
        self.assertNotIn('max(coverage_metrics.get("total_records", 1), 1)', source)


if __name__ == "__main__":
    unittest.main()
