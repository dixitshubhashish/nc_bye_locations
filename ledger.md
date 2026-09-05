# Development Ledger — `develop` branch

Running record of the work done on this repository's `develop` branch by Claude
(this assistant), across sessions. Entries are grouped by theme and ordered
oldest to newest within each group; commit hashes refer to `develop` at the
time this ledger was written. Commits authored by the project owner
(`Shubhashish` / `Shubhashish Dixit`, including the "antigravity" tool) are
mentioned only where relevant for context — this ledger tracks Claude's
contributions.

## 1. Mapping & data-integrity audit fixes

- `98f6d9a` Fix reporting map, de-duplicate metrics, fix head-to-head order,
  normalize name casing.
- `fc53187` Self-host Leaflet map assets and always render state boundaries
  (removed a dependency on an unreliable CDN for the map).
- `5ccd7fb` Split `integrations.html`'s single ~2,900-line inline script into
  per-tab modules (`ui/js/common.js`, `mapper.js`, `reporting.js`, `review.js`,
  `templates.js`) for maintainability.
- `173e0c8` Add a `window.L` compatibility shim after vendoring Leaflet.
- `d341dd8` Fix the real root cause of the Leaflet map not loading: a
  Monaco AMD loader conflict clobbering Leaflet's global.
- `047b020` Show 2-letter state codes on the map instead of full state names.
- `782ef52` Restyle location markers as small solid dots, colored blue when
  no brand is selected (previously ambiguous marker styling).
- `39976fd` Remove fabricated fallback numbers from reporting KPIs and data
  quality — the UI no longer silently substitutes made-up values when real
  data is missing.
- `6cb5108` Fix a dead-code provenance bug and confusing obfuscation found
  during a full-repo audit.
- `9703cc3` Fix a persisted-template security bug found in the same audit;
  clean up related dead code.
- `3b426c2` Always land on the Mappings tab right after login (was landing
  on a stale/inconsistent tab).
- `cea32dd` Add "Drop Custom Field", mirroring the existing "Add Custom
  Field" flow (custom field lifecycle was previously add-only).
- `7103dcb` Fix null source values silently becoming the literal string
  `"None"` instead of staying empty during ingestion.

## 2. Medallion architecture (bronze/silver/gold) build-out

- `4b45e67` Add the gold layer, an hourly silver/gold rebuild scheduler, and
  content-hash based dedup for listings.
- `e0329ee` Rename sample-data brands away from the real assessment brands
  (Domino's, Pizza Hut, Little Caesars) to fictional equivalents (Starlight
  Pizza Co., Crimson Slice, Pinnacle Pizza, ...) so synthetic demo data is
  never confused with real assessment data; sped up the bulk sample load.
- `d342dca` Fix gold-layer reporting bugs, a gold/silver sync gap, and the
  "Clear sample data and reload" flow getting stuck.
- `f0f72a6` Auto-load the Template Library on tab open, surface real
  gold-bootstrap errors instead of a misleading generic message, tint the
  reporting filters for visual separation from the metrics.
- `cf5ee63` Fix the Template Library search bar's collapsed input, resolve
  business/source-type names instead of raw IDs, improve reporting loading
  UX.
- `5c82495` Add a "ratings" field end-to-end — field catalog, `LocationRecord`
  model, normalization, bronze schema, content-hash — plus sync new standard
  fields into an existing field catalog without requiring a full reset.
- `30db3c6` Move the reporting status/loading indicator directly under the
  "Refresh Report" button instead of a full-window overlay.
- `d279b44` Give competitor brands a proper "Select competitor brands"
  default line (previously blank); verified brand loading end-to-end with
  Playwright.

### Gold-layer cleanup and a local fast-read path

- `d2de2a7` Prune 8 unused gold-layer views from both code and BigQuery
  (`vw_state_summary`, `vw_city_summary`, `vw_listing_quality_summary`,
  `vw_geo_reference`, `vw_reporting_totals`, `vw_reporting_state_brand`,
  `vw_reporting_city_brand`, `vw_reporting_zip_summary`) — none of them could
  answer a multi-brand, distinct-zip query without double-counting, so
  `reporting_summary()` always bypassed them anyway.
