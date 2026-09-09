# Codex Project Handoff

## SESSION HANDOFF (2026-09-10) — READ THIS FIRST

Written for the next session (model change mid-work). Everything below was measured, not assumed; where a number appears, it came from a real run.

### Multi-agent sync
Use `AGENT_SYNC.md` as the live coordination board when Codex and Claude are both working. Read it before starting, claim one workstream there, update it after every meaningful change, and keep `docs/bug_tracker.md` + this file authoritative for bug status and durable handoff notes.

2026-09-10 user routing update: Claude should redirect UI fixes and bug-report/UI reproduction work to Codex. Claude/subagents should avoid claiming `ui/` files unless explicitly re-routed by the user; Codex owns UI follow-through and browser-style loading/reproduction notes.

2026-09-10 ownership routing update: Codex owns frontend/UI work. Claude owns backend/query/data work. Cross-surface tasks should be split in `AGENT_SYNC.md`: Codex handles frontend, asks Claude to take backend/query action there; Claude handles backend/query, asks Codex to take frontend action there. Avoid overlapping claimed files unless the user explicitly redirects.

2026-09-10 bug tracker rule: when a user follow-up is part of the same defect, enhance the existing `BUG-N` entry instead of creating a new bug. Create a new bug only for a distinct issue.

2026-09-10 UI workstream: Codex fixed BUG-91, the app-header brand lockup adjustment. "Competitive Whitespace Tool" now sits below the Birdeye logo instead of beside it. CSS-only change in `ui/integrations.html`; no server restart required.

2026-09-10 UI workstream: Codex fixed BUG-92. Trends Over Time and Historical Quality & Change Tracking now align their period controls beside the chart heading, share the same chart height, and default period-toggle chart features to `1H`.

2026-09-10 BUG-92 follow-up: Codex corrected the Location Intelligence panel order missed in the first pass. The order is now number cards, Location Map, Top States by Coverage, then Trends Over Time and Historical Quality.

2026-09-10 UI workstream: Codex fixed BUG-93. `/app` and Mapper refresh now start in the clean 40/60 pre-parse workflow, and old mapper drafts are not restored when the boot target is `mapperView`. Other tab refresh restore behavior is preserved. Clarified by BUG-95: left-rail utility panels remain visible below the 40/60 start surface.

2026-09-10 BUG-93 follow-up: Codex fixed the pre-parse boot paint order. `#mapperView` starts with `preparse-booting`, hiding left-rail utility panels only until `syncPreParseWorkspace()` has populated the 40/60 containers; then the utility panels show below them.

2026-09-10 BUG-93 follow-up: the boot-time full-width `#status` is now also hidden while `preparse-booting` is present, then shown only after it has been relocated into the 40/60 parser panel.

2026-09-10 UI workstream: Codex fixed BUG-94, the BUG-91 header sizing follow-up. Main top nav tabs are larger and right-side utility buttons are smaller, with a contract test preventing the later theme block from shrinking the nav again.

2026-09-10 UI workstream: Codex fixed BUG-95. Selecting a brand before parse now locks the required Brand Name mapping to that selected brand and disables the dropdown; save rows carry a frontend `__brand` value and `source_fields` includes it. Brand Entity Resolution, Job History, and Data Controls remain visible below the 40/60 start surface.

2026-09-10 UI workstream: Codex fixed BUG-96. Reporting hero and both inner-tab intro blurbs now use crisp, functionality-specific copy; reporting tabs cache-buster bumped to `quality-layout-v3`.

2026-09-10 BUG-96 follow-up: copy expanded to medium-length architecture/goal language. Reporting hero names the gold reporting layer and filtered views; Location Intelligence names validated records/map/open ZIPs/trends; Data Quality names rejected listings/quality mirrors/issues/fixes/freshness/repair.

2026-09-10 BUG-96 follow-up: Mapping and Template Library now have page-level intro descriptions too. Mapping copy sits above the 40/60 start workspace; Template Library copy describes saved source mappings, stored source fields, repairs, and repeat-load alignment.

2026-09-10 UI workstream: Codex fixed BUG-98. Selecting a brand before parse no longer auto-opens the edit-brand form, so clicking Parse cannot leak that form into the parse flow; explicit edit controls still open it.

2026-09-10 UI workstream: Codex fixed BUG-99. Source Input now renders as a cyan radio group with `Public URL` still selected by default; the hidden `sourceInputMode` select remains as the compatibility state holder for parser logic, drafts, and presets.

2026-09-10 UI workstream: Codex fixed BUG-100. The 40/60 pre-parse brand selectors split brand search and selected brand into left/right columns on wider panes, while the compact left-rail mapping view stays stacked.

### Start here
1. Read this section, then `docs/bug_tracker.md` (now one flat `BUG-N` list — see "Bug IDs" below), then the Rules section of this file.
2. `scripts/` holds the repeated command blocks (syntax check, server restart, login+cookie, test suite). Use them instead of retyping — that is why they exist.
3. Nothing is committed. The last commit is `4f6bd6c`; a large batch is outstanding in the working tree. **Do not commit or push unless the user explicitly asks.**

### Standing user rules (still in force)
- Do NOT commit or push unless explicitly asked.
- Do NOT fabricate numbers. Measure, then state. If unmeasured, say so.
- A message starting with `URGENT` jumps the queue.
- Keep **at most 2 background workers** running (explicit, 2026-09-10).
- Flag genuinely ambiguous product decisions rather than guessing. The user responds well to the AskUserQuestion popup and asked for it by name.
- `sample_locations` is an immutable source dataset; the reset/clear/drop helpers raise `PermissionError` if pointed at it.

### Bug IDs
`docs/bug_tracker.md` is now a single flat list of `BUG-N` entries with no category sections. Status is a FIELD, not a heading. Every old identifier (`B1`, `BB14`, `U2`, `DAT-04`, `RPT-08`, `FLT-02`, `INV-15`, `Q8`, `O8`, ...) is preserved as `Previously:` on its entry, so `grep -n "Previously: BB14" docs/bug_tracker.md` still resolves. Append new bugs as the next `BUG-N`.

### What changed this session (all uncommitted)

**Critical fixes**
- `create_brand()` was completely broken: `INSERT ... SELECT ... WHERE NOT EXISTS` with no `FROM`. BigQuery rejects a `WHERE` on a `SELECT` that has no `FROM`. Fixed with `FROM UNNEST([1])`. Verified live: create returns 200/`created:true`; a case-different name returns 200/`created:false` with the same `business_id`.
- Raw warehouse diagnostics were reaching the browser verbatim. `productSafeError` in `ui/js/common.js` is a word denylist and the message contained none of its terms. Fixed server-side at the single choke point `_json_response()` (`_sanitize_error_fields`), which matches the SHAPE of a diagnostic (`Job ID:`, `reason:`, `at [8:5]`, tracebacks, HTTP status prefixes, >300 chars) rather than particular nouns. Real text is logged with an 8-char reference shown to the user. Human messages like `Brand name is required` pass through untouched — verified.
- Data Quality fix-state cards showed `—` beside real data. `fix_states` is a GLOBAL mirror-backed figure but was frozen into the PER-FILTER cached payload, so any filter combination first built while the mirror was cold served `{"computed": false}` forever. Now re-read on every cache hit, and the cold "warming" placeholder carries it too. Verified by injecting the stale shape into the exact cache key the browser requests.
- Map showed one metro only. `map_query` ended in `LIMIT 1000` with **no ORDER BY**, so BigQuery returned an arbitrary block — 973 Massachusetts out of 42,869 listings across 59 states. Now round-robins by state (`ROW_NUMBER() OVER (PARTITION BY state ...)`, ordered by rank) and `MAP_RECORD_LIMIT = 5000`. Measured after: 5,000 records, 59 states, ~100 each, 1.8MB in 2.17s. `_mirror_map_records()` interleaves the same way.
- Leaflet layer groups were CROSS-NAMED: the store loop added to `gapMarkersLayerGroup`, the gap loop to `pinMarkersLayerGroup`, so `syncMapLayersByZoom()` did the inverse of its own comment. Renamed (`storeMarkersLayerGroup`) and rebuilt around a `state`→`city`→`listing` tier.