- `195f1fd` Add a local SQLite mirror of the surviving gold views
  (`vw_zip_brand_activity`, `vw_reporting_locations`, active businesses) for
  fast local filtering, synced on a write-through basis (hourly tick,
  on-demand background refresh, and first bootstrap all call the same
  `_rebuild_gold_and_mirror()` choke point). `reporting_summary()` now serves
  from the mirror when it's populated and falls back to live BigQuery
  otherwise, with the JSON response shape kept byte-identical either way.

## 3. Sample-load performance

- `bd473b6` Skip redundant BigQuery schema-check (`get_table`/`create_table`)
  round trips for tables with zero rows during sample load —
  `push_to_bigquery()` gained an opt-in `skip_empty_table_checks` flag,
  cutting ~45 pointless API calls out of the 15-brand sample load that was
  causing the "stuck at 94% for a couple of minutes" symptom. Also
  reconfirmed the 3 real assessment brands remain excluded from
  `SAMPLE_BRANDS`.

## 4. Review Error Listings & Template Library UX fixes

- `f9b2718` Auto-load Review Error Listings on tab open (previously required
  an empty manual search) and make the Edit & Retry modal always show the
  required brand/name/address/city/state/ZIP inputs, keyed to the mapper's
  real mapped path, even when the raw JSON row didn't happen to contain that
  key (common with sparse JSON/XML/API sources).
- `cc36ca8` Include required main fields (name, ZIP, etc.) in the pre-parse
  "Available optional fields" picker — it was filtering out every
  `required: true` field even before a source was parsed, when that picker
  is the only place any field is visible at all.
- `0b7a870` Stop silently swallowing error-listings cleanup failures: the
  reprocess-and-move-to-listings flow now reports `rows_updated`/`ok` on the
  soft-delete step instead of a bare `try/except` + log warning, so a retry
  can no longer claim "moved to listings" while the stale error row secretly
  survives and keeps counting. Removed BigQuery time-partitioning from
  `listings`/`error_listings` (was adding DML friction for no real benefit
  at this data volume — both are now plain tables). Extended `search_zips()`
  to return each ZIP's real latitude/longitude (already stored in
  `us_zipcodes`, just not previously selected) and wired the Edit & Retry
  modal's ZIP suggestions to fill those real coordinates too, instead of
  only the ZIP/city/state text fields.
- `1aba0ad` Fix the Review "Search Records" button getting stuck on its
  spinner, and the Template Library table intermittently failing to render,
  both caused by the same root cause: `login-hotfix.js` loads asynchronously
  and can call `switchView(activeTab)` at a different time than
  `integrations.html`'s own bootstrap script, which calls it unconditionally
  too — so an already-logged-in page load can trigger `loadRejectedRecords()`
  (or `loadTemplateLibrary()`) twice concurrently. Both loaders now guard
  against concurrent re-entry with an in-flight promise. Reproduced and
  confirmed fixed with Playwright (button stuck on spinner with the table
  already rendered correctly underneath, on the old code; clean single fetch
  and correct end state on the fix).
- `436c4ed` Save both the template definition and the listing data after
  editing a loaded template. `saveMapper()` previously had an early return:
  once a template was loaded from the library, clicking "Save Template and
  Listing Data" only patched the template's stored mapper config and never
  ran the real `/api/save` pipeline — so editing a loaded template's field
  mapping and saving silently never touched actual listing data. Fixed by
  always updating the template definition first, then also running the save
  pipeline against any parsed source rows (with `save_template: false` on
  that call, since the template row is already in sync and would otherwise
  get a duplicate). Verified with Playwright against both the old code (0
  `/api/save` calls) and the fix (1 call each, correct combined status
  message).

## Notes / known follow-ups

- The BigQuery partitioning removal (`0b7a870`) only affects tables created
  fresh going forward — an already-provisioned live project's
  `listings`/`error_listings` tables stay partitioned until they're dropped
  and recreated, which wasn't done here since it's destructive.
- `reprocess_rejected()`'s multi-row path (`row_offset` forced to `0` when
  reprocessing more than one row at once) can produce colliding
  `row_number`s for newly-created error rows if a batch retry still fails
  validation. Not currently reachable from the UI (the Edit & Retry modal
  only ever reprocesses one row at a time), so left as-is, but worth
  revisiting if bulk reprocessing is ever added.
- Every change above was validated against the full `unit_tests/` suite
  (123 tests passing as of the latest commit) and, for UI-facing changes,
  against a live headless-Chromium run via Playwright with mocked `/api/*`
  routes, since this sandbox has no live BigQuery access.