**Merge durability (user's "why did the merge come back")**
- New `_apply_brand_merges_to_bronze()`. `merge_brands()` only ever fixed bronze as it stood that second; a sample reload / re-save / re-parse re-inserted the original `business_id` and resurrected the retired brand, and the duplicate-brand rail reads bronze. Every silver build now reconciles bronze FIRST. Everything carrying `business_id` moves: `listings`, `error_listings`, `workflow_templates` (which hold mapped AND unmapped structure), and `field_catalogs` (slug-collision-safe; collisions archived, not deleted). Retired brands are re-soft-deleted.
- Verified by simulating the resurrection (pointed a listing back at a retired brand, marked the brand live) then reconciling: both counts returned to 0 and the listing's `business_id` was restored. Self-reversing, safe to re-run.
- `run_sql_rows` / `run_sql_dml` now accept and forward `low_priority` (they silently dropped it before; only `run_sql` honoured it), so background reconciliation issues BATCH-priority jobs.

**Performance (measured)**
- `list_templates()` had no mirror while `/api/brands` and ZIP search did: 2.36–3.63s per call, never faster, for a ~1.6KB payload, on the critical path of opening a Review row. Now cached: **2.55s cold → 4.8ms warm**. `invalidate_template_cache()` added and called on template save.
- `content_hash` backfill EXECUTED (user-approved): 27,704 of 42,802 rows rewritten in 367s, matching the dry-run prediction exactly.

**Features / behaviour changes**
- "Stop Enriching" is now an EASE-OFF, not a stop. `ease_enrichment()`; `/api/enrichment/stop` takes `{}` to ease and `{"resume": true}` to restore. Pacing measured: full speed 10 rows/5s pause, eased 2 rows/30s pause. Status reports `throttled` and `state: "eased"` so the UI drops the spinner entirely. `ENRICHMENT_STOP_REQUESTED` is untouched by easing — it remains the genuine abort for shutdown/destructive ops.
- Hourly trend granularity added (supersedes the earlier "day level only" instruction). `1H:(MINUTE,1 HOUR)`, `1D:(HOUR,1 DAY)`, then DAY/DAY/WEEK/MONTH. Cache key bumped to `v3`. Verified live: 1H→2 points, 1D→5 points, 1W/1M/1Q/1Y→1 point.
- Template Library excludes deleted and zero-listing templates, marking them `status: "inactive"` with a `listing_count`; `include_inactive=1` returns them. **Auto-repair MUST pass `include_inactive=True`** — error rows by definition have no live listings, so filtering there would silently stop repairing them.
- Native `<select>` popups are suppressed for searchable selects (`select.onmousedown` → `preventDefault()`, bails on `disabled`). A native popup's height CANNOT be capped by CSS, which is why 1,000 brands drew a full-screen list; the bounded typeahead panel opens instead. Focus shows nothing until typed (explicit instruction). `__create_new__` is pinned at the panel top — it is now the ONLY route to brand creation, so do not remove it.
- Reporting filter rail: `position: sticky` + `align-self: start`, **no internal scroll**. Note the CSS trap that caused the reported horizontal scrollbar: per spec, when one overflow axis is a scrolling value and the other is `visible`, the `visible` one computes to `auto` — so `overflow-y: auto` forced `overflow-x: auto`. `.select-suggestions` is `position: fixed` off the input rect so no ancestor can clip it.
- Demo sources renamed to declare FORMAT: `json_locations.py` (Domino's JSON demo), `get_json_api_locations.py` (Little Caesars GET JSON API demo), `csv_locations.py` (Pizza Hut CSV demo + the type→module dispatcher). Legacy type strings kept as aliases. The Little Caesars preset in `mapper.js` now reads `source_url`/`query_params`/`headers` from `/api/predefined-templates` instead of hardcoded literals — it had drifted to a Manhattan viewbox at `limit=25` while the config was US-wide at 50.
- Measured facts worth keeping: Nominatim silently caps at 50 (limit=50, 200 and 1000 all return exactly 50 rows); Domino's JSON returns 7,342 records.

### OPEN — pick these up

> **FINAL UPDATE — stable stopping point, all agents idle, suite green.**
> This replaces the two prior "UPDATE" notes above it. Read this one; the
> earlier ones are kept only for the narrative of how we got here.

**Session-final state:**
- Zero background workers running. Full suite: **609 passed, 0 failed**
  (`./scripts/run-tests.sh`). `./scripts/check-syntax.sh`: all clean.
- Nothing committed. Last commit still `4f6bd6c`. Do not commit/push unless asked.
- Server IS currently running (restarted to pick up the map-scope change below);
  any previously-saved cookie jar is invalid — re-run `scripts/login.sh`.

**Item 1 (Review edit form) — DONE**, including the `updatedRaw`/`currentEditingMapperFields`
data-loss fix. See the mid-session update above for detail; not repeating it here.

**Item 2 (`template_id` backfill) — EXECUTED (2026-09-10, user go-ahead).**
`backfill_orphan_template_ids(dry_run=False)` run for real. Result matched the
dry run exactly: `templates_linked_existing: 2, templates_created: 0,
listings_updated: 5619`. Both orphan groups (`andrews_csv`, 5,204 rows;
`demo_pe_brand_osm_restaurants`, 415 rows) now carry a resolved `template_id`.
No new templates fabricated. Idempotent — safe to re-run, not part of the
silver-build reconciliation loop (unlike merges, doesn't resurface).

Spec detail retained below for reference.
- Function `backfill_orphan_template_ids(dry_run=True, sample_rows_per_pair=200)` added
  to `whitespace_tool/workflow_server.py` (after `rehash_listings_content_hash()`).
- Re-verified live counts: 5,619 orphans, exactly 2 groups.
- **Important finding that changes the outcome**: real, legitimate `workflow_templates`
  rows ALREADY EXIST for both orphan pairs (`andrews_csv` and
  `demo_pe_brand_osm_restaurants`), with zero listings currently pointing at either.
  So the dry run does NOT fabricate any placeholder — it links both orphan groups to
  their real existing templates. `templates_created: 0`, both `action: "link_existing_template"`.
- Dry-run output (verbatim from the worker's run):
  `{"templates_linked_existing": 2, "templates_created": 0, "listings_updated": 0}`
  with the two pairs and their target template ids listed in the function's own report.
- Also flagged: the 415-row group has NULL `ingestion_id`/`mapping_id` on every row and
  one shared `first_observed_at` — a bulk load that bypassed `save_mapper()`. Not unique
  to this group (the 5,204-row Andrews group has the same shape) — worth a separate look
  at whatever loaded them, but not blocking this backfill.
- **To execute for real: call `backfill_orphan_template_ids(dry_run=False)`.** It is
  idempotent (a linked/created template becomes "existing" on any re-run) and does not
  need to be part of the silver-build reconciliation loop (unlike merges, an orphan
  linked once does not resurface).

**Item 3 (map "load more / realtime") — DONE, backend applied by me, measured live.**
- Frontend zoom-trigger machinery (debounced scoped fetch, `map_scope=full` param,
  cache keyed by `state|filterQueryString`) was written by a worker in `ui/js/reporting.js`.
  `node --check` + `git diff --check` clean on that file.
- I applied the backend half myself (both workers were told never to touch
  `workflow_server.py` concurrently, to avoid a collision — this is why it was
  deferred rather than done by either worker directly):
  - New `SCOPED_MAP_RECORD_LIMIT = 20000` beside `MAP_RECORD_LIMIT = 5000`.
  - New `map_scope` request param; `map_scope_full = map_scope == "full" and (state or county or city or zip filter present)`.
  - Threaded through BOTH map-serving paths: the BigQuery `map_query` (skips the
    round-robin CTE when scoped, uses the higher ceiling) AND the SQLite mirror path
    (`_reporting_data_from_mirror` → `_mirror_map_records`, same skip-and-raise-ceiling
    logic) — the worker had correctly flagged that fixing only one path would leave the
    other silently capped at 5,000 for cache hits.
  - **Measured live, after a server restart**: national sample = 5,000 records spread
    ~100/state across 59 states (1.8MB, 2.07s). Scoped fetch `state=CA&map_scope=full`
    = **3,227 records, all California**, 1.3MB, 1.05s. Well under the 20,000 ceiling.
  - Real per-state counts WERE measured (worker's second report, after mine above was
    written): largest states are TX at 2,597 and CA at 2,592 — every state is well
    under both the 5,000 national cap and the 20,000 scoped ceiling. So the round-robin
    was never actually truncating any single state once filtered to it (with one state
    left, `PARTITION BY state` degrades to a no-op ordering) — the scoped path is a
    correctness/headroom improvement, not a fix for an observed truncation. If a state
    ever exceeds 20,000, the design already has a documented next step: a county-level
    pre-aggregation tier, same pattern as the existing state→city→listing zoom tiers.

**Genuinely still open, nobody has started these:**
1. Trend timestamps: all live listings share one date (`2026-09-09`), 5 distinct hours.
   User chose real hourly granularity over synthesising history — do NOT spread
   timestamps without asking again.
2. The 415-row "bulk load bypassed save_mapper()" write-path gap noted above — nobody
   has traced which code path produced rows with no `ingestion_id`/`mapping_id`.

**Fixed (2026-09-10): "This template has no stored source columns. Parse a source file
to remap it." — root cause was in bronze, not the message.** User asked (a) don't show
that message when there's genuinely no data, and (b) fix it at the bronze layer with
flags. Measured before: **461 of 461** `workflow_templates` rows had zero
`components.source_fields` — every single template in the warehouse. **456 of those**
are `is_sample_data = TRUE` and were created by the RULE R0 stub-creation `INSERT` in
`_load_sample_dataset_impl()` (`whitespace_tool/workflow_server.py`, ~line 2979) with
`components = TO_JSON(STRUCT(business_id AS brand))` — nothing else, ever. That message
was accurate (there really was no structure) but its advice was actively wrong for these:
they were bulk `INSERT...SELECT`'d straight into bronze and never parsed from a file, so
"parse a source file to remap it" describes an action that cannot apply to them.
- New `backfill_sample_template_source_structure(dry_run=True, batch_size=100)`,
  `whitespace_tool/workflow_server.py` right after `backfill_orphan_template_ids()`.
  For every template missing `source_fields`, derives the real column set from its own
  listings: `CONTENT_HASH_FIELDS` (`warehouse_bigquery.py`) columns holding a non-null
  value on any listing pointing at that template, plus any leftover `custom_fields` keys.
  Writes `components.source_fields`, `components.unmapped_fields`, and
  `components.structure_synthesized = True` (so nothing downstream mistakes this for a
  mapping someone actually configured). A template with literally zero listings gets
  `components.structure_unavailable = True` + empty `source_fields` instead of a guess.
- **Executed live (user go-ahead)**: `templates_missing_structure: 461,
  templates_synthesized: 460, templates_unavailable: 1`. Verified after: 460/461 templates
  now carry real `source_fields` (36 columns for the standard sample-brand templates, 7 for
  `andrews_csv`), 1 (`global_hotels_mixed_csv`, genuinely zero listings) carries
  `structure_unavailable: true`. Idempotent — a re-run only touches templates still
  missing `source_fields`.
- `list_templates()` (line 2343) already returns the full `components` blob verbatim to
  the frontend, and `ui/js/templates.js`'s `renderTemplateEditSourcePreview()` (line 286)
  already reads `components.source_fields` — so populating it there was sufficient to stop
  the message appearing for the 460 now-fixed templates; **no template list/get API change
  was needed**, only the bronze data.
- **Handed to Codex** (frontend, via `AGENT_SYNC.md`): the 1 genuinely-empty template now
  carries `components.structure_unavailable = True`. `templates.js`'s "no stored source
  columns... parse a source file" message should be conditioned on that flag — show it
  only when `structure_unavailable` is true (truthfully "no data was ever recorded for
  this template"), not as a generic empty-array fallback, since an empty array now means
  something specific rather than "nobody filled this in yet."
- **Root-cause path not yet closed**: the same stub-creation `INSERT` will produce another
  bare `{"brand": ...}` stub the next time a *new* orphan `template_id` shows up in a
  sample reload it hasn't seen before (unlikely with the current fixed sample set, but the
  code path itself is unchanged). Flagged, not fixed — the low-effort fix is to call
  `backfill_sample_template_source_structure()` once at the end of
  `_load_sample_dataset_impl()`'s ingestion branch; not done this pass to keep the change
  scoped to the reported bug, revisit if sample data is reloaded again with new brands.

**Fixed (2026-09-10): ZIP-in-state-column bug — state count read 59 instead of ~52.**
Root cause was in `build_silver_layer()`'s silver SQL (`whitespace_tool/workflow_server.py`,
the `_listings_staging` CTE, ~line 3547): the `normalized_state_code` `CASE` mapped full state
names to their 2-letter code, but its `ELSE` branch passed the raw `state_code` value through
UPPER/TRIM **unvalidated** — so a source row with a ZIP literally in its `state` column
(`23518`, `54136`, `77505`, `82070`, `97420`, `10509`, `22963`) or a garbage value like `"USA"`
sailed straight through as a "state." The outer `COALESCE(l.normalized_state_code,
NULLIF(UPPER(TRIM(l.state_code)), ''), cg.state_code, z.state_code)` compounded it: even if
`normalized_state_code` had been fixed to reject garbage, the second fallback term repeated the
same unfiltered raw value, so it would have won anyway ahead of the legitimate
city/ZIP-based lookups (`cg`/`z`).
- Fix 1: `ELSE` branch now checks the raw value against an explicit list of valid 2-letter
  US state/territory codes; anything else becomes `NULL` instead of passing through.
- Fix 2: dropped the redundant/unsafe `NULLIF(UPPER(TRIM(l.state_code)), '')` fallback from the
  outer `COALESCE` entirely — state_code now falls through to `cg.state_code` (worldwide-city
  match) or `z.state_code` (ZIP reference match) when the raw value is invalid, instead of
  reusing the same garbage a second time.
- Measured before: `mirror_reporting_locations.state_code` had 59 distinct values — 51 real
  (50 states + DC) + `USA` (12 rows) + 6 ZIP-shaped values (1 row each). Confirmed via direct
  query against `.cache/whitespace_cache.db`.
- Verified: `python3 -m py_compile whitespace_tool/workflow_server.py` clean;
  `unit_tests/test_silver_enrichment.py` (4 tests) updated for the new `COALESCE` shape and
  passing. **Not yet re-verified against a live rebuild** — this only takes effect on the next
  `build_silver_layer()` run (server restart, not taken per standing rule) and needs the
  affected rows' garbage `state_code` values corrected at the source/bronze level too if they're
  to stop reporting as invalid/missing-state rather than just stop polluting the state facet
  (silver's own validity gate already requires `state_code IS NOT NULL AND state_code != ''`,
  so these rows now correctly fall into `listings_invalid` with `missing_state` unless a
  city/ZIP match resolves them — that's the intended behavior, not a new gap).

**Fixed (2026-09-10): `/api/reporting/metric-export` now honours county/city/zip/reason/status.**
`reporting_metric_export()` (`whitespace_tool/workflow_server.py`) previously only threaded
brand/state/start_date/end_date into its BigQuery `query_params` — county/city/zip/reason/status
were parsed nowhere, so a DQ card download could return rows the DQ tab itself had filtered out.
- Extracted the DQ tab's own filter primitives out of `reporting_quality_summary()` into
  module-level helpers (right before it, ~line 6518): `_quality_decode_json()`,
  `_quality_raw_value()` (raw_record field lookup), `_quality_reasons_from_errors()`
  (errors → reason-label list). `reporting_quality_summary()` now calls these instead of its
  old locally-nested `decode`/`raw_value`/inline reason loop — same behavior, one definition.
- `reporting_metric_export()` now parses `county`/`city`/`zip`/`reason`/`status` as the same
  single-value, same-normalized params `reporting_quality_summary()` uses (county/city/reason
  lowercased, zip left as-is, status defaults `"all"`).
- Applied as a post-fetch Python filter (BigQuery has no indexed columns for these — the DQ
  tab itself filters the same way, in Python over the decoded `raw_record`/`errors` payload)
  on the two DQ-tab-backed query branches: `_FIX_EVENT_METRIC_TYPES` (fixed-with-ai /
  manually-fixed cards) and `_ERROR_METRIC_PREDICATES` (review-pending / invalid-listings
  cards) — both already select `raw_record`/`errors`. The coverage/location/ZIP/brand
  branches are untouched; those columns don't exist there.
- Status (`needs_review`/`ai_fixed`) is only applied on the `_ERROR_METRIC_PREDICATES` branch,
  which carries the `is_ai_enriched` flag (selected as `fixed_with_ai`) the DQ tab's status
  filter is defined over. The fix-events branch exports rows already resolved into an AI/manual
  bucket by definition of the metric itself and has no such column — left as a no-op there
  rather than inventing a mapping the DQ tab's own code doesn't have.
- `ui/reporting-tabs.js` line ~496: the DQ card download click handler's `filterIds` map was
  itself missing `county`/`city`/`zip` (`dqCountyFilter`/`dqCityFilter`/`dqZipFilter`) — it only
  forwarded brand/state/reason/status/dates, so those three were never even sent to the backend.
  Added, matching the existing `[key, id]` pairs already used for the on-page DQ filter apply
  (~line 953).
- Verified: `python3 -m py_compile whitespace_tool/workflow_server.py` and
  `node --check ui/reporting-tabs.js` both clean. No dedicated `metric_export` test file
  exists; ran `unit_tests/test_reporting_cache.py` + `unit_tests/test_bigquery_bootstrap.py`
  (both touch `reporting_quality_summary()`/BigQuery bootstrap) — 34 passed, 1 pre-existing
  failure (`test_prepare_zipcodes_skips_copy_when_existing_count_is_complete`, unrelated:
  fails identically on a clean stash of this change, in `prepare_zipcodes`/brand-merge code
  this change never touches). Not restarted — backend `.py` changed, needs a server restart
  to take effect.

### Landmines (things that cost real time this session)
- **pytest used to wipe the live SQLite mirror.** `unit_tests/conftest.py` sets `WHITESPACE_CACHE_DB` to a temp file before any test module imports. Never bypass it.
- **BigQuery cost is per STATEMENT, not per row** (measured: INSERT 2.36s, SELECT-by-key 1.59s, UPDATE 2.60s, DELETE 2.93s, SQLite mirror read 0.01s). Batching statements into one script helps; batching REST table deletes did NOT (9.4s vs 8.1s for parallel deletes).
- `_ensure_gold_reporting_views()` nests `build_silver_layer()`, so `_SILVER_BUILD_LOCK` must stay an `RLock` — a plain `Lock` deadlocks the whole suite.
- Build `SchemaField` objects lazily inside ensure-branches; constructing them up front breaks under other suites' faked bigquery module.
- Server-side sessions: restarting the app invalidates any curl cookie jar. Re-login after every restart.


## Product
Competitive Whitespace Tool: secure login, source mapping, validation/review, templates, enrichment, and US location reporting.

## Rules
- **SQL helper adoption is DROPPED (user, 2026-09-10).** Queries are working and fast; leave the remaining `client.query()` sites alone. The helpers stay where already adopted.
- **RULE R0 — `business_id` and `template_id` are FOREIGN KEYS on every listing.** Both are mandatory: the business the listing belongs to, and the template whose mapping produced it. The template must exist, not merely be named. Measured before this was enforced: of 28,119 live listings, **zero** had a `template_id` that resolved — 22,500 dangling (sample rows carrying the source's own ids, with no template ever created) and 5,619 missing entirely (every real user upload, because `__meta` was stamped only for sample rows). Save order is: **template first**, carrying the full structure, then listings referencing its id.
- **The templates table stores the WHOLE source structure at business level — mapped AND unmapped.** `components.source_fields` is every column the source had; `components.unmapped_fields` is the remainder with no typed home. A definition listing only the mapped columns is not the structure, and the template editor cannot offer to map what it does not know about.
- **A fix must be recorded as state, not applied as a one-off UPDATE.** Silver is `CREATE OR REPLACE`d from bronze on every build and a sample reload re-inserts source rows wholesale, so anything expressed only as a mutation is undone the next time either runs. Brand merges live in `brand_merges` (source -> target) and `_build_silver_layer_impl()` re-applies them on **every** build. Any future "fix" of the same shape (a dedupe, an override, a manual correction) must follow this pattern or it will come back.
- **Layer responsibilities:** bronze keeps what was actually ingested; silver is where corrections are applied; gold/mirror are derived and must never be corrected in place. Read for display from gold, write the fix so silver re-applies it.
- **Never call a brand a duplicate on name similarity alone.** Dice bigram overlap is dominated by a shared generic suffix - measured on the 1,000 sample brands (which draw names randomly from a shared list), similarity >=0.75 swept **315 brands into 125 "duplicate" groups** of which only **15** were genuinely the same name, while offering to irreversibly merge each. Require equal normalized keys, containment, or similarity **plus** a shared distinctive first token (`sameBrandRecord()`).
- **A table a query JOINs must be ensured where the query runs**, not only where something writes to it - a missing table fails the whole build.
- Active branch: `develop_new`.
- **Do not commit or push unless explicitly requested by the user.**
- **Do not restart the server unless the user explicitly asks** (standing instruction, 2026-09-09).
- **Always update `codex.md` first when making plans, completing changes, or noting new watch items.**
- `run.sh` is removed. Start with `python -m whitespace_tool.workflow_server` (or the CLI equivalent).
- Preserve unrelated user changes. When auditing behavior, trust active code and tests first, then use docs as context.

## Data Flow
Parse samples up to 50 records for discovery; save reloads and processes the complete source. Valid rows are stored and invalid rows remain in Review Error Listings. Background enrichment uses the worldwide city reference for fuzzy location matching and ZIP/coordinate validation.

BigQuery is authoritative. Persistent WAL SQLite mirrors ZIPs, brands, reporting rows, query results, and error counters for fast startup. ZIP readiness checks SQLite first, falls back to BigQuery, and repopulates the mirror. ZIP readiness does not block login; the app provides `Sync US ZIPs` for readiness and retry.

The active warehouse schema is defined in `whitespace_tool/warehouse_bigquery.py`; older SQL files may lag behind it. Current generated schemas include listing enrichment flags (`validated`, `enriched_at`, `max_enriched`), `country_code`, `error_listings.is_ai_enriched`, and `quality_fix_events`.

Local SQLite mirrors are defined in `whitespace_tool/sqlite_cache.py` and currently cover US ZIPs, worldwide cities, query payloads, field catalogs, gold reporting locations, ZIP-brand activity, businesses, review counts, ZIP readiness, auto-repair stats, enrichment queue, and quality listings.

The mirror is persistent at `.cache/whitespace_cache.db` and uses WAL mode. It is a performance layer, not the edit authority: user edits and warehouse writes remain authoritative upstream, while background refresh repopulates local reporting and readiness data. Reporting/map/table display limits are presentation limits only; source rows remain mirrored separately.

## UI Contracts
Root is the centered entry page; `/login` is the secure login page. Session failures and 401/403/404 responses return to login. Login may show ZIP loading status but remains usable. Brands and formats are independent. Demo URLs remain locked with Edit URL support. Required mapping fields appear first; auto-mapped fields use light-red verification. Source Preview is tabular with values; Data Model is a green-indicator two-pane view.

Action buttons use verb-ing labels and spinners. Warnings/errors have dismiss controls. Reporting filters include primary, `~`-joined competitors, geography, and demographics; the primary brand is excluded from competitors. Reporting uses responsive full-width layout, spaced tables, full state labels, and orange gap-ZIP markers.

## Reporting And Enrichment
Reporting metrics include states, ZIPs, active brands/stores/locations, distributions, comparisons, gaps, missing jurisdictions, data quality, and map data. Dashboard payloads may be display-limited for responsiveness; mirrors retain full source rows. Reporting refresh on load is silent; explicit refresh shows progress. Enrichment runs in background batches and refreshes reporting mirrors.

The reporting quality tab is intentionally separate from the whitespace/location tab. It is backed by `error_listings`, fix counters, and local quality mirrors, and should describe invalid listings, unresolved issues, impacted brands/geographies, and automatic/manual improvement counts without exposing backend terms in the UI.

Automatic review repair uses a persisted SQLite enrichment queue. It seeds a base set from current invalid records, claims a very small batch, moves unresolved rows into a failed set, and swaps failed back into base when the current set is exhausted. This is intended to prevent retrying the same first rows forever while keeping user-driven requests higher priority.

Worldwide geo enrichment now lives in `whitespace_tool/geo_enrichment.py`. It normalizes state/city text, detects inverted coordinates, uses cached US ZIP/city data for US hierarchy repair, uses cached worldwide cities for country-level repair, and can snap offshore/ocean coordinates to the nearest reference city when a reliable nearby point exists.

## Download Excel (Location Records Export)
The **Download Excel** button lives in the report hero section next to **Refresh Report**. It is only shown when a primary brand is selected. On click it calls `GET /api/reporting/export-excel?<current_query_params>` which directly queries BigQuery (no SQLite cache involved, may take seconds). The response is a 2-sheet `.xlsx`:
- **Sheet 1** — All records for the primary brand (sorted: state → city → address).
- **Sheet 2** — All records for selected competitor brands (sorted: brand → state → city → address).
Button states: idle (white) → loading/fetching (red, `⏳ Preparing Excel…`) → ready (green, `✅ Excel Download is Ready`) → auto-resets to idle after 4 s. Backend: `export_reporting_excel()` in `workflow_server.py` (line ~4204), HTTP handler at `GET /api/reporting/export-excel`.

## Verification
```bash
node --check ui/js/mapper.js
node --check ui/js/reporting.js
node --check ui/js/review.js
node --check ui/reporting-tabs.js
node --check ui/js/login.js
python3 -m py_compile whitespace_tool/workflow_server.py whitespace_tool/sqlite_cache.py
python3 -m py_compile whitespace_tool/geo_enrichment.py whitespace_tool/warehouse_bigquery.py
git diff --check
```

The short operational smoke checklist, fresh-upload fixture requirements, HTTP evidence, and presentation walkthrough are maintained in `docs/smoke_test_and_presentation.md`.

New test files added 2026-09-09 (run targeted, not the full suite, per project convention): `unit_tests/test_reporting_timeseries_cache.py`, `unit_tests/test_reprocess_fields_guard.py` (includes the brand-immutability regression tests).

## Current Audit
- In-progress Sep 8 2026 fixes: keep mapper left-rail enrichment/data controls visible in pre-parse 40/60 layout; replace backend-facing reset/reference-data copy with customer-safe language; harden manual review reprocess rows so malformed raw records surface useful field guidance; fix login error layout; make every fresh login land on default mapper 40/60 view; show reference-data loading as two product points; align US ZIP enrichment to a silver-layer union/dedupe reference sourced from canonical ZIPs plus US worldwide-city rows.
- Architecture: `workflow_server.py` owns routing, auth, parsing, BigQuery orchestration, sample load/clear, review repair, reporting, and background jobs. The UI is modularized (`mapper.js`, `review.js`, `templates.js`, `reporting.js`, `reporting-tabs.js`, `common.js`).
- Assessment fit: source adapters are separated, brand/source format independence exists, demo config is present, invalid rows are visible, provenance timestamps/content hashes exist, and reporting covers whitespace plus quality. Run-over-run diffing remains an explicit gap.
- Latest delta & memory optimizations:
  - Fixed Render web service OOM memory leak: replaced unbounded 50,000-row fetches in `auto_repair_error_batch()` with targeted BigQuery queries filtered directly by claimed `(event_id, row_number)` keys via `_fetch_rejected_by_keys()`.
  - Reused a single `bigquery.Client` lifecycle instance throughout the entire `start_auto_repair()` background worker, eliminating leaking gRPC transport sockets and thread pools.
  - Increased repair batch size to 10 records per iteration (cutting loop iterations and overhead by 10x).
  - Added dedicated memory leak and heap stability test suite (`unit_tests/test_memory_leak.py`) tracking `tracemalloc` allocations and single-client assertions (192 tests passing as of that point in the session — see the 2026-09-09 entries above for what's been added since; 248 collected as of the latest count, a portion not yet executed per standing instruction).
  - Refactored BigQuery silver SQL view to remove Cartesian $O(N \times M)$ `nearest_city` spatial subqueries, delegating coordinate repairs to indexed SQLite lookups in `whitespace_tool/geo_enrichment.py`.
- Latest UI fixes (session ~Sep 8 2026):
  - **Download Excel** upgraded from local CSV-of-sample-records to true 2-sheet BQ Excel export via `/api/reporting/export-excel`. Red→green state machine on the button.
  - Download Excel button relocated from inside the Location Records Sample section header to the report hero row (next to Refresh Report), now properly sized (`44px`, `14px`) to match the hero action buttons.
  - Location Records Sample section: removed clipping by adding `overflow: visible` on the section; simplified header to `<h2>` + `<p>` only.
  - **Quality tab loading state**: `dqStatus` and `dqBody` now start `hidden` — the tab shows nothing until the first fetch completes. Loading spinner only shown during fetch; body revealed only after data arrives. On force-refresh (button click), existing body stays visible while spinner overlays. No more "zero cards" flash or stale "Open this tab" message.
  - **Issue Type Breakdown donut chart** (`renderReasonsDonut`) added to `ui/reporting-tabs.js`. Pure SVG donut with 8-color palette, center count label, color-coded legend with record count + %. Grouped into "other_issues" for items beyond top-8. Shows "data looks clean" message when no issues. Replaces the old plain validation-issues table appended inside `dqSignals`. New dedicated `dqReasonsChart` section sits between Quality Signals and Improvement Opportunities.
- Watch item: mapping labels currently call listing `name` "Brand Name" in `config/field_registry.json` and `ui/js/mapper.js`, while the data model also has a separate business/brand. This can confuse users and should be reviewed before further mapper changes.
- Watch item: `config/predefined_brand_templates.json` still describes Little Caesars as JSON, while the interactive UI has GET JSON API demo behavior. Keep demo metadata and UI behavior aligned.
- Watch item: docs and generated Python schema are ahead of older SQL files. Treat `warehouse_bigquery.TABLE_SCHEMAS` as the live schema source unless the SQL files are regenerated.
- Watch item: quality metrics mix live review rows with fix counters. If a fixed row is soft-deleted from review, the visible denominator and fix counters must reconcile from `quality_fix_events`, not only the current active review population.
- **Session 2026-09-09 (extended, this file was not updated in-line — backfilled at end of session):**
  - **Reporting Data Quality tab**: added an append-only "Extended Coverage Metrics" grid (8 cards from `/api/reporting/summary`), a "Trends Over Time" multi-brand line chart with metric/period controls (new `GET /api/reporting/timeseries` endpoint, SQLite-cache-first/BQ-fallback like the rest of reporting), and a "Top States by Coverage" bar chart — all below the existing 12-card grid, none of the original sections touched. Removed the tab's own "Refresh Quality Metrics" button; the single hero "Refresh Report" button now drives both inner tabs via `window.reportingRefreshQuality`. Loading now fully hides `#dqBody` behind the spinner (both first load and refresh) without blocking the tab switcher.
  - **Reporting inner-tab nav semantics**: a genuine nav click into Reporting always resets to the first inner tab (Location Intelligence); a page refresh while already on Reporting preserves whichever inner tab was active (`switchView(viewId, isBootRestore)` new second param; boot call passes `true`).
  - **Reporting auto-refresh**: replaced the silent 60s background interval with a visible 5-minute (300s) countdown below the Refresh Report button (`#reportAutoRefreshCountdown`, `startReportingAutoRefreshCountdown()` in `reporting.js`), ticking every second, resetting to 300 on fire or on manual refresh. Removed the redundant "Refreshing report in the background..." status line (the button itself already shows "Refreshing Reports" + spinner).
  - **Fixed bug**: `'str' object has no attribute 'get'`/`.values` crash in the Review Error Listings retry-fix flow — root cause was a JS truthiness bug in `review.js` (`Object.keys()` on a string returns a truthy-length array), compounded by an unguarded `mapper.get("fields", {}).values()` in `reprocess_rejected()`. Both fixed; `validate_source_row()` (`data_validation/fields.py`) hardened defensively too.
  - **Brand immutability**: `reprocess_rejected()` now always re-resolves `mapper["brand"]` from the `businesses` table via `business_id`, ignoring any client-supplied brand string. The edit-record dialog's brand `<select>` (`review.js`) is now locked/read-only once a record already belongs to a known business — brand can only change by actually moving the record to a different `business_id`, not via this dialog.
  - **Only "brand" is mandatory** — relaxed at every layer per explicit instruction: `config/field_registry.json` (name/address/city/state/postal_code all `required:false` now), `REQUIRED_MAPPER_FIELDS` and `REQUIRED_LOCATION_VALUES` in `workflow_server.py` (both now empty), `normalize_location()` (`normalization.py`, only checks brand), and the BigQuery `listings` schema itself (`warehouse_bigquery.py` TABLE_SCHEMAS, those columns now NULLABLE) — `_ensure_listings_table()` gained a migration pass that relaxes REQUIRED→NULLABLE on an already-deployed table, not just new ones.
  - **Global postal code support**: `clean_zip()` (`normalization.py`) no longer strips letters from non-US postal codes (was silently destroying e.g. "SW1A 1AA" → "11") — now preserves+uppercases any alphanumeric code, and a 4-digit numeric code gets a leading zero restored (spreadsheet numeric formatting commonly drops it, e.g. MA "02134" → "2134"). The "invalid US ZIP code" validator (`data_validation/fields.py`) now only fires for a *purely numeric* code that isn't 5 digits, not for a legitimate non-US alphanumeric one. All ZIP write paths (worldwide_cities bronze query, `sqlite_cache.py` cache functions) now uppercase.
  - **50km reverse-geo snap cap**: `find_nearest_city_and_zip()`/`find_nearest_worldwide_city()` (`geo_enrichment.py`) now reject a "nearest" match beyond `MAX_SNAP_DISTANCE_KM = 50` instead of silently snapping to something far away (previously unbounded, including a population-only fallback with no geographic bound at all).
  - **cachedb action-timing logger**: every public `sqlite_cache.py` function is now wrapped (bulk `_timed_cache_action` wrap at module bottom, not per-`def`) — calls ≥200ms are logged and persisted to a new capped (500-row) `cachedb_action_log` table; `get_slow_actions()` reads them back.
  - **Fixed BLOCKER**: Template Library load was silently opening the Mapper's "Create Brand" modal underneath it. Root cause: `loadAppData()` (`common.js`) unconditionally calls `renderMappings()` → `updatePreParseBrandMode()` on every view's initial load regardless of active tab. Fixed by guarding `updatePreParseBrandMode()` to no-op when `#mapperView` is hidden.
  - **Fixed**: preset auto-mappings (Domino's/Pizza Hut/Global Hotels/Little Caesars demos in `mapper.js`) hardcode field names by convention (e.g. "Latitude") that don't always exist in the real parsed source, causing `Mapper validation failed: unknown source fields: ...` on save. New `pruneMappingSelectionsToParsedFields()` strips any preset mapping whose value isn't actually in the parsed `sourceFields` before it can be selected/saved.
  - **Fixed**: Save Listing Data progress ("Starting batch 1 of 1 (20%)") was frozen for the whole (usually single-batch) save with no live update. Now ticks every 400ms during each batch's in-flight fetch using an elapsed-vs-estimated-pace heuristic (same pattern as the sample-dataset loader), so multi-second saves show continuously climbing progress + ETA instead of a static number.
  - **Fixed**: header "Review Queue (N)" badge was queued behind `loadAppData()`'s slower chain (field registry, brands, template filters, a full template-library fetch) on boot even though the count endpoint itself is SQLite-cached and fast. Moved `refreshReviewCount()` to fire before/in-parallel with `loadAppData()` instead of after it.
  - Memory-leak audit + fixes: `enrichmentStatusTimer` (reporting.js) used to poll every 3s forever with no stop condition — now stops itself on a terminal state; `templatePageCache` (templates.js) now evicts expired entries on write instead of growing unbounded.
  - Sample dataset UX: Clear Sample Data moved directly below Load Sample Dataset in the header (same red styling); load button now shows amber/idle → yellow/loading → green/ready states; a confirmation `<dialog>` fires on successful load.
  - **State Distribution / Top Cities reporting tables enriched**: both now show Population, Median Income, Population-per-listing, and (when both a subject brand and at least one competitor are filtered) a Subject-vs-Competitor listing split. Backend: `top_states_query`/`top_cities_query` (live BigQuery path) and `_mirror_top_states()`/`_mirror_top_cities()` (SQLite mirror path, plus new `_mirror_state_median_income_by_state()` helper) both updated in lockstep — income is dedup'd-by-zip-then-averaged (a rate, not additive) the same way population is dedup'd-then-summed. The two tables moved from a side-by-side 2-column layout to stacked full-width (`#reportStateCityTables`) since a squeezed 2-column layout no longer fit 6+ columns per table; needed an ID-selector override since `.reporting-main-pane .report-columns` forces 2 columns via `!important`. **Watch item raised by the user**: this dual-path pattern (hand-written BigQuery SQL + a matching Python mirror function reproducing the same aggregation) exists for every reporting metric (totals, top_states, top_cities, brands, gaps, map_records, sample_records, data_quality) and risks drifting out of sync. A generalized declarative approach (one aggregate spec run against both BigQuery and mirror rows) was discussed and deliberately deferred — flagged as a real architecture improvement to do only with dedicated time, not mid-session.
  - **Table border/scroll consistency pass (app-wide)**: the global `table { overflow: hidden }` rule (and `.dq-table`'s copy in `reporting-tabs.js`) was silently *clipping* columns that overflowed a narrow viewport instead of letting the user scroll to see them. Fixed once, app-wide, via `div:has(> table) { overflow-x: auto; }` in `integrations.html` rather than patching every table's markup individually — covers `renderSimpleTable()` output (reporting.js) and the Data Quality tab's inline-template tables (reporting-tabs.js) in one shot.
  - **Second backlog batch closed out** (user said "do all open items without asking much"):
    - **`attempt_count` added** to `error_listings` (BigQuery, auto-migrated onto an already-deployed table via `push_to_bigquery()`'s existing missing-column patch) and threaded through `list_rejected()` (now selects it), `_row_error_listing()`, and `reprocess_rejected()` (`prior_attempt_count = max(rec.get("attempt_count") for rec in records) + 1`, passed to `save_mapper()` as `payload["attempt_count"]`, returned in the result). Drives a "Review Again (attempt N)" message and a per-row "Attempt N" badge in `review.js`'s rejected-records table.
    - **On-repeat-failure enricher suggestion**: `reprocess_rejected()`, when `mapped_rows == 0` after a resubmission, now calls `enrich_raw_listing_row()` (the same function the background auto-repair worker uses) on the row and returns whatever it changed as `result["suggested_fix"]`, surfaced in the dialog's error message instead of a bare generic string.
    - **New `detect_hierarchy_conflict()`** in `geo_enrichment.py`: given a ZIP + lat/lon, checks whether the ZIP's own canonical coordinates and the row's own coordinates agree (within `MAX_SNAP_DISTANCE_KM`); if not, returns both candidate resolutions ("zip_based" vs "coordinate_based", reusing `find_nearest_city_and_zip()`) rather than picking one. Wired into `reprocess_rejected()`'s repeat-failure path as `result["hierarchy_conflict"]`. Frontend: `renderHierarchyConflictPicker()` in `review.js` renders both options as buttons inside the edit form; picking one fills the fields and sets `suggestionAdopted = true` (user still clicks Retry to submit — same interaction pattern as the existing ZIP quick-fill, not auto-submit).
    - **Adopted suggestions now count as AI Fixed, not Manual Fixed**: both the ZIP quick-fill button and the hierarchy picker set `suggestionAdopted = true`; the `/api/reprocess` submit payload sends `is_ai_enriched: suggestionAdopted`, which `reprocess_rejected()` already used to route fix-count attribution (`fix_type="AI"` vs `"MANUAL"`, `_record_quality_fix_event()`) for the background worker — no new counting mechanism needed, just wiring the same existing flag from a second, human-initiated path.
    - **"Edit & Retry Fix" split into "💡 AI Suggested Fix" (blue) vs "🛠️ Manual Review" (amber)** in the rejected-records list, based on a list-view heuristic (city known, ZIP looks incomplete) approximating the edit dialog's own suggestion-availability check.
    - **Duplicate-detection messaging surfaced**: `save_mapper()` already computed `duplicate_listings_skipped` (via `_dedupe_listings_against_bronze()`) but never showed it. The save-completion message is now "`X inserted, Y duplicate(s) found, Z need(s) review`" instead of a flat "N records processed" that hid whether any were actually duplicates.
    - **Job History panel**: new SQLite-only (not BigQuery-authoritative — a UI convenience like `auto_repair_stats`) `save_events` table (`record_save_event()`/`get_recent_save_events()` in `sqlite_cache.py`, capped at `MAX_SAVE_EVENT_ROWS = 200`), written from `save_mapper()`'s return path, read via new `GET /api/jobs/recent`. New panel directly below "Data Enrichment" in `integrations.html` (`#jobHistoryList`), refreshed after every save and every reprocess.
    - **"Preparing your records..." spinner/ellipsis fix**: `setStatus()` writes plain `textContent`, so it could never actually show a spinner - bypassed for this one message to match the `busyMarkup()` convention (real spinner element, no trailing "...").
    - **Deliberately scoped down — explained, not silently skipped**: the user's fullest ask was "single row operations should be fast... save the newer input and set status to user_reviewed and then review later at enrichment" (i.e. skip synchronous validation entirely on single-row saves, defer it to the background pass). Investigation found the actual slowness is 4-6 sequential BigQuery round-trips per single-row reprocess (demographics lookup, dedupe check, push, cleanup update, recount) — the in-memory validation itself is cheap. Skipping validation and writing possibly-invalid rows straight into the authoritative `listings` table on the promise that enrichment "probably" fixes them later would break the existing invariant that reporting only ever sees validated rows, for a speed problem it wouldn't actually fix (BigQuery round-trips are the cost, not validation). Implemented instead: the safe, valuable subset above (`attempt_count` + Review Again + enricher suggestion) without touching the synchronous validation path. Revisit only with dedicated time to redesign the write path itself (e.g. genuinely async BigQuery writes), not as a quick patch.
    - Test files added this batch (written but **not executed**, per standing user instruction — "build test cases, but don't run, we will run them in bulk"): `unit_tests/test_review_ai_resolution.py` (attempt_count propagation, suggestion/hierarchy-conflict attachment), `unit_tests/test_job_history.py` (save_events status derivation, row cap), new `HierarchyConflictTests` class in `unit_tests/test_geo_enrichment.py`, plus more contract tests appended to `unit_tests/test_mapping_layout_contract.py`. **Run the full suite before trusting any of this is fully correct** — verified only by `py_compile`/`node --check` so far.
  - Test files from the prior batch (also still unexecuted): `unit_tests/test_reporting_state_city_metrics.py`, plus the table-scroll/stacked-layout tests already in `test_mapping_layout_contract.py`.
  - Explicit reminder from the user, still in force: **existing UI must not change except where a specific task calls for it.**
  - **Third backlog batch (2026-09-09, large multi-item message)** — user said "dont keep stop in backend other task while i read your message later," so this was worked through directly rather than paused on:
    - **CRITICAL FIX — gold mirror could silently wipe all reporting data to zero.** `sync_gold_mirror()` called `replace_gold_mirror()` unconditionally, even when a gold-view BigQuery query succeeded but returned zero rows (e.g. landing during `build_silver_layer()`'s `DROP TABLE IF EXISTS` → recreate window). That "successful empty result" got swapped in as the new mirror truth, zeroing out even warehouse-wide facts like the 50-state count until the next refresh happened to land cleanly. Fixed: `sync_gold_mirror()` now checks `get_mirror_status()` first - if the mirror previously held real data and the new query results are empty, the swap is skipped and a warning logged (`gold_mirror_sync_suspicious_empty_result`), leaving the last good mirror in place. This is very likely the "auto-refresh removed all data" / "50 states became 0" report.
    - **Sample load per-brand resilience**: `load_sample_dataset()`'s fallback per-brand loop (used when `sample_locations` bulk source is unavailable) had no exception handling - one brand's failure aborted the entire load. Now wrapped in try/except-continue, logging `sample_brand_load_failed` and moving on, matching "a few less records are fine" tolerance. Note: the *primary* sample-load path (when `sample_locations` exists, the common case) still bypasses `save_mapper()`/the mapper-template flow entirely via raw bulk `INSERT...SELECT` statements straight into bronze - the user's "go bronze-first via workflow template, not direct" ask is **not yet done for that primary path**, only for the fallback; flipping the primary path over is a larger change (would need the sample data reshaped into per-row mapper input) - flagged, not done.
    - **Mapping Coverage math bug fixed** ("105% - 21 of 20 columns mapped"): `updateOutput()`'s and the pre-save guard's coverage calculation counted *any* unique non-empty mapped value, including one left over in `mappingSelections` from before a re-parse shrank the real `sourceFields` list. Now both only count a mapped value if it's still actually present in `sourceFields` (`value && sourceFields.includes(value)`), so the numerator can never exceed the denominator. Investigated separately: brand is **not** part of the same `mappingSelections`/`mappingTargets` 1:1-collision system at all (it's a standalone `selectedBrand`/`brandSelect` picker) - "Template Components" text does not exist anywhere in the codebase, so the brand-lock ask needs its own design, not a fix to existing code.
    - **Reset Fields Mapping scoped back to Mapper tab only** — reverses an earlier deliberate decision (there was a regression test guarding "always visible everywhere"); `switchView()` now hides it outside `mapperView`. Restart Mapping was *not* part of this ask and stays visible everywhere, unchanged.
    - **Competitor brand checkboxes now default unselected** — reverses another earlier deliberate default ("picking a primary brand defaults to comparing against every other brand"); now starts empty, user opts in. The now-dead `competitorDefaultsAppliedForMainBrand` tracking variable was removed along with it.
    - **ZIP suggestion dedup**: the "Suggested ZIP + coordinates" quick-fill could show multiple near-identical buttons differing only by ZIP for the same city - now deduped to one (best-ranked) ZIP per (city, state) combination before rendering.
    - **`saveCompletionDialog` rebuilt on the standard theme**: previously built ad hoc in JS (`document.createElement("dialog")`, inline `style.cssText`, right-aligned OK button) - now a static `<dialog class="app-help-dialog">` in `integrations.html` (same theme as `appHelpDialog`/`sampleLoadedDialog`), with a centered OK button per explicit instruction that single-OK dialogs should center it. Audit of every other popup in the app found: native `alert()`/`confirm()` remain in several places (`mapper.js` field-remap/danger confirms, `reporting.js` Excel export failure, `review.js`), `dangerDialog`/master-delete dialogs use a separate `.danger-dialog` red-bordered pattern (intentionally distinct for destructive actions), and `pythonConnectorDialog`/`editRecordDialog` use a fourth `.connector-editor-dialog` full-editor chrome pattern - none of these were touched this round; only `saveCompletionDialog` was explicitly called out.
    - **"Preparing your records" status now clears once the save-completion dialog shows** — previously it stayed visible underneath the dialog with nothing to dismiss it.
    - **"Clearing sample dataset..."-style long status-bar text removed** where it duplicated the button's own busy state: `clearSampleDataset()`'s persistent loading bar, and the "Sample dataset already loaded, reporting is updating in the background." card shown after a redundant sample-load click (superseded by the `sampleLoadedDialog` popup, which is now the single acknowledgement for that action). `reporting.js`'s similar long-text bars ("Refreshing report...", "Preparing reporting data...", "Starting report refresh...") were identified by the investigation but **not yet touched** - flagged for a follow-up pass.
    - **Review Queue event_id field**: confirmed already cleared on every fresh page load (`el("reviewEventId").value = ""` added to the boot IIFE) with `autocomplete="off"` added defensively against browser form-restore - this closes the "stale UUID left in the search box" report.
    - **Random lat/lon placeholder confirmed already randomized** (`Math.random()`-based example values on every render) — not a static hardcoded string as first assumed; if a fixed realistic example is preferred instead, that's a separate small design call, not a bug fix.
    - **Investigated, not yet fixed** (documented so the next pass doesn't re-derive this): (a) recurring "unknown source fields: X" errors - root cause is likely `MAPPER_SAMPLE_ROWS = 50` (`source_adapters/common.py`) truncating field *discovery* itself to the first 50 rows, not a hardcoding bug like the earlier lat/lon case - a field absent from the first 50 rows never reaches `sourceFields` at all, independent of any preset function; (b) "50 stores on box vs 900 on map" - not a bug per se, `total_stores` (raw `SUM(location_count)`), `active_market_locations` (distinct ZIPs with a brand), and the map's per-record markers are three genuinely different metrics that happen to all sound like "stores"/"listings" - labels exist but could be clearer; (c) Edit Brand button race (`updatePresetBrandPanel()`/`syncBrandSelection()` runs before `loadBrands()`'s async fetch resolves, so the button can stay in "create" mode briefly) and a separate hard "not working" case (the click handler no-ops entirely when `activeCsvPresetConfig` is null, i.e. for any brand not tied to a CSV demo preset); (d) `/api/learning` re-queries BigQuery's `workflow_templates` live on every mapping-workspace open with no SQLite cache layer - the user wants this (and the `MAPPER_SAMPLE_ROWS` heuristic) persisted/cached; (e) demo XLS restaurant source reportedly returns `HTTP Error 400: Bad Request` - not yet reproduced/diagnosed; (f) an unsaved-changes navigation guard ("ask to save or continue" before leaving a parsed-but-unsaved mapping) does not exist yet; (g) out-of-US coordinate handling ("Coordinates fall outside valid US boundaries") should first try worldwide enrichment data and offer a "save as non-US" action counted under AI Fixed, rather than only rejecting - not yet built; (h) a possible header visual overlap between `.top-tabs` and `.header-data-actions` after the Clear-Sample-Data-under-Load-Sample-Dataset move - user will share a screenshot before this is diagnosed further; (i) filter-panel vertical spacing (Reporting sidebar) could be tightened (concentrated in `.filter-category`'s 16px margin + 12px padding dividers) but not yet touched; (j) README.md tone/readability pass for a non-technical end-customer audience requested but not yet done.

### 2026-09-10 — Server restarted; Review Queue count gap found; Template Library re-verified

**Server restarted** (`scripts/restart-server.sh --yes`) to pick up the ZIP-in-state-column
and metric-export fixes above — both Codex's and Claude's `AGENT_SYNC.md` slots were IDLE at
the time, which the user made an explicit exception for (see that file's Standing Rules).

**Review Queue shows "51", user asked why there are 20k+ records in the DB.** Investigated —
real, measured gap, but a product-scope question, not (only) a bug:
- `error_listings` (bronze) — **50-51 rows**. Backs the Review Queue donut/cards. These are
  rows that failed at PARSE/MAPPING time; they never reached bronze `listings`.
- `listings_invalid` (silver, rebuilt hourly or on `/api/silver/enrich`) — **13,745 rows**,
  measured via a live rebuild triggered this session (`rows: 48523, invalid_rows: 13745`).
  These DID reach bronze `listings` but fail the silver validity gate (`missing_state`,
  `missing_zip`, `unresolved_coordinates`, etc.). The ZIP-in-state-column fix will have
  INCREASED this count going forward (garbage state values that used to falsely pass now
  correctly fail).
- The Review Queue UI only ever surfaces the first population. **Flagging rather than
  deciding**: should it also surface/count `listings_invalid`? That's a real product call
  (two different failure modes — reject-at-import vs fail-at-enrichment — currently
  conflated by the user's expectation that "invalid" means "invalid").
- Secondary, smaller finding, not yet chased down: `listings_enriched` (48,523) is 79 rows
  LARGER than bronze `listings` (48,444) — likely JOIN fan-out from the `city_geos` fuzzy
  `EDIT_DISTANCE <= 2` match in the silver SQL producing >1 match for some rows.

**Template Library "templates with no listings" — re-verified, backend already correct.**
`list_templates()` (line 2343) already excludes zero-listing templates by default
(`COALESCE(u.listing_count,0) > 0`), and `ui/js/templates.js` never sends
`include_inactive`. Live check: `GET /api/templates?limit=500` → 462 templates, all with
`listing_count > 0`; the one known zero-listing template (`global_hotels_mixed_csv`) is
correctly absent. Not reproducible from a direct backend call as of this restart — handed
to Codex via `AGENT_SYNC.md` in case it's a stale-frontend-cache or different-fetch-path
issue, or was actually the (now backend-fixed) BUG-97 "no stored source columns" symptom
being read as "no listings."

**Mirror/chart refresh — mechanism confirmed working.** Manually triggered
`/api/reporting/refresh`; `mirror_meta.synced_at` advanced and `replace_gold_mirror`
completed in ~1 minute. A scheduled hourly background tick also exists
(`_start_silver_gold_scheduler()`) — by design, not continuous real-time. Whether the
reporting charts actually re-paint after a refresh completes is a frontend question, handed
to Codex.

## Remaining Gaps

### Twenty-fifth batch (2026-09-09) — the remaining open items, all closed

**BB1 - one column filling several fields.** `applyMappingSelection()` enforced
one-column-one-target for a dropdown pick; nothing enforced it for mappings
written in BULK - presets, restored drafts, templates. The shipped instance:
`setPizzaHutMappings()` mapped the column `address` to **both** `name` and
`address`. New `dedupeMappingSelections()` runs from `renderMappings()`, the
one choke point every path passes through, so it holds regardless of where a
mapping came from; required targets keep the column, later claims are cleared,
and the status line names what it dropped. A test scans every preset for the
pattern.

**U2 - no way back to the suggestions.** `renderMappings()` only suggests for
target keys ABSENT from `mappingSelections`, and a cleared field leaves an
empty-string key behind - so once everything was unmapped the suggestions
could never return. The Auto-map button deletes those entries and re-runs the
SAME pass via a one-shot `forceAutoMapOnce`; the test asserts it never calls
`suggestField()` itself, so the two can't drift.

**BB3 - demo preset locked the business.** `updatePresetBrandPanel()` disabled
`#brandSelect` once the preset's brand existed, so a demo source could only
be tested against that one business. Selector freed, brand form still locked.

**BB7 follow-up - the search box still did not appear.** `syncPreParseWorkspace()`
relocates nodes from a snapshot of the panel's children taken ONCE; an input
created after that snapshot is not in the list that moves back, so it was
stranded in the hidden panel. `attachSearchableSelect()` now re-homes itself
beside its select on every call. Matching was already case-insensitive; it
also normalises whitespace now.

Suite: **576 passed**. Every user-reported bug is closed.

### Twenty-fourth batch (2026-09-09) — merges made durable, and a false-duplicate rule that was destroying brands

**The duplicate-brand panel was offering to merge DISTINCT brands.** This is
why "I already merged this, why is it back": nothing was ever a duplicate.
Dice bigram overlap is dominated by a shared generic suffix, so "Thornton
Steakhouse" and "Clayton Steakhouse" scored over 0.75 on the strength of
"steakhouse". Measured against the 1,000 real sample brands (which draw names
randomly from a shared list, so near-collisions are guaranteed): the rule
swept **315 brands into 125 "duplicate" groups**, of which only **15** were
genuinely the same name - each offered under "This brand was added more than
once" with an irreversible Combine button. `sameBrandRecord()` now requires
equal normalized keys, containment, or similarity **plus** a shared
distinctive first token: 52 groups over 108 brands, all real, with
"Dominos Pizza" vs "Domino's Pizza Inc" still matching.

**Merges are now durable across rebuilds.** The user's architectural read was
right: a merge is not a bronze concern. It cannot live only there either -
silver is `CREATE OR REPLACE`d from bronze on every build and a sample reload
re-inserts source rows wholesale, so a merge expressed as a one-off UPDATE is
undone the next time either runs. New `brand_merges` table records
source -> target (chains flattened), and `_build_silver_layer_impl()`
re-applies the mapping on **every** build. Proven end to end against the live
warehouse: merge moved 20 listings, mapping recorded, silver rebuilt (24,941
rows), and afterwards **0 rows remain under the retired brand in bronze or
silver** while the target holds 447.

Also fixed: `resetMapping()` now clears the brand selection (hiding a save
returned a "cleared" workspace that still had the previous business selected),
and `saveMapper()` refuses to implicitly create a brand from leftover form
state - a record nobody asked for; "Continue Without Saving" now actually
discards the parse; an empty Review queue renders as a green success panel
rather than a bare line on a blank tab; failed enrichment backs off 5 minutes
per consecutive failure to a 60-minute ceiling, cleared by the first success
and bypassed entirely by a user pressing the button (no retry timing is ever
shown, per explicit instruction).

**Two test-isolation faults found on the way**, both order-dependent and both
worth knowing: a leftover `REPORTING_REFRESHING` made
`_refresh_silver_background()` skip its thread in a later test, and
`_ensure_brand_merges_table()` built its `SchemaField` list **before** probing
the table - the only ensure pass that did - so under the fake bigquery module
other suites inject it raised and failed the whole silver build with rows=0.
Both now reset/deferred; `unit_tests/conftest.py` clears the process globals
between tests.

Suite: **567 passed**.

### Twenty-third batch (2026-09-09) — the server wedged itself, and why

Caught while verifying the previous batch: the live server answered static
files, `/` and `/api/session` in under 3ms while `/api/reporting` and
`/api/reporting/quality` timed out past 180s - no error, nothing in the access
log, 18 threads, 65MB RSS, 166 file descriptors. Not a leak, not a pile-up.

`_heavy_request.__enter__` called `_HEAVY_REQUEST_SEMAPHORE.acquire()` with **no
timeout**, and `HEAVY_REQUEST_CONCURRENCY` is 3 - so once three requests wedged
inside, every later caller queued behind them for the life of the process.
Bounded now by `HEAVY_REQUEST_WAIT_SECONDS = 45`, raising `TimeoutError`, which
the existing handler already renders as "busy, refresh shortly". Verified: six
concurrent `/api/reporting` calls all return 200 in ~10s, warm calls 10ms.

Also throttled `/api/sample/status`, which spawned a background recount thread -
six BigQuery COUNTs on a **fresh client each time**, because `_bigquery_client()`
is a plain factory and not a cache - on every single poll.

**The diagnostic is the reusable part.** When this app looks "stuck", check
*which* endpoints are affected first. Static files and `/api/session` answering
instantly while only the heavy reads hang points at the concurrency gate, not
at BigQuery or SQLite. Running `reporting_summary()` out-of-process at the same
moment returned in 1.6s cold / 0.0s cached, which is what ruled out the query.

Suite: **549 passed**.

### Twenty-second batch (2026-09-09) — master delete: the leak and the speed-up

**The leak the user asked about.** `drop_dataset_tables()` built a brand new
`bigquery.Client` on every call and never closed it, and the master delete
calls it three times (bronze, silver, gold). That is exactly the pattern this
repo already records as the cause of a prior gRPC socket/OOM leak. It now takes
the caller's memoised client and closes only a client it created itself.

**The speed-up: 4.3x, measured.** 21 objects were deleted one sequential HTTP
round trip at a time; they now go concurrently on a bounded
`ThreadPoolExecutor`. Benchmarked on a throwaway dataset (never the live
warehouse): 14 objects, **7.4s -> 1.7s**.

**A wrong turn worth keeping in the record.** The obvious fix looked like
collapsing the deletes into a single multi-statement DROP script - one job
instead of N round trips. Measured, that was *slower*: 9.4s versus 8.1s for the
same 14 objects, because a BigQuery query job carries seconds of fixed
scheduling overhead that a REST delete does not. Batching cheap calls into one
expensive job made it worse; concurrency was the answer. A test asserts no
query job is issued, so the idea does not get re-introduced on intuition.

Suite: **544 passed**.

### Twenty-first batch (2026-09-09) — concurrent silver builds

Surfaced while verifying the sample load:
`400 Destination deleted/expired during operation: birdeye_silver_listings._listings_staging`.
`build_silver_layer()` writes a **fixed** staging table and DROPs it, so two
builds running at once destroy each other's destination. Only two of its five
call sites took `REPORTING_REFRESHING` - the sample load, the clear worker and
the gold bootstrap did not - so clicking Load Sample Dataset while a background
refresh was running collided, the build failed, and gold stayed stale. That is
one of the ways reporting comes to disagree with the warehouse.

Serialised on `_SILVER_BUILD_LOCK` at the single public entry point, with the
body moved to `_build_silver_layer_impl()`. The **first** version of that fix
used a plain `threading.Lock` and hung the entire test suite:
`_ensure_gold_reporting_views()` calls `build_silver_layer()` in its bootstrap,
so the nested same-thread path blocked on itself. `RLock` instead - reentrancy
costs nothing on one thread, and the cross-thread collision is still blocked.
The hang is what caught it, which is a good argument for running the suite
after a concurrency change rather than reasoning about it.

Suite: **538 passed**.

### Twentieth batch (2026-09-09) — sample load simplified on the owner's call

**The NTILE(2) half-split is gone.** The user's read was right and the
measurement backed it: a single INSERT over all 22,500 source rows runs in
about three seconds across 17MB, so splitting bought nothing - while costing a
background thread that re-entered `load_sample_dataset()` itself. That
re-entrancy is not theoretical: the second half took the reset branch and
soft-deleted the 11,250 rows and every business the first half had just
written (`businesses: 0 live`, measured). One statement now, no `load_half`
parameter, no background thread, no half-loaded failure mode. The INSERT stays
idempotent, so a load interrupted by a restart tops up instead of duplicating.

**The per-load DDL waste the user spotted in the job log.**
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS is_deleted/deleted_on` ran across
four tables on every single load at roughly four seconds each - about 30 of a
47-second load spent proving columns exist. They are in `TABLE_SCHEMAS`, so on
any table this app created they are already there; the ALTERs are only a
safety net for tables that predate them. Memoised per process via
`_ensure_soft_delete_columns()`, and cleared by `_forget_ensured_tables()` so a
clear or master delete still re-reconciles. The `UPDATE` still runs every time.

**On "mutate the sample table, then make it immutable again":** it was not
needed, and the distinction matters. **Those ALTERs were on
`birdeye_bronze_listings`, not `sample_locations`** - bronze is ours to mutate
freely. `sample_locations` was never at fault: 51 columns, no type mismatches
against the 57-column target, fully compatible. The bug was a query selecting
a column the table does not have. **No copy table was created and the
immutable-source guard was never lifted.**

Suite: **535 passed**.

### Nineteenth batch (2026-09-09) — the sample dataset had never loaded, not once

Reported as "entire sample dataset is not loading". It was worse than partial:
**none of it had ever loaded**. The INSERT selected
`COALESCE(s.validated, FALSE)` but `sample_locations.listings` has no
`validated` column, so BigQuery rejected the whole statement
(`Name validated not found inside s at [17:43]`) and the `except` around it
fell through to the in-memory generator and returned success.

The two datasets have **nothing in common**, which is how the substitution
went unnoticed: bronze held `sample_business_crimson_slice_csv` /
"Crimson Slice Austin 12" (15 demo brands) while the source holds
`biz_brand_0887` / "Brewer Roastery #18447" (1,000 synthetic brands), and all
22,500 source `listing_id`s were absent from bronze. What looked like a
41%-loaded sample (9,295 of 22,500) was a different 9,295-row generated set
standing in for it.

Fixes: `FALSE AS validated` (the source carries no validation state, and
freshly ingested rows being unvalidated is the honest value); the fallback now
logs at ERROR and carries the reason out on `sample_ingestion_error`, because
a silent fallback that substitutes different data is indistinguishable from
the real thing; a `verify_sample_source_schema()` preflight names missing
columns up front; "already loaded" now means the SOURCE's rows are present
rather than "some sample rows exist" (the generator's own rows were making the
loader skip ingestion entirely); and the INSERT skips source `listing_id`s
already in bronze so a re-run tops up instead of duplicating.

**A bug I introduced and then fixed, worth recording.** Making "already
loaded" source-aware had a consequence I did not anticipate: half 2 re-enters
`load_sample_dataset()` from its own background thread and can never look
complete either, so it took the reset branch and soft-deleted the 11,250 rows
*and every business* half 1 had just written - businesses went to 0 live.
The reset is now guarded to `load_half == 1`; a top-up needs no reset at all
because the INSERT is idempotent. Caught by measuring the warehouse after the
load rather than trusting the load's own success response.

**Schema compliance verified both directions** (user asked): 51 source columns
vs 57 target, no type mismatches on any shared column; the 6 target-only
columns are defaulted or left NULL. Permission to modify `sample_locations`
was offered and proved unnecessary - the fault was in the query, not the
table - so the immutable-source safety rule stays intact.

Suite: **531 passed**.

### Eighteenth batch (2026-09-09) — the real cause of "0 data": pytest was wiping the live mirror

`sqlite_cache.DB_PATH` was a bare constant pointing at
`.cache/whitespace_cache.db` **with no test override**, and the suite
exercises `clear_sample_reporting_mirror()`, `clear_local_cache_db()` and the
gold-mirror swap for real. Every `pytest unit_tests/` run therefore mutated
the **live application cache**. That is why reporting kept collapsing to zero
with nothing in the server log to explain it: the wipes were not coming from
the server.

How it was pinned down, rather than guessed: `mirror_meta.synced_at` was in
`CURRENT_TIMESTAMP` format (`2026-09-09 16:07:08`), which only
`clear_sample_reporting_mirror()` writes - `replace_gold_mirror()` writes
ISO-8601 with a `T`. The deltas matched a sample-brand deletion exactly
(zip-brand 41,882->41,585, i.e. -297 brand rows; businesses 1,013->998, i.e.
-15 sample brands). `lsof` then showed **five orphaned pytest processes**
holding the database open, the oldest from 12:56.

Fixed with `WHITESPACE_CACHE_DB` plus `unit_tests/conftest.py`, resolved once
at import so the ~10 tests that already isolate themselves with
`patch.object(sqlite_cache, "DB_PATH", tmp)` are unaffected. Verified end to
end: live mirror 13,803 rows before a full suite run, 13,803 after, identical
`synced_at`. A guard test asserts the suite can never point back at `.cache/`.

Two real bugs were found and fixed on the way there, both genuine:

- **The gold-mirror wipe guard was unreachable for locations.** It read
  `if had_real_data and not force and not zip_brand_rows and not location_rows:`
  - only skipping when BOTH collections were empty. But
  `vw_zip_brand_activity` is a LEFT JOIN off the ZIP reference and returns
  ~41.5k rows whether or not any brand has activity, so it is never empty and
  the conjunction could never be true. Each collection is now judged on its
  own collapse, and a row count is no longer mistaken for health.
- **A slow sync could commit its empty result over a newer good mirror.** The
  three gold reads take a minute or more; the original guard compares against
  the mirror at read time, so a second check now compares at write time,
  immediately before the swap.

Also in this batch: sample status mirrored in `app_settings` (not
`query_cache`, which `invalidate_cache()` wipes) so a status hiccup can no
longer render "Load Sample Dataset" over a loaded warehouse; half-vs-complete
distinguished by comparing against the source's own row count (measured live:
9,295 of 22,500); Clear now cancels an in-flight load instead of racing it and
runs against BigQuery before the mirror; `/api/sample/load` refuses a
concurrent second load; and the trailing-"..." progress text is gone in favour
of the spinner.

**Not a bug:** the review count of 118 is correct - `error_listings` holds 395
rows total and 118 live against 14,499 live listings. 118 is still-open
validation errors; 395 is every listing that was ever invalid.

Suite: **528 passed**.

### Seventeenth batch (2026-09-09) — nine live-reported bugs, plus brand-independent content_hash

Reported by the user while working in the app; every one traced to a cause
before being changed, and **measured** where a number was in doubt. Full
per-bug detail is in `docs/bug_tracker.md` (B23-B32). The ones worth knowing:

**`business_id` removed from `CONTENT_HASH_FIELDS` (user instruction).** The
hash now answers "is this the same physical place?" independently of which
brand filed the record — which is exactly what made the cross-brand duplicate
signal (old O2) impossible before. Per-brand dedupe is unaffected:
`_dedupe_listings_against_bronze()` keys on the composite
`(business_id, content_hash)`, so the brand is still carried explicitly.
Removing a field changes **every stored hash**, so `LEGACY_CONTENT_HASH_FIELDS`
/ `legacy_content_hash()` reproduce the old definition and the dedupe matches
either, upgrading a matched legacy row to the new hash in place. That closes
the real risk (a re-save inserting a duplicate copy of the entire warehouse).
A one-shot backfill for rows never re-observed is the remaining piece — see
O8; recompute in Python, not SQL, because reproducing `json.dumps(sort_keys=True)`
plus Python `str()` float formatting in BigQuery is a trap.

**"Is clear cache happening always?" — yes, and it was measurable.**
`query_cache` held **only** the exempt `reporting_quality:*` keys; every
`reporting_summary:*` entry was gone. `invalidate_cache()` is a blanket
DELETE and the background loops called it every pass. Background callers now
go through `_invalidate_cache_background()` (120s floor); user actions still
clear immediately, and a test enforces that split.

**Numbers that disagreed on screen were wiring, not data.** The review cards
showed "-" while the mirror held correct, reconciling values
(`ai_fixed=110, manual_fixed=155, manual_pending=130, total=395`) — they were
read off the heavy `/api/reporting/quality` and failed with it; they now have
their own mirror-backed `GET /api/review/fix-states`. "AI Fixed by Total
Error" showed 0.00% beside 110 AI fixes because it divided the *current
auto-repair batch* (which resets per batch) instead of the cumulative counts;
it is 27.85%.

**Head-to-Head colours were inverted.** Every row is a competitor measured
against the primary brand, so a competitor with MORE locations is bad news —
`diff > 0` was green. One shared helper now drives all five columns.

**Top States: same root cause, third time.** `container.clientWidth` is 0
while the panel is hidden. Rewritten as a fixed-viewBox plain SVG so nothing
is measured — deliberately the one chart here that is not d3.

**The brand form had three mode flags and a button that read one.**
`presetBrandEditMode` was never consulted by `#createBrandBtn`, so the preset
"Edit Brand Details" path left it on its create branch and saving filed a
second copy of the brand on screen.

Suite: **518 passed**. `node --check` clean on all 7 UI JS files, `py_compile`
clean, `git diff --check` clean. **No server restart taken** (standing rule),
so none of the backend half is live yet.

### Sixteenth batch (2026-09-09) — one dialog shell, merge confirmation, store-level enrichment, failed-save visibility

**Measured, not estimated:** coverage is **53%** overall
(`workflow_server.py` 48%, 4151 statements / 2150 missed), taken with
`.venv/bin/python -m coverage run --source=whitespace_tool -m pytest unit_tests/ -q`.
The ~110 tests added since the last 52% reading moved the total by one point,
because `workflow_server.py` dominates the statement count. Suite is now
**508 passed** (was 498).

**1. Every dialog is on one shell (the user-reported bug, now fixed).** Five
dialogs carried bespoke frames that ignored the app theme:
`pythonConnectorDialog` and `editRecordDialog` (`connector-editor-dialog`),
and `dangerDialog` / `masterDeleteCredentialsDialog` /
`masterDeleteConfirmDialog` (`danger-dialog`). All twelve dialogs now use
`<dialog class="app-help-dialog"> > .app-help-content > .app-help-header >
<h2 id>`, varied only by three modifier classes — `--editor` (the 1200x800
code-editor size), `--form` (mid-width record form), `--danger` (red border,
red rule, red title, so a destructive action stays visibly destructive while
on the blue/white shell). Both retired frames were deleted from the CSS
outright, and every dialog gained `aria-labelledby`. Guarded by
`test_every_dialog_uses_the_one_birdeye_shell`, which asserts the two retired
class names appear **nowhere** in the file and walks every `<dialog>` in the
markup rather than spot-checking ids.

**2. Merge now has an explicit confirmation naming what moves (O3).**
`merge_brands()` takes `preview: true` and answers with per-table COUNTs
instead of running the UPDATEs; the rail's "Combine selected" runs it for
every group before showing a themed confirm. A table whose count cannot be
read reports **None**, not 0, and the dialog then declines to show totals at
all — reporting an unreadable table as zero would let the dialog say "nothing
will move" about data that is actually there. Mutation-tested: forcing that
path to 0 fails the test.

**3. Store-level idle enrichment (O6/Q9), and what it actually could be.**
The stated plan was to refill fields cleared by semantic cleaning using
`raw.__meta.semantically_cleared_fields`. **That breadcrumb never reaches the
warehouse for a valid listing** — `listings` has no `raw` column (57 columns,
verified); only `error_listings.raw_record` keeps the raw payload. So the
refill cannot be driven off the marker for saved rows, and is driven off the
blank column itself instead. New `enrich_location_contact()` in
`brand_enrichment.py` queries Overpass **around the listing's own
coordinates** and requires a shared meaningful word between the listing name
and the POI name, so a neighbouring business cannot donate its phone number;
a name-matched POI carrying no contact tag is not an answer either.
`_idle_location_enrichment_pass()` fills only blank columns and **re-asserts
the blank-only guard in the SQL WHERE**, because the row was read moments
earlier and a concurrent user edit must win. It shares the existing
`brand-enrichment` thread rather than adding a second idle worker on a 512MB
box. Both guards mutation-tested.

**4. A failed save left no trace anywhere (O1).** `record_save_event()` was
reached only *after* a successful `push_to_bigquery`, so a save that failed
produced **no Job History row at all** — indistinguishable from never having
been started. It is now also recorded on the failure path
(`mapped_rows=0` with rows present is what `record_save_event()` already
derives `FAILED` from, so no new status vocabulary), narrowly around the push
so an argument-validation raise still never becomes a job. On the UI side, a
save the user dismissed to the background now announces its own failure
through the themed dialog and refreshes Job History — previously the only
signal was an inline `#status` line, and `resetMapping()` had already
returned the user to the pre-parse layout where they were not looking at it.
The dismissal flag is read *before* `hideProgress()` resets it.

**5. O2 is not "unwired", it is impossible as specified — do not revive it.**
`duplicateContentHashGroups()` grouped listings by shared `content_hash` to
find one physical store filed under two brands. But `business_id` **is** one
of `CONTENT_HASH_FIELDS`, so two brand records can never collide on a hash by
construction — verified: the identical listing under `brand-A` and `brand-B`
produces two different hashes. The helper could never have fired. It has been
removed with the reasoning left at the call site, and the test now asserts its
**absence** plus the hash property itself. A real cross-brand overlap signal
needs a hash over physical identity *excluding* `business_id`, computed
warehouse-side, plus a product call on whether a shared street address is
evidence of a duplicate brand or just a shared strip mall. Both still open.

Also confirmed **already done but still listed as open** in the tracker: O4
(per-table downloads — `data-table-export` on Top States, Top Cities, Brand
Comparison and Market Gaps) and O5 (Extended Coverage Metrics panel removed;
`loadExtendedMetrics()` now serves only the Top States chart).

**Settled by the user (2026-09-09):** sample-load halves keep the **automatic
second half**. `load_sample_dataset(load_half=1|2)` splits via `NTILE(2)`;
half 1 returns fast so the app is usable and half 2 self-starts in a
background thread. No second click. Current code already does this — no change
was needed, and this is no longer an open question.

### Fifteenth batch (2026-09-09) — see `docs/bug_tracker.md` SESSION HANDOFF

Landed: five-state cumulative counters (`was_ever_invalid`/`resolution_status`)
on both the reporting and review tabs; per-brand counts switched to the same
cumulative model so Quality-by-Brand and the headline card stop disagreeing;
adopted AI suggestions now count as AI fixes; auto-refresh no longer blanks the
report (`reportHasRenderedOnce`); NTILE(2) half-loading for sample data;
keyless brand enrichment (OSM + DuckDuckGo, never invents a value); generic
`run_sql`/`run_sql_dml` helpers; deferred `user_reviewed` save; server-side
session enforcement; concurrency cap on heavy reads (peak 432MB -> 261MB on a
512MB box); wrapped-longitude repair; pagination on every reporting table;
themed notice/confirm dialogs; per-table ZIP exports.

**Reverted deliberately:** bulk migration of ~85 `client.query()` call sites to
`run_sql`. It broke test doubles whose `query()` accepts only SQL. The helper
stays and `merge_brands` uses it; adopt the rest incrementally with tests
between batches.

**Still open:** 5 dialogs not on the Birdeye blue/white shell (user-reported,
unfixed); coverage unmeasured since ~110 tests were added; sample-load second
half automatic vs second-click unresolved; idle enrichment does not yet refill
semantically-cleared fields.


**See `docs/bug_tracker.md` for the live fixed-vs-open status table.** Batch entries below carry the detail.

### Fourteenth batch (2026-09-09) — per-column-type validation, repair and clearing

**STANDING INSTRUCTION (user, explicit): do NOT restart the server unless the user asks.** One restart was taken to load this batch; none after that.

Implements the generalized form of the earlier "if you are so sure a column can't hold a string, just clear it and try to enrich" instruction: **if a column's name or type is commonly understandable and the value inside is not what that kind of column should hold, clear it, fix it, and leave it for enrichment.**

New module `whitespace_tool/data_validation/semantic_types.py` - deliberately ONE declarative table plus two small functions, not a per-column branch (the user's "less code on Claude's side, not less functionality"). Adding a column type is a row in `NAME_PATTERNS`, not new code.

- **Name beats declared type.** The registry declares 25 of its 41 fields as plain `"string"`, so the declared type says almost nothing; the column NAME is what identifies it. `phone_number` declared as a string is still a phone number.
- **Kinds covered**: phone (E.164 digit range), email, url (adds scheme, validates domain), money (strips `$`/commas, rejects negatives), count, percent (0-100), rating, year, boolean, date, timestamp, latitude/longitude ranges, free text.
- **`NULL_SENTINELS`** - "N/A", "null", "none", "-", "unknown", "TBD", "#N/A", "(blank)" and friends are cleared in *every* kind of column. Stored verbatim they look like real data and defeat every completeness metric downstream.
- **Cleared, not rejected** - matches how unparseable numerics already behave: the row's other good fields survive, and the blank becomes something enrichment can fill.
- **Cleared field names are recorded** on `raw.__meta.semantically_cleared_fields`, so review/enrichment can target them instead of seeing a silent blank.

**`GEO_OWNED_FIELDS` - the "don't forget the older city->zip / zip->city features" guard.** The generic cleaner NEVER touches postal_code, city, state, country, county, address, or lat/long. Each already has dedicated logic strictly smarter than a regex: `clean_zip()` keeps non-US alphanumeric codes ("SW1A1AA") a US-shaped rule would wrongly clear; `normalize_state_code()` handles names/codes/misspellings; `lookup_cached_city_state()` does city<->ZIP<->state resolution from cached reference data; and `detect_and_fix_inverted_coords()` **swaps** transposed pairs - so clearing an out-of-range latitude would destroy the very input that repair works from. If a geo field needs new behavior it belongs in `geo_enrichment.py`, not here.

**Wiring** (two call sites, so mapped and unmapped columns cannot disagree):
1. `_apply_semantic_cleaning()` runs as a post-construction pass in `normalize_location()`, over the built record - it sees the same normalized values the warehouse would store.
2. `_collect_extras()` cleans unmapped passthrough columns, which previously had **no validation at all**. **This is what covers custom fields**: a custom field has no typed column, so it lands in extras and is cleaned by column name exactly like a mapped field.

Verified end to end on a real record: `Phone "N/A"` -> cleared and recorded; `Email "BOB@Example.COM"` -> `bob@example.com`; `Web "example.com"` -> `https://example.com`; `Rev "$1,250,000"` -> `1250000.0`; `Stars "excellent"` -> cleared; custom `franchise_phone "(512) 555-1234"` -> `5125551234`, `opened_year "1998"` -> `1998`, `custom_revenue "$99,000"` -> `99000.0`, `store_rating "not-a-number"`/`notes "---"` dropped; **ZIP/city/state/country all unchanged**.

Tests: new `unit_tests/test_semantic_field_cleaning.py` (18 tests) covering geo ownership, kind inference, repair/clear behavior per kind, and normalize_location integration including custom fields. **Mutation-tested**: disabling the geo exemption fails 2 geo-protection tests, confirming they have teeth. Full suite **378 passed**; the older geo/silver/demo-validation suites (27 tests) pass unchanged.


### Thirteenth batch (2026-09-09) — test coverage and validation for batches 10-12

New file `unit_tests/test_custom_fields_lifecycle.py` (24 tests) adds **behavioral** coverage where source-contract assertions were not enough — these drive the real functions against a recording fake client and assert on which statements actually get issued:

- **Archive-not-delete**: exactly one `is_archived = TRUE` UPDATE and **zero** `DELETE` statements; standard fields rejected; missing field rejected; admin password enforced.
- **Revive-not-duplicate**: an archived slug is revived with no catalog insert; a genuinely new field IS inserted; `_ensure_listings_table()` is always called first.
- **Gold view drift**: a current stamp skips rebuild; a stale stamp rebuilds; an **unstamped legacy view is treated as stale** (views created before versioning existed carry no stamp).
- **`_collect_extras` edge cases**: mapped columns not duplicated, `__meta` excluded, blank/null skipped, `None` (not `{}`) when empty, dotted mapping keeps the parent object.
- **Workbook**: metrics sheet arithmetic reconciles against sheet-1 rows; unavailable is labelled; a genuine zero does not claim unavailability; oversized cells truncate instead of failing the export; column headers are a **union** of all rows' keys (different parses carry different columns).

**Mutation-tested rather than trusted.** All 24 passed on first run, which is suspicious, so each critical assertion was verified to actually fail when the behavior is reverted: disabling the drift check → 2 failures; removing the archive flag → 1 failure; dropping `custom_fields` from the mirror column list → failure; removing the silver passthrough → failure. The tests have teeth.

**BUG FOUND BY LIVE SMOKE, not by any test: `uncovered-zips` (and every ZIP-family metric) returned 400.** The export computed `location_count > 0 AS is_covered` in its SELECT list and then filtered on it in the WHERE of the *same* query — BigQuery rejects that with "Unrecognized name: is_covered". Fixed by computing the flag in its own `flagged` CTE. **No fake-client test could ever have caught this** — a fake returns rows regardless of whether the SQL is valid (the same reasoning behind `_QueryRecordingClient` in `test_reporting_timeseries_cache.py`). This is why the live endpoint smoke matters and is not optional. Guarded now by a SQL-shape regression test.

**Test-isolation gotcha (cost real debugging time, worth knowing):** the new tests passed standalone but failed 6 ways in a full-suite run. Other suites inject a fake `google.cloud.bigquery` into `sys.modules` and leave the real namespace package degraded on cleanup, so a later `from google.cloud import bigquery` resolves to a module with no `QueryJobConfig`. Faking only the *client* is not enough — the *module* must be faked too. Fixed by reusing the established `_FakeBigQueryModuleMixin` pattern. **Any new test touching a BigQuery-calling function must inject its own fake bigquery module.**

Also note: an 83s/1-failure run during this batch was pytest reading a test file **mid-edit**, not a flake. Verified deterministic: 358→360 passed across repeated runs at ~3.5s. There is no `pytest-randomly` in this project, so order is file-order stable.

**Full validation run**: 360 tests passed; `node --check` clean on all 8 UI JS files; `py_compile` clean on all 6 touched Python modules; `git diff --check` clean; server restarted; 7 core endpoints all 200; **all 24 metric exports across both tabs return 200** with zero server tracebacks.


### Twelfth batch (2026-09-09) — custom fields made first-class end to end

Follows the eleventh batch, which only reached bronze. Custom/unmapped source columns now survive every layer and every read path.

- **Silver**: `l.custom_fields` added to the `_listings_staging` SELECT. `listings_enriched` and `listings_invalid` are both `SELECT *` off staging, so one line reaches both.
- **Gold**: added to `vw_reporting_locations`.
- **SQLite mirror**: added to `MIRROR_LOCATION_COLUMNS` and to `sync_gold_mirror()`'s explicit SELECT. **Also fixed a latent bug**: `mirror_reporting_locations` had no ALTER top-up pass (unlike `mirror_businesses`), so an existing `.cache/whitespace_cache.db` would have failed `replace_gold_mirror()`'s explicit-column INSERT with "no such column" on the first sync after any column addition. Added the same migration loop.
- **Write-back**: verified, no change needed. The review edit form is built from `Object.entries(rawObj)` — every raw key, not just mapped ones — so an edit resubmits unmapped columns, and `reprocess` re-derives extras from that full record via `normalize_location()`. Locked with a test so a future "only render mapped fields" tidy-up cannot silently break it.

- **`delete_custom_field()` now ARCHIVES instead of deleting.** New `is_archived`/`archived_at` columns on `field_catalogs`. Listings already saved carry that field's values inside `listings.custom_fields`; a hard DELETE stranded them with no label, type or provenance to read them by. `field_catalog()` filters `is_archived IS NOT TRUE`, so archived fields vanish from the mapper and every field picker while both the values and their definition stay intact and recoverable.
- **`create_custom_field()` revives an archived slug** rather than inserting a duplicate (the archived row already describes the stored values), and calls `_ensure_listings_table()` so the column that physically stores custom values exists before the catalog advertises the field.
- **Live round-trip verified**: create → visible in catalog → delete → row retained with `is_archived=TRUE`, hidden from `field_catalog()` → re-create → same row revived, **no duplicate**, `is_archived=FALSE`.

- **BUG FOUND AND FIXED (general, not specific to this work): a changed gold view definition never reached an already-deployed environment.** `_ensure_gold_reporting_views()` returned early whenever the five required views merely *existed* — it never checked whether their SQL was current — so an edited view kept serving its OLD columns forever, and only a brand-new environment got the new definition. This was live-confirmed: bronze and silver picked up `custom_fields` immediately, gold did not. Same drift class as `error_listings` missing `has_ai_suggestion`. Fixed with `GOLD_VIEW_DEFINITION_VERSION`, stamped onto each view's `description` at build time and compared on every ensure; a version mismatch triggers a rebuild. **Bump this constant whenever a gold view's SELECT list changes.**

- **`field_catalog()`'s ad-hoc migration generalized**: it carried two hardcoded `ALTER ... ADD COLUMN` statements (business_id, content_hash). Now reconciles against `TABLE_SCHEMAS` like the other ensure passes, so `is_archived`/`archived_at` deployed automatically. Columns are added NULLABLE (BigQuery rejects adding REQUIRED).

**Live verification** (after restart, `build_gold_layer()` + `sync_gold_mirror(force=True)`): `custom_fields` present in bronze `listings`, silver `listings_enriched`, gold `vw_reporting_locations` (stamped `birdeye_gold_view_version=2026-09-09.custom-fields`), and `mirror_reporting_locations`. Mirror populated count is 0 **and that is correct** — the 37,208 existing listings were written before the column existed, so they legitimately have NULL; new saves populate it.

Regression: **336 passed**. Note: running `test_warehouse_schema.py` *alone* shows unrelated numpy/pandas re-import failures caused by other tests' `patch.dict(sys.modules, ...)` fakes in the same process — it is green in the full suite, which is how it is run.


### Eleventh batch (2026-09-09) — dynamic/bronze column coverage

**Question answered: how are dynamic columns handled at the bronze level? Previously — they weren't.** Traced end to end and reproduced the drop:

- **Developer-added columns: already fully handled.** Two independent reconcile passes ALTER the deployed table to match `TABLE_SCHEMAS` — `push_to_bigquery()` (`warehouse_bigquery.py`, appends any missing column as NULLABLE via `update_table(["schema"])`) and `_ensure_listings_table()`. Add a column to `TABLE_SCHEMAS` and it lands automatically. **This is exactly the mechanism that was missing for `error_listings`** (see tenth batch) — hence the `has_ai_suggestion` outage.
- **User/source columns that differ per parse: silently dropped.** Two places killed them independently: `_listing_row()` builds an explicit dict from `LocationRecord`'s typed attributes, and `rows_to_dataframe()` does `.reindex(columns=table_columns(table))` against the *static* schema. No error, no warning. `create_custom_field()` registered metadata in `field_catalogs` (`table_name: "listings"`) but nothing ever added the column, so a mapped custom field reported `mapped_rows: N` and stored nothing.

**Fix: `listings.custom_fields`** — a per-row JSON document of every source column no typed field consumed. Populated by `_collect_extras()` in `normalize_location()`, the only place that knows which source paths the mapper actually used; carried on `LocationRecord.extras`; serialized in `_listing_row()`.

Three deliberate design constraints, each guarded by a test in `test_warehouse_schema.py`:
1. **STRING-holding-JSON, not the BigQuery `JSON` type.** A JSON column flips `table_has_json_fields("listings")` to True, which forces every save off the fast `load_table_from_dataframe` path onto `load_table_from_json` — a real regression on the hottest write path (tens of thousands of rows per save). `PARSE_JSON`/`JSON_VALUE` read a STRING fine.
2. **Excluded from `CONTENT_HASH_FIELDS`.** Listings hashing is driven by that explicit tuple (`table_hash_columns()` special-cases listings), so adding the column leaves every existing row's hash byte-identical — verified. Including it would have made the next save treat the entire warehouse as new rows. **Trade-off, documented:** two rows differing *only* in an unmapped column still dedupe as identical.
3. **Bounded** (`EXTRAS_MAX_KEYS = 60`, `EXTRAS_MAX_CHARS = 8000`) so a pathological wide source can't blow the 512MB budget one row at a time — and truncation writes a `__truncated` marker into the payload rather than happening silently.

A top-level source key counts as consumed only on an exact path match, so for a dotted mapping (`address.street`) the parent object is also kept in extras — duplicating a little is the deliberate trade against losing a column.

`custom_fields` is also included in the listing-family metric exports as "Additional Source Fields".

**Caught immediately by the tenth batch's honest-empty work:** the first live export after adding the column returned `DATA UNAVAILABLE` because `custom_fields` was not yet on the deployed table — the same `has_ai_suggestion` failure class, self-inflicted. Fixed by calling `_ensure_listings_table()` alongside `_ensure_error_listings_table()` in `reporting_metric_export()`. Had the old behavior still been in place this would have returned a plausible-looking empty workbook instead. Live-verified after the fix: 5.0MB export, `Additional Source Fields` present.

Regression: **331 passed**. Server restarted.


### Tenth batch (2026-09-09) — entity-level exports, Excel workbooks, and two live-breaking schema/guard bugs

- **RULE ADDED (user, explicit): no metric anywhere in the app may read stale after a clear.** Both `clear_saved_data()` and `clear_sample_dataset()` already re-mirrored (ninth batch); this batch found the counters were still stale afterwards. `auto_repair_stats` (the AI/manual fix tally) is a *persisted SQLite counter*, not a derived read, so re-mirroring never corrected it — it kept showing fixes for rows that had just been deleted. Both clear paths now also call `_schedule_quality_fix_metrics_refresh(force=True)`. Guarded in `test_reporting_cache.py`.

- **Metric card downloads now export the ENTITIES behind the number, as a 2-sheet Excel workbook** (`/api/reporting/metric-export`, `reporting_metric_export()`). Previously the hover download produced a single summary line (`metric,value,filters,generated_at`) — the figure restated, not the data behind it — and tab 1 (Location Intelligence) had no export at all. Now:
  - **Sheet 1 "Listing Data"**: one row per entity, at the grain the metric is actually counted at.
  - **Sheet 2 "Metrics"**: the metric's definition plus arithmetic computed *from the sheet-1 rows themselves*, so the two sheets can never disagree and the headline figure is reproducible by hand.
  - Five metric families, deliberately separated because they are counted over different populations: `_FIX_EVENT_METRIC_TYPES` (quality_fix_events — the same source the cards and Trends chart count from), `_ERROR_METRIC_PREDICATES` (error_listings), `_LISTING_METRIC_SLUGS` (listings + the boolean flag each rate is defined by), `_LOCATION_VIEW_METRIC_SLUGS` (vw_reporting_locations, for the richest location fields), `_ZIP_METRIC_SLUGS` (vw_reporting_gap_base — an uncovered ZIP has no listing by definition, so listing grain would be nonsense), `_BRAND_METRIC_SLUGS` (businesses).
  - Slugs are derived from the card label, so a new card needs no wiring beyond its label. A contract test asserts **every** label on both tabs resolves to a known slug — this caught two genuinely missing mappings before shipping.
  - **Watch item**: fix counts come from `quality_fix_events`, NOT `error_listings.is_ai_enriched`. `fix_type` is stored upper-cased (`'AI'`/`'MANUAL'`) — comparing against `'Manual'` silently matches nothing. My first draft had exactly that bug; caught by the contract test.

- **BUG (live-verified, was breaking the whole quality tab): `error_listings` had no ensure-pass at all.** Unlike `listings`/`businesses`, nothing ever reconciled the deployed `error_listings` table against `TABLE_SCHEMAS`. So `has_ai_suggestion` (added in the ninth batch for the AI/manual review-pending split) never reached the live table, and every query selecting it failed with `400 Name has_ai_suggestion not found inside e` — same class as the coverage-query bug. Added `_ensure_error_listings_table()` and called it from both `reporting_quality_summary()` and `reporting_metric_export()`. Live-verified: all seven error-family exports went 400 → 200 after the fix.

- **BUG (pre-existing, was documented as "needs product decision" — now fixed): the `bad_row_index` guard aborted an entire save over one malformed row.** This directly contradicted the documented data-flow contract ("valid rows are stored; invalid rows are routed to Review Error Listings without blocking valid rows"), and the row loop in `save_mapper()` *already* handles a non-dict row correctly by routing it to error_listings. The early guard just raised first, silently losing every valid row alongside it. Now it only fires when **every** row is malformed (a wrong-shape submission, where there is nothing to save either way). The long-failing `test_csv_workflow.py` test passes; the suite is green for the first time in this session.

- **Empty exports now say why they are empty.** A missing table/view is an honest empty result, but a blank sheet is indistinguishable from a real zero — the exact silent-zero trap that once made every coverage metric read 0%. `unavailable_reason` is now surfaced as a `DATA UNAVAILABLE` row on the Metrics sheet and as the empty-sheet message; non-404 failures propagate to a 400 instead of being dressed up as "no records". (This was not hypothetical: exports issued while a silver/gold rebuild was in flight came back empty, and looked exactly like real zeros.)

- **"Data Enrichment" panel renamed to "Brand Entity Resolution"** with a description covering validation → AI resolution → enrichment.

- **BUG (user-reported): hiding the parser progress left the post-parse workspace up**, with no way to start another parse. The hide action now calls `resetMapping()`, returning the mapper to its pre-parse 40/60 layout. The save keeps running in the background — it works from data captured before that point, not from mapper state.

- Full regression: **326 passed** (previously 322 passed + 1 long-standing failure). Server restarted and live-verified.

- **Ninth batch (2026-09-09) — the user sent a formal, deduplicated, ticket-numbered engineering backlog** ("Listing Data Platform — Engineering Backlog", INV-1..15 cross-cutting invariants + GEO/BRD/MAP/TPL/SMP/JOB/RVW/RPT/FLT/UIX/BUG/DOC tickets + a suggested Wave 1-6 execution order). This is now the authoritative backlog going forward — cross-reference ticket IDs (e.g. "RPT-13", "UIX-05") in future work. Wave 1 (P0 unblockers) work done this batch, largely triggered by the user live-screenshotting the running app while I worked:
  - **RPT-01 (auto-refresh wipes report data) — CONFIRMED already fully fixed** by the Sixth-batch `sync_gold_mirror()` guard (see below): traced every `replace_gold_mirror`/`sync_gold_mirror` call site again, confirmed there is no other direct-empty-swap path, and `replace_gold_mirror()` is already a single atomic SQLite transaction (BEGIN/commit/rollback) — no further change needed.
  - **RVW-02 / JOB-08-adjacent — FIXED a real, live-measured 30-second hang.** User asked directly "is this wired to local db or always fetching BQ" after screenshotting a stuck "Loading quality metrics" spinner. Answer, confirmed by curl against the running server: `reporting_quality_summary()` *is* cache-first (`get_cached_query()`), but a genuinely cold cache (first load, or right after any `invalidate_cache()` from a save/reprocess) fell through to a live BigQuery scan + full Python aggregation over the entire `error_listings` population — **measured at 30.15s** against ~21k rows. Fixed by extending the same stale-cache background-refresh pattern that already existed for warm caches to the cold-cache case too: a cold, non-force-refresh request now kicks off the identical computation in a `quality-mirror-cold-warm` background thread and returns an honest all-zero `{"quality_cache": "warming"}` placeholder immediately (0.015s, live-verified) instead of blocking. Explicit `?refresh=1` requests are deliberately excluded — those already show their own progress UI and are expected to wait. Frontend (`reporting-tabs.js`'s `loadQuality()`) now recognizes `quality_cache === "warming"` and polls again every 2s (capped at 20 tries) instead of rendering the placeholder's all-zero shape as real data. Live-verified end-to-end: first call → placeholder in 0.015s; ~30s later, polled again → real data (`quality_cache: "sqlite"`, `invalid_listings: 28665`). Tested: 2 new tests in `test_reporting_cache.py` (source-contract style, matching this function's existing test convention) + 1 pre-existing test in the same file fixed (stale assertion string, unrelated drift from an earlier `median_household_income` addition to the same dedup query — not caused by this batch).
  - **New finding while investigating the above, also FIXED**: the same cold BigQuery response showed `invalid_record_rate_pct: 2866500.0` — a nonsensical percentage (INV-15 violation). Root cause: `coverage_metrics.get("total_records", 1)` never actually falls back to its "1" default because the key is always present in the dict (just sometimes legitimately `0`, when its own coverage BigQuery query returns nothing) — `28665 * 100 / max(0, 1)` computed as `2866500`. Fixed to report `0.0` when `total_records` is falsy instead of dividing by a fabricated denominator. Tested in `test_reporting_cache.py`.
  - **RPT-13 (fix counters reset on logout/login) — ROOT-CAUSED and FIXED; it was never actually a persistence bug.** Traced per the ticket's own suggested order: (1) confirmed `get_auto_repair_stats()`/`auto_repair_stats` is SQLite-backed, not session state; (2) confirmed `_refresh_quality_fix_metrics_from_bigquery()` already reconciles `fixed`/`manual_fixed`/`remaining` from the durable `quality_fix_events` BigQuery log (throttled 60s, force-refreshed after every reprocess) — live-verified via curl immediately after a fresh server restart: `/api/enrichment/status` returned `{"fixed": 9, "manual_fixed": 4, ...}` with an `updated_at` timestamp from *before* the restart, proving the numbers survive a restart just fine; (3) the actual bug was purely frontend: `#reviewAiFixedCount`/`#reviewManualFixedCount`/`#reviewAiFixedPercent` were *only* ever updated inside `pollAutoRepairStatus()`, which only runs while an auto-repair job is actively polling — a fresh page load (including right after logging back in) left them frozen at their static HTML default of `"0"` forever, indistinguishable from "the counters really did reset." Fixed by extracting the DOM-update logic into a shared `renderFixCounters(state)` (`review.js`) and adding `refreshFixCountersOnce()`, called once whenever the Review tab opens (`switchView()` in `common.js`, alongside the existing `loadErrorBrandBreakdown()` call) — so the real persisted count now displays immediately on every tab visit, not just during an active run. Guarded by a new contract test. **This likely also resolves (or at least stops masking) RPT-03 and JOB-10** per the ticket's own cross-reference note — both should be re-tested against this fix before doing any further work on them.
  - **UIX-05 (top-tabs overlaps data-actions) — FIXED, screenshot confirmed the exact mechanism.** `.header-data-actions` uses fixed pixel-width grid columns (132+148+158px ≈ 462px minimum, can't shrink) plus `.header-account-actions` (132px min-width) — combined ~600px minimum crammed into the header's `minmax(0, 1fr)` "utilities" grid column. The only overflow safety net (`overflow-x: auto`) was gated behind a `@media (max-width: 900px)` breakpoint that collapses the header to block layout entirely — at in-between laptop widths (roughly 900–1400px, matching the reported screenshot), there was no safety net at all, and the box (right-anchored via `justify-self: end`) bled left over the top-tabs instead of being contained. Fixed by adding `max-width: 100%; overflow-x: auto;` to the *base*, unconditional `header .header-actions` rule — a no-op whenever there's enough room (nothing to scroll), only kicking in to keep the overflow inside its own box otherwise, so no specific breakpoint had to be guessed. Guarded by a new contract test.
  - **Reporting/Data Quality polish, from live screenshots** (not yet numbered tickets in the user's doc, filed under §8 Reporting in spirit): "Issue Type Breakdown" donut enlarged (`r` 68→82, `inner` 40→48, viewBox 180→210) and its legend column capped at `minmax(0, 480px)` instead of an unbounded `1fr` that spread label/count/percentage across a huge empty middle gap on a wide report panel; legend font sizes bumped (12px→13px, 11px→12px) for readability. "Improvement Opportunities" changed from a 2-column grid (which orphaned an odd-numbered last card next to empty space — "should be a proper down list") to a genuine single-column vertical list via a new `.dq-improvements-list` class, deliberately *not* reusing the shared `.dq-improvements` class since that one is also used by the States/Cities table pair below it, which is a real, even 2-up that must stay untouched; card title/body font sizes bumped (implicit→15px, 12px→13px). All guarded by new contract tests in `test_mapping_layout_contract.py`.
  - Full regression across every test file touched this session so far: 190 passed, 1 (the same pre-existing, already-documented `bad_row_index` bug, still unrelated and untouched).
  - **MAP-01/MAP-02 (hardcoded `Latitude`/`Longitude`/`state` source fields) — CONFIRMED already fixed, live-verified against the real demo sources.** Fetched the actual global-hotels CSV live via `/api/source-url` + `/api/preview` against the running server: its real header is `HotelId,HotelName,Description,Category,Tags,ParkingIncluded,LastRenovationDate,Rating,StreetAddress,City,StateProvince,PostalCode,Country,IsDeleted` — genuinely no `Latitude`/`Longitude` column, confirming the ticket's premise. `setGlobalHotelsMappings()` (`mapper.js`) does hardcode `latitude: "Latitude", longitude: "Longitude"`, but simulating `pruneMappingSelectionsToParsedFields()` (added earlier this session, after the CSV workflow batches) against the real field list in Node showed both get stripped correctly, while `state: "StateProvince"` (a genuinely real field) is correctly kept. Also fetched the real Pizza Hut demo CSV — its header literally is `address,city,state,zip,phone,id,longitude,latitude`, so that preset's identical-looking hardcoded values are all real columns needing no pruning. Both known sources of a "state"/"Latitude"/"Longitude" mismatch are covered. Guarded by a new regression test verifying the prune call exists, runs in the correct order (after the preset, not before), and is wired for the global-hotels branch specifically.
  - **RVW-04 (`'str' object has no attribute 'get'`) — investigated extensively, NOT reproduced in current code; flagged rather than guessed at.** Traced every `raw_record`/`errors`/`components` JSON-decode site that could plausibly produce this: `list_rejected()` and `_fetch_rejected_by_keys()` (both wrap `json.loads()` in try/except and leave the value as whatever it was on failure, but every consumer downstream — `raw_value()` in `reporting_quality_summary()`, `normalize_reprocess_row()` in `reprocess_rejected()`, the `isinstance(raw_rec, dict)` guard in `auto_repair_error_batch()`, `_row_error_listing()`'s `first_error = row_errors[0] if row_errors else {}` — already checks `isinstance(..., dict)` before calling `.get()` on it). Live-verified `list_rejected()`'s real output already returns `raw_record` as a proper decoded dict. Also traced the review-queue edit-and-retry submit path (`review.js`'s `submitEditRecordBtn` handler) — it builds a fresh plain JS object from form inputs (`updatedRaw[rawKey] = input.value`), not a re-serialization of a possibly-malformed stored value, so a partial edit can't produce this either. **Needs an exact repro step from the user** (which record, which action) since static analysis across every candidate site didn't find an unguarded call — this may be pre-existing bad data in one specific stored row rather than a code path bug.
  - **TPL-01 / TPL-02 — root-caused and FIXED, after two prior failed static-analysis attempts this session.** User confirmed via OQ-1 that every template always has a real `business_id` (backend can't store one without it), so Load/Review should never need brand context at all — and asked for the button to read "Review" everywhere, never "Load". The actual bug: `syncPreParseWorkspace()` (`mapper.js`) relocates DOM nodes — including `#newBrandFields`, the brand-creation form — between panels whenever the mapper toggles between its pre-parse and mapping layouts, but it only ever toggles the surrounding *panel's* hidden state, never the form's own. If a user had opened the brand-edit form earlier in the same page session (leaving `#newBrandFields`'s own `hidden` class removed) and then later opened Template Library and clicked Review, the form rode along still-visible through the relocation and reappeared — even though nothing on the Review path ever asked to open it. This only reproduces on a *second-or-later* interaction in a session, which is exactly why two prior static read-throughs of `loadTemplateIntoEditor()` in isolation missed it: the bug is in leftover state from an unrelated earlier action, not in the Review path itself. Fixed by having `loadTemplateIntoEditor()` unconditionally force `#newBrandFields` hidden and reset `brandEditMode`/`presetCreateMode` to false, regardless of their prior state. Also (TPL-02): the button now reads "Review" from creation (previously started as "Load" and relabeled to "Review" only after first use), and its busy state now reads "Reviewing" instead of "Loading". Guarded by 2 new contract tests. Frontend-only, no restart needed. **User asked me to restart the server and re-verify live** — done (see below); flagging for the user to click-test in a real browser session that included an earlier brand-edit interaction, since that's the specific precondition this fix targets and a static/curl check can't fully exercise it.
  - **Still open from Wave 1, not yet investigated this batch**: SMP-02 (sample load hangs at 94%).
  - **New (2026-09-09, live user feedback) — numeric-field validation now clears instead of blocking.** User hit `⚠️ Seating Capacity: Field 'seating_capacity' value 'Springfield' could not be parsed as a valid type.` and asked, generically ("not just this column"): for a field that can never legitimately be a string (capacity, rating, amount, etc.), clear it and let enrichment try, rather than rejecting the whole row. Confirmed every field `validate_source_row()` checks (`FIELD_VALIDATORS`: latitude, longitude, seating_capacity, annual_revenue, average_ticket_size, daily_footfall, monthly_footfall, rental_cost, lease_cost, population_density, average_household_income, competitor_count, foot_traffic_score, opening_date, observed_at) is **optional** in the registry, and `normalize_location()` already calls the identical validator (`optional_int`/`optional_float`/`optional_date`/`optional_timestamp`) and stores `None` when it fails — `validate_source_row()` was *also* independently flagging the same failure as a blocking error, rejecting the whole row over one field that was already being handled gracefully and can't be "fixed" by rejecting it (there's no way to enrich a real seating capacity out of "Springfield"). Fixed: `validate_source_row()` (`data_validation/fields.py`) now always returns `[]`. Updated 4 tests across `test_csv_workflow.py`/`test_reprocess_fields_guard.py` that guarded the old blocking behavior (including two `test_save_mapper_guard.py`-style fixtures that used a bad *latitude* to construct an "invalid" row — switched to a bad ZIP, which is still a genuine hard-blocking rule in `validate_normalized_location()`, since a bad coordinate no longer blocks either). Full regression: 208 passed, 1 (the same pre-existing `bad_row_index` bug). Server restarted.
  - **New (2026-09-09, live user feedback) — header polish, three rounds.** (1) `.header-account-actions` (How this works / Log out) changed from stacked to side-by-side (How this works left, Log out right) to save vertical space, now that it wraps to its own row. (2) `.header-data-actions`'s Reset Fields Mapping slot (hidden outside Mapper per MAP-05) left an empty, "orphaned" gap in its `grid-template-areas` since hiding an item doesn't remove its reserved named slot — new `.reset-mapping-hidden` modifier class (toggled in `switchView()` alongside the existing button-hide) collapses the layout to let Restart Mapping span the freed column instead. All guarded by new contract tests.
  - **New (2026-09-09) — created_at/updated_at now format to the second everywhere they're shown.** Two display sites found: the Template Library table (previously raw ISO string with fractional seconds) and the brand-select dropdown's "created" label (previously date-only via `toLocaleDateString()`). New shared `formatTimestamp()` (`common.js`) applied to both; `data-sort-value` still uses the raw ISO string so chronological sorting is unaffected. Confirmed (unprompted, via live tracing) that `created_at` is never overwritten on update (the `UPDATE ... SET updated_at = CURRENT_TIMESTAMP()` path never touches `created_at`) and `updated_at` does change on every template update — both already correct, no backend change needed.
  - **New (2026-09-09) — FLT-05 built: searchable brand dropdown.** New shared `attachSearchableSelect(selectId, {threshold, minChars})` (`common.js`) — the same "build once" component the user's own ticket asked for, rebuilding real `<option>` elements on input (not CSS-hiding them, since a native `<select>`'s open dropdown doesn't reliably respect `display:none` on options cross-browser). Wired to `brandSelect` in `loadBrands()` with `threshold: 15, minChars: 1` (the user explicitly asked for 1 character for this dropdown, overriding FLT-05's own written spec of 2 - noted as an intentional per-instance override, not an inconsistency). **Not yet done**: retrofitting FLT-02 (competitor-brand checklist search) and FLT-03 (geo filter search) to use this same shared function instead of their own bespoke implementations — left alone since they already ship and are tested; flagged as a low-priority followup consolidation, not attempted this batch to avoid regression risk on working code.
  - **Investigated, not a code fix — user's "loaded Dominos twice, no merge option, is content_hash weak?" question.** Traced `CONTENT_HASH_FIELDS` (`warehouse_bigquery.py`): `business_id` is hashed first, by design (TPL-04: "Scope: brand_id") — content_hash is a strong SHA-256 over ~35 real normalized fields, not weak. Loading identical data under the *same* existing brand would correctly dedupe. Since it didn't, the second Dominos load must have created a *second, separate brand* (a new `business_id`) — meaning the real gap is DAT-04 (duplicate-brand-name prevention), not yet built, not a hashing weakness. User has since described a concrete desired flow for this (auto-detect on `/app` load, surface one-by-one in the mapper's left rail with a name/ID/created-at hover, dedupe the brand dropdown) — **not yet built, needs scoping** (see open items below).
  - **Investigated, confirmed a real gap — MAP-08 (mapping-size learning persistence).** User asked directly whether `source_fields` learning is now durably wired to BigQuery. Answer: no — `field_discovery_learning` (`sqlite_cache.py`) exists **only** in the local SQLite cache, never pushed to BigQuery, despite MAP-08's explicit requirement ("store in a durable table... cache DB fronts it for speed" — i.e. BigQuery should be the system of record, SQLite the accelerator). Since SQLite lives on Render's ephemeral disk (the same root cause diagnosed for RPT-13), this data is lost on every restart, defeating "reuse across sessions." **Not yet fixed** — needs a BigQuery table + write path added alongside the existing SQLite write in `record_field_discovery_gap()`.
  - **User decisions received on the two open items above**: RPT-08's "AI Review Pending" should be **computed once at write-time** (a new column, set when a row enters/re-enters error_listings) rather than reused from `is_ai_enriched` or computed live — "but all should be lightweight." DAT-04's merge action should **remap silently as one admin transaction** (rewrite `business_id` on the losing brand's listings/templates/error_listings to the winning brand's id, log it as one deliberate operation, soft-delete the losing brand). **Neither built yet** — next up.
  - **RPT-13 follow-up: fix counters STILL showed 0 on login, live-reproduced with screenshots after the earlier "fix."** Root cause of the earlier fix's gap: `refreshFixCountersOnce()` was only ever reachable through `switchView()`'s `viewId === "reviewView"` conditional branch — for whatever reason (exact trigger not fully isolated, but the backend was independently re-confirmed correct: `fixed: 58` mid-session, `authenticate()` has zero side effects on any counter, `invalidate_cache()` never touches `auto_repair_stats`), that branch didn't paint the real value on this login. Fixed by **also** calling `refreshFixCountersOnce()` unconditionally in the app boot sequence (`integrations.html`, right next to the already-proven-working `refreshReviewCount()` boot call) — regardless of which tab ends up active, exactly mirroring that call's own reasoning. Guarded by a new contract test. **Flagged for the user to re-verify live** before considering this fully closed, given the previous "fixed" claim didn't hold up.
  - **RPT-05 (Trends Over Time) — properly redesigned, not just the earlier backend column-name fix.** User correctly called out that the earlier fix ("why did you do half-baked work") only patched the `brand_name` SQL bug without ever addressing the chart's actual design: it still legended by brand (15+ colors, one per brand) instead of by metric dimension, wasn't resized, and the single-`metric` dropdown model was structurally wrong for "all metrics as separate lines" per RPT-05's own spec. Backend `reporting_timeseries()` rewritten: always returns all 4 metric-dimension series (`Locations`, `Errors`, `AI Fixed`, `Manual Fixed`) aggregated across whichever brands are filtered (a filter now, never a grouping key) — replacing the old "pick one metric, split by brand" model. Two real bugs caught and fixed *before* shipping (found while writing the redesign, not after): `quality_fix_events` has no `business_id` column at all (fixed/manual-fixed series now join through `error_listings` on `event_id`+`row_number` to reach the brand, same pattern `_refresh_quality_fix_metrics_from_bigquery()` already uses) and no `fixed_at` column (it's `created_at`) — both would have reproduced the exact "Trends Over Time empty" symptom from the earlier batch if shipped uncaught. Also: finest granularity is now always DAY (was HOUR for the 1D period — explicit "granularity till day level only" ask). Frontend: legend recolored by fixed metric-name (not a reassigned-per-view brand palette), chart resized 720×175 → 1100×340, the now-meaningless single-metric `<select>` removed, a lone single-bucket dataset now renders as a dot instead of two identical-looking axis-end date labels. Cache key bumped to `v2` (shape changed). Tested: rewrote `test_reporting_timeseries_cache.py` (8 tests, including two that specifically assert the two just-caught column bugs by SQL-text inspection, not just fake-row content) + 1 new frontend contract test. **Still not done**: physically moving the section to tab 1 (Location Intelligence) — flagged, not attempted this batch given the scope of also relocating "Top States by Coverage" (RPT-06) and "Extended Coverage Metrics" (RPT-07), which are wired together through the same `loadExtendedMetrics()`/`loadTrendChart()` call chain and should move as one unit, not piecemeal.
  - **Later batch of live UI fixes (all tested, all shipped):** source-parser half of the mapper's left rail now hides in template-review mode (new `source-parser-only` marker class + `#mapperView.template-edit-mode` scope, set in `loadTemplateIntoEditor()` and cleared at all 3 `templateEditMode = false` sites) — repeatedly reported, previously planned but never actually implemented; both reporting tabs now place their heading/description block in the same spot (Data Quality's moved inside `.dq-main` to match tab 1, and tab 1 gained the equivalent intro it was missing); `created_at`/`updated_at` display to the second everywhere via a shared `formatTimestamp()`; Most Impacted States shows full state names via the existing global `stateCodeToName`; unmeasured coverage metrics (ZIP/coordinate completeness, duplicate rate, stale records) now render "—"/"No data" instead of a fabricated "0.0% — Needs attention"/"Healthy" verdict on a coverage query that returned nothing (INV-15, same root as the 2,866,500% bug); Issue Type donut rebuilt with an aligned 4-column legend grid (swatch/label/count/percent, tabular-nums) and slice↔legend hover linking; hoverable per-bucket points added to both the Trends Over Time and Historical Quality charts, with axis labels trimmed from full ISO timestamps to plain dates. Edit-record modal now builds its field list from the record's **own saved template mapping** (looked up by `business_id` — live-verified that `template_id` is frequently null, so gating on it skipped the lookup entirely) instead of the Mapper tab's live UI state, labels mapped raw columns by their registry label, and sorts flagged fields first — this is why a field the error named (e.g. "Seating Capacity") was never findable in the form. That lookup also surfaced a genuine data problem worth flagging: the Dominos template maps **two different target fields to the same source column** (`seating_capacity` → `city`, alongside `city` → `city`), which is what produces the "Seating Capacity: 'Agawam'" error and directly violates INV-4/MAP-04's 1:1 rule — the mapping itself needs repairing, not just the error display.
  - **Enrichment metric definitions wired to the user's stated meanings (backend).** Audited each against what the code actually computed: **Entity-resolution attempts/success** were already correct (COUNT of `fix_type='AI'` events / COUNTIF improved) — added the missing `entity_resolution_failure_rate_pct` so the failure half can't drift from the success half. **ZIP completeness** counted any non-empty string; now requires a *usable* code (5-digit US, or an alphanumeric non-US postal code). **Coordinate completeness** counted merely non-null lat/lon; now requires present **and valid** (in-range, and not the 0,0 null-island placeholder). **Duplicate rate** partitioned on `(business_id, address, zip)`; now partitions on `content_hash` (the canonical dedup key — `business_id` is already baked into it per `CONTENT_HASH_FIELDS`), falling back to the old identity only for rows written before the hash existed. **Stale records** was hardcoded to `INTERVAL 90 DAY`; now a **persisted, user-configurable threshold** — new `app_settings` key/value table + `get_stale_after_days()`/`set_app_setting()` in `sqlite_cache.py`, a `GET`/`POST /api/settings` endpoint, a "Stale after (days)" control in the Data Quality filter rail, and a `?stale_days=` per-request override for previewing a window without changing the saved value. Changing it calls the new `invalidate_quality_cache()` (not `invalidate_cache()`, which now deliberately spares `reporting_quality:*` keys) so the numbers actually recompute against the new threshold. Live-verified end to end: default 90 → POST 30 → GET returns 30 → out-of-range value rejected with a clear message.
  - **🚨 Found and fixed the reason EVERY coverage metric read zero — a silently-failing query, live-diagnosed.** While validating the metric definitions above, `total_records` came back 0 even though `listings` demonstrably holds 12,815 rows. Running the coverage query directly (the app swallows it in a broad `except` that only logs) surfaced `400 Unrecognized name: event_id`. The query selected **four columns that don't exist on `listings`**: `event_id`, `coordinate_source`, `coordinate_confidence`, and `state` (it's `state_code`). So the query had been failing on *every single run*, silently zeroing ZIP/coordinate completeness, duplicate rate, stale records, required-field completeness, geo-enrichment, provenance, traceability **and the overall DQ score** — the same "column doesn't exist, swallowed into a silent zero" class as the earlier `brand_name` and `qf.business_id` bugs. Fixed against real columns: `event_id`→`ingestion_id`, `state`→`state_code`, `coordinate_source`→`enriched_at IS NOT NULL` (the actual enrichment signal on this table), `coordinate_confidence`→genuine coordinate validity (in-range, not null-island) rather than an invented confidence score.
    Two further bugs surfaced once real numbers finally flowed: (a) **ZIP completeness still read 0.0%** because the regex quantifiers `{5}`/`{2,9}` sit inside an **f-string** — Python consumed them as format fields and the pattern silently became `^[0-9]5$`, matching almost nothing; escaped to `{{5}}`/`{{2,9}}`. (b) **`invalid_record_rate_pct` read 280%** and `valid_location_rate_pct` a bogus 100% (inflating the DQ score to 93.85), because invalid rows live in `error_listings` and valid rows in `listings` — two different populations being divided by each other; both now use everything-ingested as the denominator. Live-verified end state: `total_records 12815, zip_completeness 99.33%, coordinate_completeness 99.57%, entity_resolution 268 attempts / 44.78% success / 55.22% failure, invalid_record_rate 73.69%, valid_location_rate 26.31%, overall_dq_score 79.11` — all real, all internally consistent, none over 100%. Guarded by 3 new tests (column-existence against `TABLE_SCHEMAS`, f-string brace preservation, and rate ceilings).
  - **UIX-07 (both reporting sidebars share one design) + "Live" text removed from both.** The Data Quality filter rail's CSS now mirrors the Location Intelligence sidebar's spec exactly (single-column stack, same card padding/border, same 11px/600 label and control type scale, same heading treatment) instead of being a separate 2-column design with its own type scale; the `Report Filters • Live` pseudo-element text and tab 1's blue "Live" badge are both gone. RPT-07 also done: Extended Coverage Metrics moved directly beneath the first number-card block.
  - **Fixed a pre-existing test-isolation bug surfaced by the full-suite run.** `test_reporting_timeseries_cache.py` passed standalone but failed 7 ways in a full-suite run with `module 'google.cloud.bigquery' has no attribute 'QueryJobConfig'` — several other suites inject a fake `google.cloud.bigquery` into `sys.modules` and, on cleanup, leave the real namespace package degraded. Fixed the same way every other affected suite here already handles it: the timeseries tests now inject their own fake module via a small mixin, removing the ordering dependency. **Full suite: 312 passed, 1 failed** (only the long-documented pre-existing `bad_row_index` bug) — was 8 failed before this fix.
  - **DONE — d3.js migration (all four charts) + number-card hover download.** d3 v7.9.0 is **vendored locally** at `ui/vendor/d3/` (with its LICENSE), matching the existing leaflet/topojson pattern rather than a CDN, so charting works offline and adds no third-party runtime dependency. It loads *inside* the existing AMD-define guard — verified necessary: d3's UMD preamble checks `define.amd` first, so outside the guard it would register with Monaco's AMD loader instead of defining `window.d3`. New shared helpers in `reporting-tabs.js`: `renderTimeSeriesChart()` (real `scaleTime`/`scaleLinear` axes, gridlines, a hoverable point per bucket, `curveMonotoneX` lines, single-bucket padding so one point doesn't collapse onto the axis) and `chartTooltip()` (one cursor-following tooltip per chart container). All four charts rebuilt on it: **Trends Over Time** and **Historical Quality** now share the one helper (so they can't drift apart again), **Issue Type Breakdown** uses `d3.pie()`/`d3.arc()` with arc-expansion on hover and slice↔legend linking, and **Top States by Coverage** uses `scaleBand`/`scaleLinear` with animated bars, real axes and tooltips. Each renderer degrades honestly with "Charting library failed to load" rather than rendering nothing if d3 is somehow absent. **Number-card hover download**: every `.dq-card` shows a "⬇ CSV" button on hover; a `metricDatasets` registry (repopulated each `loadQuality()`) hands over the *rows behind* the figure where a real breakdown exists (Invalid listings → issue-type rows, Needs manual review → per-brand rows, Active issue types → issue-type rows) and otherwise the figure plus the active filter context — never a fabricated row set. One delegated click listener, since cards re-render on every refresh. Guarded by 2 new tests (vendoring + AMD-guard placement + every renderer using d3; download wiring) and the 3 existing chart tests updated from asserting hand-rolled SVG internals to asserting the d3 implementation while keeping the regressions they originally guarded. Live-verified: `vendor/d3/d3.min.js` serves 200 (279,706 bytes) and the tag is present in the served page. **Full suite: 317 passed, 1 failed** (only the long-documented pre-existing `bad_row_index` bug).
  - **Still open / explicitly not done (flagged rather than half-built):** (1) **Relocating Trends Over Time / Top States by Coverage / Extended Coverage Metrics to tab 1** (RPT-05/06/07) — repeatedly raised and still not done; the three are cleanly decoupled from the slow quality payload (they read `/api/reporting/summary` + `/api/reporting/timeseries`) so they can move together, but Historical Quality (RPT-04) is fed by the quality payload's `history` and needs its data flow reworked before it can follow. (4) RPT-08's four-state cards + pivot, now unblocked by the user's "compute at write-time, keep it lightweight" decision. (5) DAT-04 brand-merge, now unblocked by the "remap as one admin transaction" decision.
  - **New structural fix — Data Quality tab now has real cache resilience, not just a cold-start band-aid.** User asked directly "why did tab 1 load but Data Quality not, even with enough time — is mirroring not in place?" Correct diagnosis: Location Intelligence reads dedicated gold-mirror SQLite tables, untouched by the generic cache wipe; Data Quality only had the opaque `query_cache` blob cache, which `invalidate_cache()` (no-key form) wipes **entirely** on *any* save/reprocess/reset anywhere in the app — forcing the next Data Quality view back into a full cold BigQuery recompute, which (as the error-listing count has grown 21k→28k→36k+ this session) was likely now exceeding the earlier fix's 40s retry budget. Fixed: `invalidate_cache()` (`sqlite_cache.py`) now exempts `reporting_quality:*` cache keys from its blanket wipe, since `reporting_quality_summary()` already re-warms itself in the background on every read of a warm entry (its own `should_refresh`/`_QUALITY_REFRESH_KEYS` logic) — it doesn't need external invalidation to eventually reflect a new save. Also bumped the frontend's retry budget (20×2s=40s → 40×3s=2min) and, for the genuinely-rare case that's still not enough, replaced the old silent "render the all-zero placeholder as final data" fallback with an honest "taking longer than usual, try refreshing" status.
  - **New in the user's updated backlog doc (superseding the version above)**: MAP-10 (restore the unsaved-mapping session on "Continue Without Saving", server-side persisted keyed on user+brand+source, reusing the existing Restart Mapping rehydration path — OQ-9 needs confirming what Restart Mapping currently restores before this can be built correctly), FLT-05 (brand dropdown becomes searchable above a 15-option threshold — explicitly the same component as FLT-02/FLT-03, build once with a threshold prop, not a third implementation), and a new §13 Data Model & Persistence Layer: DAT-01 (stop interactive single-row BigQuery DML writes — write to the operational/cache DB synchronously, flush to BigQuery async via Storage Write API, nothing on the request path waits for BigQuery), DAT-02 (one generic `save`/`update`/`get`/`bulk_upsert`/`exists` data-access layer parameterized by entity, so connection handling/timing/cache-invalidation are each implemented once), DAT-03 (two-tier duplicate detection: exact `content_hash` on a normalized+versioned+ordered field list, then a weighted ~70%-similarity fuzzy tier bucketed by ZIP/city to avoid O(n²) — blocked on OQ-6 defining "non-common fields" precisely), DAT-04 (prevent duplicate brands by normalized-name match with a DB-level unique constraint — blocked on OQ-7 scope-of-uniqueness and OQ-8 a deliberate admin merge path for existing duplicates, since BRD-03 makes each record's brand link immutable). The suggested execution order also moved DAT-01+DAT-02 earlier (into Wave 2, before JOB-09/JOB-01/JOB-05), reasoning that the connection handling in JOB-06, the timings in JOB-08, and the cache invalidation in RPT-13 each need one place to exist, not three.
- **Fifth batch (2026-09-09, new items only — the rest of that message was a re-send of the third/fourth batches, already covered above)**. Everything below is tracked so nothing gets lost; items marked FIXED were addressed same-session, the rest are open.
  - External enrichment validation for brand name/email/website/phone via an open API, wired through the same BQ+SQLite-cache path as every other enrichment metric, counted under AI Fixed on real adoption - **not built**. User wants a manual data-test proving a record that's easily enrichable actually gets enriched and the counter moves, "no fake data."
  - Review Queue needs an AI-Reviewed vs Manual-Review filter dropdown so high-confidence AI suggestions can be triaged separately - **not built**.
  - Validation error hints show raw field keys (e.g. `opening_date`) instead of a human-formatted column name in the Action column - **not fixed**.
  - **New Template Library bug - the "stuck on Loading" half is FIXED**: `loadTemplateIntoEditor()` runs synchronously but nothing ever called `clearButtonBusy()` afterward, so the clicked row's Load button stayed disabled reading "Loading" forever, even after navigating back to the tab later. Fixed: the button is restored and relabeled "Review" (still clickable, so re-opening the same template to check its mapping is one click). The other half - a brand-creation form allegedly still popping on Load click - was investigated but not reproduced from static analysis: `loadTemplateIntoEditor()` always sets `selectedBrand` to a truthy object (falls back to `{business_id, name: "", ...}` even when no match is found) before `switchView("mapperView")` runs `renderMappings()`, and the auto-open guard added earlier this session (`if (!selectedBrand) openBrandEditorForm(...)`) should already prevent it firing in that case. Needs live browser reproduction to pin down further, since nothing in the code path explains it as read.
  - Reporting page's own top heading ("Reporting") renders larger than intended relative to Template Library's equivalent - wants it smaller, with more explanation moved into the subtitle text instead - **not fixed**.
  - **Chart/metric bugs in this session's own new Data Quality additions - both root-caused and FIXED, live-verified via curl against the running server, not just re-wired blindly**:
    - **"Trends Over Time" was empty because of a real backend bug**: the "locations" metric query in `reporting_timeseries()` selected `brand_name` directly from the bronze `listings` table - but `listings` has no such column (only `business_id`; brand comes from a join to `businesses`, which the sibling errors/fixes queries already did correctly). Against this environment's BigQuery this silently returned zero rows into `_collect()`'s broad `except Exception` (logged as a warning, no error surfaced) rather than raising - exactly the "empty, no error" symptom reported. Fixed by joining `businesses` the same way the other two metrics already do. Verified live: `metric=locations` went from `"series": []` to real per-brand counts (17 brands, non-zero) after the fix and a forced cache refresh.
    - **"Top States by Coverage" was empty because of a frontend field-name bug**: `renderTopStatesBar()` read `row.zip_count ?? row.count`, but the real `top_states` payload (confirmed live) uses the field name `locations` - neither `zip_count` nor `count` ever existed on it, so every bar always evaluated to 0. Fixed to read `row.locations` (and use `state_name` for the label, falling back to `state`).
    - **"Quality by Brand" AI Fixed vs. Review Queue "Fixed Automatically" - investigated, found to be an intentional (if confusing) semantic split, not simply "broken wiring"**: the per-brand column is a *live* count of currently-active `error_listings` rows with `is_ai_enriched=True` (rises and falls as rows enter/leave review), while the top-level card reads `auto_repair_stats.fixed` - a cumulative, monotonic counter that is itself already periodically reconciled *from* the authoritative `quality_fix_events` log (`_refresh_quality_fix_metrics_from_bigquery()`, throttled to once/60s, but force-refreshed immediately after every `reprocess_rejected()` call). So the reconciliation pipeline the user asked to check does already exist and isn't obviously broken - the two numbers are answering different questions ("how many AI fixes ever happened" vs. "how many AI-fixed rows are still sitting in the queue right now") and will diverge by design once any fixed row leaves review. Unifying them into one definition is a real product decision (which definition wins), not a code fix - flagged for the user rather than guessed at.
    - "Trends Over Time" legend should be by metric type (locations / errors / AI-fixed / manual-fixed counts), not by brand.
  - **Requested restructuring** of the Data Quality tab's newer sections (all **not done**): move "Historical Quality & Change Tracking" (made into a real interactive 1W/1M/1Q/1Y line chart, multi-line per competitor when added) to tab 1 (Location Intelligence); move "Trends Over Time" and "Top States by Coverage" to tab 1 too; move "Extended Coverage Metrics" up to right after the first ~3 rows of the existing number-card grid, instead of near the bottom.
- **Sixth batch (2026-09-09)**:
  - **New: field-mapping confidence scoring ("advanced AI kinda mapping")** - a genuinely new adaptive-learning feature, not a bug fix. Per explicit user spec: an auto-suggested mapping the user *keeps* scores +1, *switches to a different mapped field* scores +0.5 (partial credit against the original suggestion), *switches to unmapped* scores -0.5, and a *fresh manual pairing with no prior suggestion at all* scores +1 (how a brand-new field like "cuisine type" first builds confidence). Implementation:
    - `ui/js/mapper.js`: `originalAutoMapping` is an immutable snapshot of `mappingSelections` taken right after auto-mapping settles post-parse (unlike the existing `autoMappedKeys`, which loses entries as soon as the user touches them, so it can't be diffed against the final save). `computeMappingConfidenceEvents()` diffs that snapshot against the final mapping at save time; sent once per save (not once per batch) as `mapping_confidence_events` in the `/api/save` payload.
    - `whitespace_tool/sqlite_cache.py`: new `field_mapping_confidence` table (`target_key`, `source_field_normalized`, cumulative `score`, `sample_count`) - `record_mapping_confidence_events()` upserts (accumulates, never overwrites), `get_mapping_confidence()` reads back sorted by score. `source_field_normalized` collapses casing/punctuation so "Cuisine Type" and "cuisine_type" earn into the same row.
    - `save_mapper()` records the events (wrapped in try/except so a tracking failure can never break a real save); `learn_mappings()` (`/api/learning`) now layers confidence-earned suggestions on top of the existing template-vote suggestions for any target field the votes didn't already cover - requires `score > 0` and `sample_count >= 2` before a pairing gets suggested, and only when its normalized name actually matches one of the current source's real parsed fields.
    - Confirmed **field_registry.json → BigQuery push already existed** before this session (`field_catalog()` seeds BigQuery's `field_catalogs` table from `load_field_registry()` on first use, and tops up any newly-added standard fields on later calls) - no new work needed for that part of the ask.
    - Tested: `unit_tests/test_field_mapping_confidence.py` (13 tests, run and passing) covering score accumulation, independent per-target tracking, malformed-event handling, the diff-logic rules standalone, and the `learn_mappings()` merge (gap-filling, score/sample-count gating, source-not-present gating).
    - **Not yet done**: no UI surface for this data yet (no admin/debug view of `get_mapping_confidence()` - `get_field_discovery_gaps()` from the prior batch is in the same boat); the merge into `learn_mappings()` is the only consumer today, so the score doesn't yet influence anything beyond that one endpoint's suggestions.
  - Header separator removed between `.header-data-actions` (Sync US ZIPs etc.) and `.header-account-actions` (Log out, How this works) - was a `border-left` on `.header-account-actions`.
  - **Validation error field names now formatted**: `whitespace_tool/data_validation/fields.py` built hint strings with the raw registry key (`Field 'opening_date' value ... could not be parsed`) - added `FIELD_LABELS`/`_field_label()` (backed by the registry's own `label`) and used it in all three hint sites (type mismatch, missing-mandatory, standardized-type mismatch). Frontend: new shared `formatFieldLabel()` in `common.js` (same transform as reporting-tabs.js's existing local `formatIssue`) applied to the bold field name in Review Error Listings' Action column, so both the bold label and the hint text now read "Opening Date" instead of `opening_date`.
  - **Review Queue AI-Suggested vs Manual-Review filter added**: new `#reviewFixTypeFilter` dropdown, filtering client-side on the already-fetched page of records using the exact same `recordHasSuggestionAvailable()` heuristic that colors each row's action button (extracted into one shared function so the filter and the button color can never disagree).
  - **Reporting page heading resized** (30px → 20px) to stop dwarfing Template Library's equivalent `<h2>`, with more explanation moved into the subtitle paragraph below it instead of the oversized title carrying it.
  - **Demo XLS restaurant "HTTP Error 400" - investigated, could not reproduce.** Ran the exact live pipeline directly against the running server for the real `demoRestaurantExcelUrl` (a published Google Sheets XLSX link): `/api/source-url` fetch (2.1MB content, succeeded), `/api/sheets` discovery (`["Sheet1"]`), and `/api/preview` (9825 records, 20 correctly-detected fields including `cuisine`, `restaurant_name`, etc.) all completed successfully end-to-end with no error. Most likely a transient Google Sheets hiccup (rate-limit or momentary unavailability) at the time it was hit, not a deterministic bug in `fetch_public_source()`/`excel_source.py`. If it recurs, capture the exact response body/status from `/api/source-url` at the time - `_remote_source_request()` (workflow_server.py) doesn't currently distinguish "URL down" from "URL blocked us" from "malformed response" in its error message, which would help narrow it down (though the URL is Google-hosted publish-to-web, not something this app can control the availability of).
  - **Unsaved-parse navigation guard added**: `pendingUnsavedParse` (mapper.js) is set on a successful parse and cleared on a successful save or a workspace reset. The top-nav tab click handler (`integrations.html`) now checks it before leaving the Mapper tab for another tab - if set, it opens a new `#unsavedChangesDialog` (standard `.app-help-dialog` theme) offering Save Listing Data / Continue Without Saving / Cancel, instead of silently discarding a parsed-but-unsaved mapping.
- **Seventh batch (2026-09-09) — out-of-US coordinate handling, now DONE** (was listed as still-open under the Fourth batch). Per the user's spec: try the US reading first, and only if nothing resolves in US terms, enrich against the worldwide reference, offer an explicit "save as non-US" action, count it under AI Fixed, and make sure the same record doesn't come back asking the same question.
  - `whitespace_tool/data_validation/fields.py`: `validate_normalized_location()`'s US-boundary check now exempts a record whose `country`/`country_code` is explicitly set to something non-US. This is the piece that stops the loop — once the user accepts the non-US reading, `country` is populated, so the next validation pass no longer flags "coordinates outside US boundary." A record with a *blank* country is still flagged exactly as before (deliberate: blank means "unknown," not "non-US").
  - `reprocess_rejected()` (`workflow_server.py`, repeat-failure path): after the existing `enrich_raw_listing_row()` + `detect_hierarchy_conflict()` US-first passes, if the coordinates fail `is_us_land_coordinate()` it calls `find_nearest_worldwide_city()` and returns the match as `result["non_us_suggestion"]` (city/state/country/country_code/zip_code/distance_km). Never auto-applied — the whole block is wrapped in try/except so an enrichment failure can't break the reprocess response.
  - `ui/js/review.js`: new `renderNonUsSuggestion()` renders a "🌍 These coordinates look like real data outside the US (~N km away): City, State, Country" box above the edit form with a single **Save as Non-US Data** button. Clicking it sets `suggestionAdopted = true` (so the subsequent `/api/reprocess` sends `is_ai_enriched: true` and the fix lands under **AI Fixed**, not Manual) and fills city/state/country/postal_code. This is the third `suggestionAdopted` trigger, alongside the ZIP quick-fill and the hierarchy-conflict picker.
  - Tested and **run**: 2 new tests in `unit_tests/test_csv_workflow.py` (non-US country exempts the boundary error; blank country still flags it), 2 new tests in `unit_tests/test_review_ai_resolution.py` (`non_us_suggestion` attached when outside US / `find_nearest_worldwide_city` not even called when inside US), 1 new contract test in `unit_tests/test_mapping_layout_contract.py` (explicit button, no auto-apply, `suggestionAdopted` set, wired to `result.non_us_suggestion`). Full run of those files plus `test_geo_enrichment.py`: **116 passed**, 1 failure — the unrelated pre-existing `bad_row_index` bug below. Server restarted and confirmed serving 200.
- **Eighth batch (2026-09-09, large re-sent list — deduped against prior batches). Two items in it were already closed and need no further work:** the field-registry confidence-scoring layer (built in full in the Sixth batch above, 13 passing tests) and the header separator near Log out / Sync US ZIPs (removed in the Sixth batch; `.header-account-actions` carries no `border-left` today — only a now-redundant `border-left: 0` reset left over in the mobile media query). Everything below is genuinely new and **open**:
  - **FIXED — reporting filter fonts now in sync.** There is only one filter sidebar (shared by both reporting tabs), so the real mismatch was *within* it: the Brand Filters heading hand-copied `.report-filter-category-title`'s styling inline (and so lost the class's `display:flex`/`gap`), and its label/select carried different padding, weight and background from the Geographic and Demographic ones. Added two shared classes (`.report-filter-label`, `.report-filter-control`) and replaced all 17 divergent inline style blocks with them, so the groups can't drift apart again. Guarded by `test_reporting_sidebar_filters_share_one_label_and_control_style`.
  - **FIXED — type-to-search after 2 characters on the competitor-brand and geographic filters.** `setupGeoFilterSearch()` (`ui/js/reporting.js`) inserts a search box above each of State/County/City that narrows the select's options once 2+ characters are typed; the blank "All X" option and the current selection always survive the filter, so searching can never strip out an active selection. The option cache is refreshed inside `loadGeoOptions()` *before* re-applying the search, so a repopulate can't discard what the user typed. The competitor dropdown gets a matching search field in its sticky toolbar which **hides** (never removes) non-matching rows — a checked-but-filtered-out brand has to stay in the DOM to keep counting as selected. Guarded by `test_geo_and_competitor_filters_search_only_after_two_characters`.
  - **RESOLVED — "Edit brand details" duplication.** Both existing surfaces turned out to live in the same left-rail aside (there's no separate 40/60-main-pane one): `#editExistingBrandLink` (a `.text-link` under the brand dropdown) and `#presetBrandEditBtn` (a button inside the CSV-preset panel) — confirmed they call the identical underlying flow (`fillBrandFields()` opening the shared `#newBrandFields` form). Per explicit user decision after being asked to confirm this, `#editExistingBrandLink` is now force-hidden via a dedicated `#editExistingBrandLink { display: none !important; }` CSS rule (its markup/JS click handler are untouched, so it isn't lost) — `#presetBrandEditBtn` and the unrelated `preParseEditBrand` radio ("Edit a brand" mode selector, a different control entirely) are unaffected. Guarded by `test_edit_existing_brand_text_link_is_force_hidden_but_not_removed`.
  - **FIXED — Job History "Show More" now opens a paginated popup.** The panel previously had no "Show More" at all — a fixed `fetch("/api/jobs/recent?limit=10")` with no way to see older jobs. Backend: `get_recent_save_events()` (`sqlite_cache.py`) gained an `offset` param, plus new `count_save_events()`; `/api/jobs/recent` now accepts `offset` and returns `total` alongside `jobs`. Frontend: `renderJobHistoryRow()` extracted as a shared renderer for both the panel and the popup; new `#jobHistoryDialog` (`.app-help-dialog` themed, same convention as the other dialogs) with Previous/Next paging 20 rows at a time via `loadJobHistoryDialogPage()`; the panel's own "Show More" link only appears when `total` exceeds what the panel already shows. Tested and run: `JobHistoryPaginationTests` (3 tests, `test_job_history.py`, offset pages don't overlap and cover every row, most-recent-first holds across pages) + a new frontend contract test. Live-verified via curl: `/api/jobs/recent?limit=5&offset=0` returns `"total": 59` with correctly paged rows.
  - **FIXED — auto-repair now yields to real foreground activity.** New `LAST_FOREGROUND_ACTIVITY_AT` (`workflow_server.py`), stamped once per genuine user `do_POST` action (parse/save/reprocess/etc — explicitly *not* the worker's own `/api/review/auto-repair` start call or `/api/enrichment/stop`, and never by GET polling like `/api/enrichment/status`, so the frontend's own 2s status poll during a run can't make the worker think it's busy). Before every batch, `start_auto_repair()`'s loop checks `FOREGROUND_IDLE_GRACE_SECONDS` (10s) of quiet since the last real action and sleeps out the remainder if activity was recent — best-effort, so waiting longer is always an acceptable outcome. Most of the "never hangs the 512MB free tier" half of this ask was actually already done earlier this session (single reused `bigquery.Client` per run, batch size 10, targeted `_fetch_rejected_by_keys()` instead of unbounded fetches — see "Current Audit" above) — this batch adds the missing "pause when something else needs priority" piece. Tested and run: 2 new tests in `test_memory_leak.py` (sleeps out the grace period when activity was just seen; does not wait when already idle) + the pre-existing 3 auto-repair resource tests, all passing (5/5).
  - **Enrichment fairness (round-robin across brands): FIXED.** `claim_enrichment_batch()` (`sqlite_cache.py`) claimed `ORDER BY listing_id`, so cycles spent their early passes on whichever brand's ids sorted first — switched to `ORDER BY RANDOM()` (same fix logged above under the "Fix with AI" item, since it's the identical root cause and code path). **Resource hygiene (BQ-direct, minimal cachedb/connection pressure): not further changed this batch** — already uses `get_db_connection()`'s context-manager pattern everywhere (closes on every call, no held-open connections) and a single reused BigQuery client per repair run; going further (bypassing the SQLite queue table entirely in favor of a pure-BigQuery cursor) would be a larger architectural change than this ask's wording implies and risks the exact "don't hallucinate, don't break things" line this close to closure — flagging rather than guessing at a rewrite.
  - **FIXED — save progress is now dismissible.** The blocking full-screen overlay (`#loadingOverlay`) never had a working way to dismiss it during a save — its existing Cancel button only appears when the caller passes an abort handler, which `setProgress()` never did. Added a second, distinct **"Hide — notify me when done"** button (`#loadingHideBtn`, blue, deliberately not styled like Cancel since it doesn't abort anything — the save keeps running, batch by batch, exactly as before). Clicking it sets `saveProgressHiddenByUser` (`common.js`), which makes every subsequent `setProgress()` tick a no-op (both the overlay and the inline sticky `#saveProgress` banner) until the save finishes and `hideProgress()` resets it. While hidden, a synthetic "Saving in the background…" row (`showBackgroundSaveNotice()`/`clearBackgroundSaveNotice()`, `mapper.js`) sits at the top of the Job History panel; `hideProgress()` clears it on both the success and failure paths, right before the real save result replaces it via the existing `loadJobHistory()` call. On completion, `showSaveCompletion()`'s message was also rewritten to name the brand and source type (`"Acme Pizza csv: 7342 read, 7180 saved, 162 need review (AI will attempt the best fixes)."`) instead of bare counts, since it now has to stand on its own if the user only sees it after dismissing the loader. Guarded by `test_save_progress_can_be_hidden_and_continues_reporting_via_job_history`; the two pre-existing tests asserting the old message string/offset were updated to match. Frontend-only change, no server restart required; full regression across all touched-file suites this session: 159 passed, 1 (the same pre-existing, already-documented `bad_row_index` bug).
  - **CONFIRMED already fully enforced — no code change needed.** Backend: `normalize_location()` returns `None` without a brand and `REQUIRED_MAPPER_FIELDS` is deliberately empty so brand is the *only* hard requirement. Frontend: `parseSource()` (`mapper.js`) already blocks parsing itself — `if (... && !hasSelectedBusiness()) { ...; return; }` — before a source is ever read, with a validation message and focus on the brand field. Brand is mandatory end-to-end today.
  - Brand identity should be enriched via open-source/free sources (email, phone, website, and other fields already on the record). Same ask as the Fifth batch's external-enrichment item — **still not built**.
  - **Messaging audit across the whole app**: align tone and make copy product-fit rather than vague/ad-hoc.
  - **FIXED — event-id search bar length / button wrapping.** `.review-toolbar` declared only 4 grid columns for 5 controls, so "Try Auto-Fixing with AI" was pushed onto a second row, and the search input took `1fr` (greedily consuming the leftover width). Now 5 columns with the input capped at `minmax(200px, 280px)` and `justify-content: start`; placeholder shortened to match the narrower field. Guarded by `test_review_toolbar_declares_a_column_for_every_control_so_buttons_do_not_wrap`.
  - **FIXED — "Fix with AI" now picks randomised ids.** `claim_enrichment_batch()` (`sqlite_cache.py`) claimed `ORDER BY listing_id`; ids from one brand sort together, so every cycle spent its early (most-visible) passes on a single brand. Now `ORDER BY RANDOM()`. The full base set still drains either way — each row leaves `pending` the moment it is claimed — so this only changes coverage *spread*, not completeness. Guarded by `test_claim_enrichment_batch_does_not_always_pick_the_same_sorted_first_ids` (`test_geo_enrichment.py`, 21 passing).
  - **Number cards 4-way split + field pivot — deliberately NOT built yet, flagged instead of guessed.** AI Fixed and Manual Fixed map cleanly to the existing cumulative `auto_repair_stats.fixed`/`manual_fixed` counters. But "AI Review Pending" vs "Manual Review Pending" would need to split the *currently-pending* `error_listings` rows by whether an AI fix is available right now for each — and this collides directly with the ambiguity already logged under the Fifth batch ("AI Fixed vs Fixed Automatically... intentional semantic split, not simply broken wiring... a real product decision"): a pending row's own `is_ai_enriched` flag records the provenance of its *last* reprocess attempt, not "does it have a live AI suggestion today," so reusing it here would silently misclassify rows. Computing a true live suggestion-availability pivot across every pending row on each reporting load would also mean running enrichment probes over the whole queue synchronously — exactly the "must not hang the system" resource cost the batch's own enrichment-throttling ask (above) is trying to prevent. Needs a product decision on what "AI Review Pending" concretely means (e.g., a cheap proxy field on the row set at write-time, updated once per reprocess, rather than computed live) before building either the 4-way cards or the field-group pivot table.
- **Fourth backlog batch (2026-09-09, continuation of the third)**:
  - **Edit-brand-slow-to-enable fixed**: `loadAppData()` (`common.js`) was calling `renderMappings()` (which enables the brand-dependent "Edit a brand" radio) only *after* awaiting `loadTemplateLibrary()`, even though `loadBrands()` itself had already resolved in the earlier parallel `Promise.allSettled`. Reordered so `renderMappings()`/`updateOutput()` run immediately once brands are in, not queued behind an unrelated fetch - same class of fix as the earlier review-count reordering. Confirmed `presetBrandEditBtn`'s `if (!activeCsvPresetConfig) return;` is not a real bug - that whole panel is hidden unless a CSV demo preset is active, so it's unreachable otherwise.
  - **`/api/learning` now SQLite-cached** (`LEARNING_TEMPLATES_CACHE_KEY`, `get_cached_query`/`set_cached_query` - the same pattern used everywhere else in reporting) instead of re-querying BigQuery's `workflow_templates` on every mapping-workspace open. Cleared by the existing broad `invalidate_cache()` calls after any save, so it can't go stale.
  - **New field-discovery-gap learning table** (`field_discovery_learning` in `sqlite_cache.py`, `record_field_discovery_gap()`/`get_field_discovery_gaps()`) - `save_mapper()` now compares the full/batch row set's real fields against the discovery-time `source_fields` list and records it when the fixed-size discovery sample missed something. **Deliberately did not change `MAPPER_SAMPLE_ROWS = 50`** despite this being the likely root cause of recurring "unknown source fields" errors - it's a documented product contract ("parse samples inspect at most 50 records for discovery," stated in `CLAUDE.md`/README/this file), not a bug to silently vary. This is a pure observation/analytics layer for a future adaptive sizing decision; flag `get_field_discovery_gaps()` to the user if the recurring-error reports continue, since that's a product call about the contract itself, not an engineering fix.
  - **Store vs. Listings clarity**: confirmed these are three genuinely different real metrics, not a bug - `total_stores` (raw per-record count), `active_market_locations`/"Covered Markets (ZIPs)" (distinct ZIP count), and the map's per-record markers (same unit as `total_stores`, and already correctly geo-filtered via `fetch_mirror_reporting_locations(state, county, city, zip)` before reaching the map). Added `title` tooltips to both KPI cards and a one-line caption under the map's legend explaining the unit difference, rather than changing any number.
  - **Reporting sidebar filter spacing tightened**: `.report-filter-group` padding 12px→8px, inter-category margins 16px→10px, section-divider padding 12px→8px, header divider 14px/10px→10px/8px - concentrated in the CSS/inline styles the earlier investigation flagged, without touching the grid layout itself.
  - **Still open from this batch**: demo XLS restaurant `HTTP Error 400: Bad Request` (not yet reproduced/diagnosed); unsaved-changes navigation guard; out-of-US coordinate handling (worldwide-enrich-first, then an explicit "save as non-US" action counted under AI Fixed); the `.top-tabs`/`.header-data-actions` overlap (waiting on a user screenshot); a full README.md tone/readability pass for a non-technical audience (the in-app "How this works" dialog got this treatment already this batch, README.md itself has not).
- **Pre-existing bug found 2026-09-09 (not caused by this session, not yet fixed):** `save_mapper()`'s `bad_row_index` check (`workflow_server.py`, ~line 5836-5842) rejects the *entire* batch with a `ValueError` if any single row isn't a dict, instead of routing just that one malformed row to error_listings and continuing with the rest. `unit_tests/test_csv_workflow.py::test_save_mapper_routes_bad_rows_to_error_listings_without_halting_valid_rows` still expects the old per-row behavior and fails against current code. This predates this session (from earlier "review reprocess hardening" work) — needs a product decision on intended behavior before fixing either the code or the test.
- Run-over-run change tracking needs snapshot history.
- Authenticated browser smoke coverage should exercise login, source demos, parse/save/review, reporting filters, sample load/clear, and logout.
- Backend module extraction is still needed around source parsing, brand/template management, reporting, and enrichment queues.
- Demo metadata should be reconciled so README/config/UI all describe the same current demos.
- The smoke matrix and PPT-ready walkthrough live in `docs/smoke_test_and_presentation.md`. Last confirmed clean run: 192 passing. 248 tests now collected after this session's additions — a portion (see the batches above) has only been `py_compile`-verified, not run with pytest yet; re-run the full suite before quoting a new passing count anywhere.
- A fresh upload smoke run must use new CSV, Excel, JSON, XML, GET JSON, and Python fixtures; parse may inspect at most 50 records, but save must verify the complete source count.
- Root serves the centered entry screen, `/login` is the secure route, and `/app` is the authenticated workspace. Refresh preserves the active view when the session remains valid; unauthorized and not-found flows return to login/not-found handling.
- The current reporting model supports US-wide, state, county, city, and ZIP analysis. It does not yet provide true metro-area boundaries or historical snapshot diffs.
