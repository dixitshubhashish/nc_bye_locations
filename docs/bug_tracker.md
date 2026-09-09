# Bug Tracker — live status

Single flat list. Every entry has an ID of the form `BUG-N`, numbered
sequentially across the whole file. There are no per-area, per-severity or
per-status sections — status is a **field on the entry**, so the list can be
scanned, grepped and appended to without deciding where something belongs.

**How to use this file**

- Find an entry: `grep -n "^### BUG-42" docs/bug_tracker.md`
- Find an old identifier: `grep -n "Previously: BB14" docs/bug_tracker.md`
  (every pre-2026-09-10 ID — `BB*`, `B*`, `O*`, `U*`, `RULE R0`, `DAT-*`,
  `RPT-*`, `INV-*`, `FLT-*`, `Q*` — is preserved on its entry, because
  `codex.md`, code comments and past sessions reference them.)
- Add a new entry: append at the end of the list with the next free number.
  Do not renumber existing entries; the IDs are referenced elsewhere.
- Add detail to an existing entry: extend its body. Keep the field block at
  the top intact.

**Entry format** — a `### BUG-N — <title>` heading, then these fields, then
free-form detail:

| Field | Meaning |
|---|---|
| `Status:` | `FIXED` · `PARTIAL` · `OPEN` · `IN PROGRESS` · `NEEDS DECISION` · `WON'T FIX` · `NOT A BUG` · `REFERENCE` |
| `Previously:` | the old identifier(s), or `—` if it never had one |
| `Area:` | rough subsystem, for reading only — **not** a grouping |
| `Reported:` | date or round it came from |

Detail for each fix also lives in `codex.md`'s batch entries.

**Verification commands** are not duplicated here. The canonical list is in
`CLAUDE.md` ("Pre-commit verification") and `codex.md`; the executable
wrappers are in `scripts/` — see `scripts/README.md`. Run
`scripts/check-syntax.sh` before finishing a change and `scripts/run-tests.sh`
to exercise the suite.

---

## SESSION HANDOFF — read this first

**State:** 518 tests green (`.venv/bin/python -m pytest unit_tests/ -q`, ~5s).
Coverage **53%** overall, `workflow_server.py` **48%** — measured 2026-09-09,
not estimated. Nothing committed since `fcbd0ab`.

**`.py` changes are NOT live — a restart is required** (not taken; standing
rule). Pending in `workflow_server.py`: merge preview, failed-save job event,
idle location enrichment, `GET /api/review/fix-states`, the rate-limited
`_invalidate_cache_background()`, and legacy-tolerant dedupe. Plus new
`brand_enrichment.enrich_location_contact()` and the `CONTENT_HASH_FIELDS`
change in `warehouse_bigquery.py`. **Until the restart, the UI fixes that
depend on `/api/review/fix-states` will 404** — the review cards keep showing
"-" until the server is restarted.

**Standing rules (do not violate):**
- Do NOT commit or push unless explicitly asked.
- Do NOT restart the server unless explicitly asked.
- Do not fabricate numbers. Measure, then state. If unmeasured, say so.
- A message starting with `URGENT` jumps the queue.

**One known flaky test:** `test_sample_loader_prepares_zips_before_existing_sample_refresh`
fails only in slow (~85s) runs where it reaches the network; it passes in the
normal ~4s run. Not a real failure — do not "fix" it by weakening the test.

### Open work, in priority order

| # | Item | Notes |
|---|------|-------|
| 1 | **Brand-merge weighting in enrichment (Q8)** | Still queued, untouched. |
| 2 | **Test coverage** | **53%** overall, `workflow_server.py` **48%** (4151 statements / 2150 missed). Re-measured 2026-09-09 — the ~110 tests added since the 52% reading moved it one point, because `workflow_server.py` dominates the count. Only tests aimed at that file will move this. Re-run with `.venv/bin/python -m coverage run --source=whitespace_tool -m pytest unit_tests/ -q && .venv/bin/python -m coverage report`. Never quote a figure without running it. |
| 3 | **Cross-brand duplicate signal (was O2 / BUG-22)** | The `content_hash` approach is impossible — `business_id` is inside the hash. Needs (a) a physical-identity hash excluding `business_id`, computed warehouse-side, and (b) a product call: is a shared street address evidence of a duplicate brand, or a shared strip mall? |
| 4 | **Semantic-clearing refill, second source** | `_idle_location_enrichment_pass()` covers phone/website/email from OSM by coordinates. Other kinds semantic cleaning clears (rating, money, year, boolean) have no external source yet and stay blank — blank being a true statement, not a gap to paper over. |

---

## Bugs

### BUG-1 — Duplicate brands ("Domino's Pizza" twice) shown in the brand dropdown
Status: FIXED · Previously: B1 · Area: brands/UI · Reported: 2026-09-09

Only one survivor per similar-name group reaches `brandSelect`; the rest go to the left rail. A currently-selected duplicate stays visible so the user's own selection is never blanked.

### BUG-2 — Brand duplicate detection never ran on `/app` load
Status: FIXED · Previously: B2 · Area: brands/UI · Reported: 2026-09-09

`loadAppData()` → `loadBrands()` → `duplicateBusinessGroups()` → `renderDuplicateBrandRail()`.

### BUG-3 — Merge option was never offered
Status: FIXED · Previously: B3 · Area: brands/UI · Reported: 2026-09-09

New "Duplicate Brands" panel in the 40% left rail, one group at a time, hidden when nothing to merge.

### BUG-4 — Brand match required byte-identical names
Status: FIXED · Previously: B4 · Area: brands · Reported: 2026-09-09

Dice-coefficient bigram similarity at **≥75%**. Verified: `Dominos Pizza` vs `Domino's Pizza Inc` = 0.85 (merge); `Little Caesars` vs `Little Caesar's LLC` = 0.86 (merge); `Pizza Hut` vs `Domino's Pizza` = 0.38 (no merge).

### BUG-5 — Brand id / listing count / created_at cluttered the option text
Status: FIXED · Previously: B5 · Area: brands/UI · Reported: 2026-09-09

Detail is hover (`title`) only; visible text stays short. Newest vs oldest marked in the hover.

### BUG-6 — Two competing merge UIs
Status: FIXED · Previously: B6 · Area: brands/UI · Reported: 2026-09-09

Old "Similar Brands" block inside the Active Brands box removed; the rail owns merging.

### BUG-7 — Data Controls lost its ⚠️ warning sign
Status: FIXED · Previously: B7 · Area: UI · Reported: 2026-09-09

Restored on the panel heading and the clear-confirm dialog. The amber `.data-danger-panel` styling was never removed — only the sign had been.

### BUG-8 — Donut/metrics stayed outdated after 5+ minutes on the page
Status: FIXED · Previously: B8 · Area: reporting · Reported: 2026-09-09

A warm-but-stale cache was served while a background thread recomputed — and **nothing ever asked for the result**. Server now returns `refreshing: true`; the page re-fetches (max 3×, 6s apart) and re-renders.

### BUG-9 — The four fix counters "reset to zero"
Status: FIXED · Previously: B9 · Area: reporting/enrichment · Reported: 2026-09-09

Not a data loss and **not** a mirroring failure — verified live: BigQuery `quality_fix_events` = AI 124 / Manual 4, SQLite mirror = exactly the same, `/api/enrichment/status` returns them correctly. The bug was `state.auto_repair?.fixed || 0`: **any** status response omitting `auto_repair` rendered all four as 0, wiping correct numbers off screen. Absent data now leaves the displayed values alone.

### BUG-10 — Hiding parser progress left the post-parse workspace up
Status: PARTIAL · Previously: B10 · Area: mapper/UI · Reported: 2026-09-09

Returns to the 40/60 pre-parse layout (done). **Still open:** see BUG-21.

### BUG-11 — Review action buttons ("AI Suggested Fix" / "Manual Review") did nothing on click
Status: FIXED · Previously: B11 · Area: review · Reported: 2026-09-09

Per-button listeners were bound right after `enableSortableTable()`, which rebuilds the tbody on sort — detaching them. Replaced with one delegated listener on the container that survives any re-render, re-bound per load so handlers don't stack.

### BUG-12 — AI action had a generic lightbulb icon
Status: FIXED · Previously: B12 · Area: review/UI · Reported: 2026-09-09

Now 🤖 (AI); Manual Review keeps 🛠️.

### BUG-13 — `reviewActionHandler is not defined` on the review queue
Status: FIXED · Previously: B13 · Area: review · Reported: 2026-09-09

My own regression: the declaration landed *inside* the preceding function (between its `finally` and its closing brace), so it was function-scoped and invisible to `loadRejectedRecords()`. Moved to module scope; a test now asserts brace-depth 0. The empty-queue path also detaches the handler instead of returning early and leaking the old closure.

### BUG-14 — Template review let the business be changed, and the top tab jumped to Mapping
Status: FIXED · Previously: B14 · Area: templates · Reported: 2026-09-09

A saved template cannot exist without its `business_id`, so the brand is a fact, not a choice — all three brand pickers are locked while editing (released everywhere `template-edit-mode` ends). Top nav stays on Template Library.

### BUG-15 — Data Model unusable past ~100 columns
Status: FIXED · Previously: B15 · Area: mapper/UI · Reported: 2026-09-09

Search box + independent vertical scrolling (`max-height: 60vh`) above a 100-field threshold; below it the plain list is kept. Search matches the raw column **and** its mapped label ("zip" finds `address.postcode`), and filters both columns so the pairing stays aligned.

### BUG-16 — Merge picker didn't show which record was new vs old
Status: FIXED · Previously: B16 · Area: brands/UI · Reported: 2026-09-09

The picker now shows `BID · N listings · Newest/Oldest · created <date>` inline (a decision needs visible basis, unlike the dropdown where detail was clutter), plus a stated recommendation.

### BUG-17 — One click produced many Excel download attempts
Status: FIXED · Previously: B17 · Area: export · Reported: 2026-09-09

The `<a href=server-url>` was removed from the DOM immediately after `.click()`, which makes some browsers re-issue the request. Now one guarded `fetch` → blob → single save, with an in-flight set that blocks double-clicks and a busy state on the button.

### BUG-18 — Export was a bare .xlsx; large filters failed
Status: FIXED · Previously: B18 · Area: export · Reported: 2026-09-09

Now a **ZIP**: workbook + `listings.csv` + `metrics.csv` + `competitors.csv` + `README.txt` (naming the filters that produced it). Filters accept **multiple** values (`IN UNNEST`) instead of one scalar — "20 states" silently matched nothing before. Row ceiling raised 50k → **200k**, and hitting it is reported as `PARTIAL RESULT`, not passed off as complete.

### BUG-19 — Export had no competitor view
Status: FIXED · Previously: B19 · Area: export · Reported: 2026-09-09

Third sheet + `competitors.csv`: per-brand listings, share %, states, cities, ZIPs, coordinate/ZIP completeness — derived from the same rows as sheet 1, so they always reconcile.

### BUG-20 — "Top States by Coverage" rendered as one solid block
Status: FIXED · Previously: B20 · Area: reporting/charts · Reported: 2026-09-09

`container.clientWidth` is 0 while the panel is hidden, so `Math.max(360, 0 || 900)` built a 900px viewBox the browser then scaled up. Now waits for a real width via `ResizeObserver`. Bars also got a sequential colour ramp and the track a contrasting tone — one flat blue on a near-identical track was the "same background" confusion. (See also BUG-31 and BUG-61: same root cause, three times.)

### BUG-21 — Background save after hiding progress
Status: FIXED · Previously: O1 · Area: mapper/jobs · Reported: 2026-09-09

Traced end to end. Success was already announced (dialog + `loadJobHistory()`); **failure was not**. `record_save_event()` ran only after a successful `push_to_bigquery`, so a failed save produced **no Job History row at all** — indistinguishable from never having started. Now recorded on the failure path too (`mapped_rows=0` + rows present is what already derives `FAILED`), narrowly around the push so an argument-validation raise still never becomes a job. The UI now pops the themed dialog and refreshes Job History when a *dismissed* save fails — the old inline `#status` line was invisible after `resetMapping()` returned the user to the pre-parse layout.

### BUG-22 — `content_hash` near-duplicate dedupe
Status: WON'T FIX AS SPECIFIED · Previously: O2 · Area: warehouse/dedupe · Reported: 2026-09-09

Its premise is impossible. `business_id` **is** one of `CONTENT_HASH_FIELDS`, so two brand records can never share a hash — verified: the identical listing under `brand-A` vs `brand-B` yields two different hashes. `duplicateContentHashGroups()` could never have fired; removed, with the reasoning left at the call site and a test asserting its absence *and* the hash property. A real signal needs a physical-identity hash **excluding** `business_id`, computed warehouse-side, plus a product call on whether a shared street address means a duplicate brand or a shared strip mall. Both open. See BUG-87 for the later `CONTENT_HASH_FIELDS` change.

### BUG-23 — Merge user-confirmation step
Status: FIXED · Previously: O3 · Area: brands · Reported: 2026-09-09

`merge_brands()` gained `preview: true` — per-table COUNTs instead of the UPDATEs — and the rail runs it for every group before a themed confirm naming listings / templates / review rows. A table whose count can't be read reports **None**, not 0, and the dialog then shows no totals: reporting an unreadable table as zero would let it claim "nothing will move" about data that is there. Mutation-tested.

### BUG-24 — Per-table downloads (market gap, brand comparison)
Status: FIXED (was stale in this tracker) · Previously: O4 · Area: reporting/export · Reported: 2026-09-09

`data-table-export` buttons are live on Top States, Top Cities, Brand Comparison and Market Gaps, served by `/api/reporting/table-export`.

### BUG-25 — Extended Coverage Metrics panel
Status: FIXED (was stale in this tracker) · Previously: O5 · Area: reporting · Reported: 2026-09-09

The panel is gone; `loadExtendedMetrics()` now serves only the Top States chart, with the reasoning kept as a comment at `ui/reporting-tabs.js:784`.

### BUG-26 — Idle-time enrichment loop
Status: FIXED (differently than specified) · Previously: O6, Q9 · Area: enrichment · Reported: 2026-09-09

The plan was to refill from `raw.__meta.semantically_cleared_fields` — but **that breadcrumb never reaches the warehouse for a valid listing**: `listings` has no `raw` column (57 columns, verified); only `error_listings.raw_record` keeps it. So the refill is driven off the blank column itself. New `enrich_location_contact()` queries Overpass **around the listing's own coordinates** and requires a shared meaningful word with the POI name, so a neighbour can't donate its phone number; a name-matched POI with no contact tag isn't an answer either. `_idle_location_enrichment_pass()` fills only blanks and **re-asserts the blank-only guard in SQL**, so a concurrent user edit wins. Shares the existing `brand-enrichment` thread rather than adding a second idle worker.

### BUG-27 — Five dialogs off the Birdeye shell
Status: FIXED · Previously: B22 · Area: UI/dialogs · Reported: 2026-09-09

`pythonConnectorDialog`, `editRecordDialog`, `dangerDialog`, `masterDeleteCredentialsDialog`, `masterDeleteConfirmDialog` all moved onto `<dialog class="app-help-dialog"> > .app-help-content > .app-help-header > <h2 id>`. Three modifier classes carry the difference: `--editor` (1200x800), `--form`, `--danger` (red border/rule/title, so destructive stays visibly destructive). Both retired frames (`connector-editor-dialog`, `danger-dialog`) deleted from the CSS; every dialog gained `aria-labelledby`. The test walks every `<dialog>` in the markup and asserts the retired names appear nowhere.

### BUG-28 — Sample load "always stops at 94%"
Status: FIXED · Previously: B21 · Area: sample load/UI · Reported: 2026-09-09

It was never stuck. The bar was `Math.min(94, elapsed / estimate * 100)` — a pure time guess (15s/25s) hard-capped at 94, so any slower load parked there until the fetch returned. It measured nothing. Now shows the estimate only while it is still an estimate, then switches to an honest `Ns elapsed - larger batches take longer, this keeps running`. Trailing `...` removed per the spinner rule. Confirmed the loader already skips a failing brand (`except → continue`) and, since the `bad_row_index` fix, routes malformed rows to review rather than aborting — so nothing is blocking additional data.

### BUG-29 — `/api/reporting` and `/api/reporting/quality` could hang forever
Status: FIXED · Previously: B54 · Area: server/concurrency · Reported: 2026-09-09 (server wedged during verification)

Caught live: the running server answered static files, `/` and `/api/session` in **under 3ms** while those two endpoints timed out past **180s** — no error, nothing in the access log, 18 threads, 65MB RSS, 166 FDs, so not a leak or a pile-up. Cause: `_heavy_request.__enter__` called `_HEAVY_REQUEST_SEMAPHORE.acquire()` with **no timeout**. `HEAVY_REQUEST_CONCURRENCY` is 3, so once three requests wedged inside, every later caller queued behind them permanently. Now bounded by `HEAVY_REQUEST_WAIT_SECONDS = 45`, raising `TimeoutError`, which the existing handler already turns into a "busy, refresh shortly" response. **Verified: 6 concurrent `/api/reporting` calls all return 200 in ~10s** (previously 3 was enough to take the endpoint down until restart); warm calls are 10ms.

**Diagnostic worth keeping:** when this app appears "stuck", check which endpoints are affected before assuming a slow query. Static files and `/api/session` responding instantly while only the heavy reporting endpoints hang points at the concurrency gate, not at BigQuery or SQLite. `reporting_summary()` measured **1.6s cold / 0.0s cached** out-of-process at the same moment the HTTP endpoint was hanging, which is what ruled the query out.

### BUG-30 — `/api/sample/status` spawned a thread per poll
Status: FIXED · Previously: B55 · Area: sample load/server · Reported: 2026-09-09

The mirror-backed status endpoint kicked off a background recount — six BigQuery COUNTs, each on a **fresh client**, since `_bigquery_client()` is a plain factory and not a cache — on *every single call*, and the UI polls it. Throttled to at most one recount per 60s.

### BUG-31 — Master delete leaked a BigQuery client per dataset
Status: FIXED · Previously: B52 · Area: warehouse/master delete · Reported: 2026-09-09

This is the "where are we leaking it all". `drop_dataset_tables()` built a **brand new `bigquery.Client` on every call and never closed it** — and the master delete calls it three times (bronze, silver, gold). That is precisely the pattern `codex.md` already records as the cause of a prior gRPC socket/OOM leak. It now accepts the caller's memoised client (`master_delete_data()` passes one for all three datasets), and only closes a client it created itself.

### BUG-32 — Master delete dropped 21 objects one at a time
Status: FIXED — 4.3x · Previously: B53 · Area: warehouse/master delete · Reported: 2026-09-09

21 objects across the three datasets, one sequential HTTP round trip each. Now deleted concurrently on a bounded `ThreadPoolExecutor`. **Benchmarked on a throwaway dataset (never the live warehouse): 14 objects, 7.4s → 1.7s.**

**A wrong turn worth recording.** The obvious fix looked like collapsing the deletes into one multi-statement `DROP` script — one job instead of N round trips. **Measured, it was SLOWER: 9.4s vs 8.1s for the same 14 objects.** A BigQuery *query job* carries seconds of fixed scheduling overhead that a REST `delete_table` does not, so batching cheap calls into one job made it worse. Concurrency was the actual answer. The test asserts `client.queries == []` so nobody re-introduces the batching idea on intuition.

### BUG-33 — Two silver builds at once corrupt each other
Status: FIXED · Previously: B50 · Area: silver layer · Reported: 2026-09-09

Surfaced live as `400 Destination deleted/expired during operation: birdeye_silver_listings._listings_staging`. `build_silver_layer()` writes a **fixed** staging table and DROPs it, so two concurrent builds destroy each other's destination. Only **2 of 5** call sites took `REPORTING_REFRESHING`; the sample load, the clear worker and the gold bootstrap did not — so clicking **Load Sample Dataset while a background refresh was running** collided, the build failed, and gold stayed stale. That is one of the ways reporting ends up disagreeing with the warehouse. Now serialised on `_SILVER_BUILD_LOCK` at the single public entry point, with the query body moved to `_build_silver_layer_impl()`.

### BUG-34 — …and the first version of that fix deadlocked
Status: FIXED · Previously: B51 · Area: silver layer · Reported: 2026-09-09

A plain `threading.Lock` hung the whole test suite: `_ensure_gold_reporting_views()` calls `build_silver_layer()` as part of its bootstrap, so the nested same-thread path blocked on itself. Changed to `RLock` — reentrancy costs nothing (a nested call on one thread is already serialised) and the cross-thread collision it exists to stop is still blocked. Worth recording because the hang is what caught it: the suite went from 4s to never finishing.

### BUG-35 — NTILE(2) half-split removed
Status: DONE · Previously: B48 · Area: sample load · Reported: 2026-09-09

User: "if full sample dataset load can happen quick we dont need that split into 2 parts, it should not stuck". Measured, they were right: a **single INSERT over all 22,500 rows runs in ~3s across 17MB**, so the split bought nothing — while costing a background thread that **re-entered `load_sample_dataset()` itself**, which is how the second half's reset came to soft-delete the 11,250 rows and every business the first half had just written (`businesses: 0 live`, observed). One statement now, no `load_half`, no background thread, no half-loaded failure mode. The INSERT stays idempotent, so a load interrupted by a restart tops up rather than duplicating.

### BUG-36 — 8 DDL statements re-run on every load
Status: FIXED · Previously: B49 · Area: sample load/warehouse · Reported: 2026-09-09

User spotted it in the job log: `ALTER TABLE … ADD COLUMN IF NOT EXISTS is_deleted/deleted_on` across 4 tables, ~4s each — roughly **30 of a 47-second load** spent proving columns exist. They are in `TABLE_SCHEMAS`, so on any table this app created they are already there; the ALTERs are only a safety net for tables predating them. Now memoised per process via `_ensure_soft_delete_columns()`, cleared by `_forget_ensured_tables()` so a clear/master-delete still re-reconciles. The `UPDATE` still runs every time.

**On "make a copy of the table / mutate then re-immutable it":** not needed, and worth being precise about — **those ALTERs were on `birdeye_bronze_listings`, not `sample_locations`.** Bronze is ours to mutate freely. `sample_locations` was never the problem: its schema is fully compatible (51 columns, no type mismatches), and the fault was a query selecting a column it does not have. **No copy was made and the immutable-source guard was never lifted.**

### BUG-37 — The real 22,500-row sample dataset has never loaded
Status: FIXED · Previously: B43 · Area: sample load · Reported: 2026-09-09

Reported as "entire sample dataset is not loading". It was worse than partial: **zero** of it had ever loaded. The INSERT selected `COALESCE(s.validated, FALSE)`, but `sample_locations.listings` has no `validated` column, so BigQuery rejected the **entire statement** — `Name validated not found inside s at [17:43]` — and the `except` around it fell through to the in-memory generator and returned success. Proof the two are different datasets: bronze's sample rows are `sample_business_crimson_slice_csv` / "Crimson Slice Austin 12" (15 demo brands), the source is `biz_brand_0887` / "Brewer Roastery #18447" (1,000 synthetic brands), and **all 22,500 source `listing_id`s were absent from bronze**. What looked like a 41%-loaded sample (9,295 of 22,500) was a different 9,295-row generated set standing in for it. Fixed to `FALSE AS validated` — the source carries no validation state, and freshly ingested rows being unvalidated is the honest value.

### BUG-38 — A hard ingest failure was logged as a warning and reported as success
Status: FIXED · Previously: B44 · Area: sample load · Reported: 2026-09-09

The silent fallback is what let BUG-37 survive the whole life of the feature: a total failure and a clean load look identical on screen. Now `LOGGER.error(...sample_locations_ingestion_failed falling_back_to_generator...)` and the reason is carried on `sample_ingestion_error`.

### BUG-39 — One missing column could kill the whole load opaquely
Status: FIXED · Previously: B45 · Area: sample load · Reported: 2026-09-09

New `verify_sample_source_schema()` preflight names the missing columns up front instead of leaving an opaque mid-statement SQL error for a fallback to paper over. `SAMPLE_SOURCE_REQUIRED_COLUMNS` sits beside it so the two cannot drift, and a contract test cross-checks every `s.<column>` in the INSERT against the source's real schema.

### BUG-40 — "Already loaded" meant "some sample rows exist"
Status: FIXED · Previously: B46 · Area: sample load · Reported: 2026-09-09

Written when the generator was the only source, so the generator's own rows made the loader declare itself loaded and skip ingestion — the real dataset could never get in even after the SQL was fixed. Loaded now means the **source's** rows are actually present, measured against `sample_locations.listings`' own count.

### BUG-41 — Re-running a load could duplicate rows
Status: FIXED · Previously: B47 · Area: sample load · Reported: 2026-09-09

The INSERT now skips any source `listing_id` already in bronze, so a re-run (or finishing a half that died on a restart) tops up what is missing instead of inserting a second copy.

**Schema compliance verified both directions** (user asked): 51 source columns vs 57 target, **no type mismatches** on any shared column. The 6 target-only columns (`country_code`, `custom_fields`, `email`, `enriched_at`, `max_enriched`, `validated`) are defaulted by the INSERT or left NULL. **`sample_locations` did not need modifying** — permission to alter it was offered and turned out to be unnecessary, so the immutable-source safety rule stays intact.

### BUG-42 — `pytest` wiped the running app's reporting mirror
Status: FIXED — this was the real cause of "0 data" · Previously: B41 · Area: sqlite mirror/tests · Reported: 2026-09-09

`sqlite_cache.DB_PATH` was a bare constant pointing at `.cache/whitespace_cache.db` **with no test override**, and the suite exercises `clear_sample_reporting_mirror()`, `clear_local_cache_db()` and the gold-mirror swap *for real*. So every `pytest unit_tests/` run mutated the **live** application cache. This is why the dashboard kept collapsing to 0 with nothing in the server log to explain it — **the wipes were not coming from the server at all.** Proof: `mirror_meta.synced_at` was written in `CURRENT_TIMESTAMP` format (`2026-09-09 16:07:08`), which only `clear_sample_reporting_mirror()` produces — `replace_gold_mirror()` writes ISO-8601 with a `T`. And the deltas matched a sample-brand deletion exactly: zip-brand 41,882→41,585 (−297, the brand rows) and businesses 1,013→998 (−15, the sample brands). **Five orphaned pytest processes** (started 12:56, 13:02, 18:29, 19:02, 19:23) were still holding the database open and doing this hours later. Fixed with `WHITESPACE_CACHE_DB` + `unit_tests/conftest.py`, which points the suite at a throwaway file. Resolved once at import so the ~10 tests that already isolate themselves via `patch.object(sqlite_cache, "DB_PATH", tmp)` keep working unchanged. **Verified end to end: live mirror 13,803 before a full run, 13,803 after, same `synced_at`.** A guard test asserts the suite can never point back at `.cache/`.

### BUG-43 — A slow sync could commit its empty result over a newer good mirror
Status: FIXED · Previously: B42 · Area: gold mirror · Reported: 2026-09-09

The three gold reads take a minute or more; another sync (or a manual rebuild) can land a good mirror in that window, and committing the older empty result over it is a lost update. The first guard compares against the mirror at **read** time; a second check now compares at **write** time, immediately before the swap. `force=True` still lets a deliberate clear empty it.

**How to tell these apart in future:** `mirror_meta.synced_at` identifies the writer. ISO-8601 with a `T` → `replace_gold_mirror()` (the gold sync). Space-separated (`CURRENT_TIMESTAMP`) → `clear_sample_reporting_mirror()` or `clear_local_cache_db()`. If the app is losing mirror rows and the server log shows no clear call, look for another **process** — not another code path.

### BUG-44 — Reporting kept collapsing to 0 listings / 0 brands
Status: FIXED — root cause · Previously: B33 · Area: gold mirror/reporting · Reported: 2026-09-09

`sync_gold_mirror()`'s data-wipe guard was **unreachable for locations**. It read `if had_real_data and not force and not zip_brand_rows and not location_rows:` — i.e. it only skipped when **both** collections were empty. But `vw_zip_brand_activity` is a LEFT JOIN off the ZIP reference, so it returns ~41.5k rows whether or not a single brand has activity — **it is never empty**, so the conjunction could never be true and the location half had no protection at all. A gold read landing during a silver rebuild's drop-then-recreate window swapped **0 locations** straight in. Measured live: 13,803 location rows replaced by 0 while 41,585 zip rows "looked fine"; reporting then served `total_listings: 0, total_brands: 0` as a legitimate answer. Each collection is now judged on **its own** collapse from non-empty to empty, and a row count is no longer mistaken for health (`zip_brand_has_activity` checks for an actual brand). `force=True` still lets a deliberate clear empty the mirror. **After the fix: 13,761 listings, 15 brands.**

### BUG-45 — Half-wiped mirror served as real data
Status: FIXED · Previously: B34 · Area: gold mirror/reporting · Reported: 2026-09-09

`_reporting_data_from_mirror()` returned zeros whenever `get_mirror_status()` was non-null, so a mirror that had been partially cleared answered confidently with nothing. Zero location rows alongside zip-brand rows carrying real activity is a partial wipe, never a real state — it now falls back to BigQuery and triggers a resync.

### BUG-46 — Clear emptied the mirror before the warehouse
Status: FIXED · Previously: B35 · Area: sample load/mirror · Reported: 2026-09-09

`clear_sample_dataset()` cleared the local mirror first and BigQuery second, so a BigQuery failure left the worst possible state: data still in bronze and gold, nothing in the mirror. Authoritative store first now.

### BUG-47 — Nothing stopped a second sample load
Status: FIXED · Previously: B36 · Area: sample load · Reported: 2026-09-09

`/api/sample/load` had no in-flight guard, so a double click — or one landing while the automatic NTILE(2) second half was still running — started another full load, each spawning its own half-2 thread against the same rows and the same BigQuery client. Returns the in-flight status instead.

### BUG-48 — Clear raced the loader instead of stopping it
Status: FIXED · Previously: B37 · Area: sample load · Reported: 2026-09-09

Clear now raises `SAMPLE_LOAD_CANCELLED` **before** deleting, and the loader checks it between halves — otherwise the still-running loader wrote half 2 back in straight after the delete. `load_sample_dataset()` is now a thin try/finally wrapper (the implementation has 11 return statements) so the in-flight flag is always released.

### BUG-49 — Button flipped to "Load Sample Dataset" on refresh
Status: FIXED · Previously: B38 · Area: sample load/UI · Reported: 2026-09-09

`/api/sample/status` ran six BigQuery COUNTs inline on every page load, and the UI's catch did `updateSampleDatasetControls({ loaded: false })` — so any hiccup rendered "not loaded" over a loaded warehouse. Same class as BUG-9. Status is now mirrored in **`app_settings`** (not `query_cache`, which `invalidate_cache()` wipes), BigQuery re-counts in the background, a BigQuery failure serves the mirror, and the UI leaves the last known state alone.

### BUG-50 — Half-loaded looked identical to fully loaded
Status: FIXED · Previously: B39 · Area: sample load/UI · Reported: 2026-09-09

Status now compares loaded listings against the source's own row count (`sample_locations.listings`). Half → "Sample Dataset Loaded"; complete → "✓ Sample Dataset Already Loaded"; unknown source count → the weaker of the two, never a false "complete". Clear is available in both states and reads "Stop & Clear Sample Data" while a load is still running. **Measured live: 9,295 of 22,500 — a genuine half-load.**

### BUG-51 — Trailing "..." instead of the spinner
Status: FIXED · Previously: B40 · Area: UI/copy · Reported: 2026-09-09

"Removing custom field..." and 14 other sites. `busyMarkup()` now strips the single-glyph ellipsis as well as "...", and the in-progress messages route through it. Remaining `...` in the UI source are JavaScript spread syntax only.

**Not a bug — the review count of 118 is correct.** Measured in BigQuery: `error_listings` holds **395 rows total, 118 live**, against **14,499 live listings**. 118 is the count of *still-open* validation errors, not of records; 395 is every listing that was ever invalid (what the "Ever invalid (all time)" card shows). Both numbers are right and they measure different things.

### BUG-52 — "Some clicks lose the create brand form, call the unexpected one"
Status: FIXED · Previously: B23 · Area: brands/UI · Reported: 2026-09-09

**Three** flags decide what the single `#createBrandBtn` means — `brandEditMode` (Edit-brand link + pre-parse Edit radio), `presetBrandEditMode` (the CSV preset panel's "Edit Brand Details") and `presetCreateMode` — each set by a different path that opens the form. The click handler consulted only `brandEditMode`, so the preset edit path left the button on its **create** branch: saving a form showing an existing brand's details filed a **second copy of that brand**. Now dispatches on `(brandEditMode || presetBrandEditMode) && selectedBrand?.business_id`; the `business_id` check stops a stale preset flag turning a genuine create into an update of nothing. Separately, `brandSelect` change and Cancel reset **all three** flags — they reset two of three, so `presetBrandEditMode` survived into a context whose form no longer described the selected brand.

### BUG-53 — Review cards showed "–" while the donut showed 118
Status: FIXED · Previously: B24 · Area: review/reporting · Reported: 2026-09-09

Not a data loss. **Measured the live mirror**: `fix_state_counts` held `ai_fixed=110, manual_fixed=155, manual_pending=130, total=395` and reconciled exactly. The cards were read off `/api/reporting/quality` — a heavy multi-query aggregation they had to wait on **and fail with**. New mirror-backed `GET /api/review/fix-states` serves the six numbers directly; a cold mirror now returns `refreshing: true` so the page polls (bounded) instead of leaving dashes for the session.

### BUG-54 — "AI Fixed by Total Error" read 0.00% beside cards showing 110 AI fixes
Status: FIXED · Previously: B25 · Area: reporting · Reported: 2026-09-09

It divided the **current auto-repair batch** (`fixed / fixed+manual_fixed+remaining`), and that batch's counters reset when a batch starts — live values were `fixed:0, manual_fixed:0, remaining:118`, hence 0.00%. Now computed from the same cumulative counts as the cards beside it: 110/395 = **27.85%**. Unmeasured renders "-", never "0.00%" — a zero there claims the AI has fixed nothing.

### BUG-55 — Donut centre said "total"
Status: FIXED · Previously: B26 · Area: reporting/copy · Reported: 2026-09-09

"Total" names nothing. Now "error listings", matching what the slices and tooltips count.

### BUG-56 — Refresh reporting: spinner kept coming back again and again
Status: FIXED · Previously: B27 · Area: reporting · Reported: 2026-09-09

`scheduleReportingWarmupPoll()` was the only poll in the file with **no attempt budget** (the quality tab retries 40x, stale-refetch 3x). Every poll returning `refreshing` scheduled another, forever, re-raising the "Preparing reporting data" line each time it rendered. Budget of 20; exhausted says so once instead of spinning; an explicit Refresh click resets it so a session can always recover.

### BUG-57 — "Is clear cache happening always — more frequent 0 data"
Status: FIXED · Previously: B28 · Area: cache · Reported: 2026-09-09

Yes, it was. **Measured**: `query_cache` held **only** the exempt `reporting_quality:*` keys — every `reporting_summary:*` entry gone, so each dashboard load paid a full recompute and reported itself still refreshing. `invalidate_cache()` is a blanket DELETE, and the background loops called it every pass (auto-repair fixes 10 rows a cycle; the two enrichment passes fill a field at a time). Background callers now go through `_invalidate_cache_background()`, rate-limited to once per 120s. **User actions still clear immediately** — a save or brand merge must be visible at once — and a test asserts that split.

### BUG-58 — Head-to-Head: "+ count is red for business, − count is green"
Status: FIXED · Previously: B29 · Area: reporting/competitive · Reported: 2026-09-09

Inverted. Every row is a **competitor** measured against the primary brand, so a competitor with **more** locations is bad news; the table coloured `diff > 0` green, reading "+278 competitor locations" as an achievement. Now `ahead ? --error : --ok`, with a hover title spelling out which brand is ahead and by how much. One shared helper drives all five columns so two can never disagree again.

### BUG-59 — Benchmark brand + competitor wrapped onto two lines
Status: FIXED · Previously: B30 · Area: reporting/UI · Reported: 2026-09-09

`.comp-bench-brand-cell` was `flex-direction: column` and both names carried `word-break/overflow-wrap`. Now one nowrap row; a name too long truncates with its full text in `title`. Width came from the three metric columns (38%→46% brand; 22/20/20→19/17.5/17.5), which held a short number and a short parenthetical under generous padding.

### BUG-60 — Top States rendered as overlapping full-height rectangles
Status: FIXED · Previously: B31 · Area: reporting/charts · Reported: 2026-09-09

Third occurrence of one root cause: the chart sized itself from `container.clientWidth`, which is **0 while the panel is hidden**. Attempt 1 built a 900px viewBox the browser scaled into one solid block (BUG-20); attempt 2 added a `ResizeObserver` that could re-enter and stack a second chart over the first — the overlapping rectangles. Now a **fixed-viewBox plain SVG**: scales to any width without measuring anything, so neither the zero-width case nor the re-entrancy exists. Birdeye accent hue stepped by rank, labels, and group-level hover. Deliberately the one chart here that is not d3; the test says why.

### BUG-61 — Download Excel sat in the page hero
Status: FIXED · Previously: B32 · Area: reporting/UI · Reported: 2026-09-09

Moved onto the "Location Records Sample" section header (right), beside the table it exports — in the hero it sat next to Refresh Report with nothing saying what it downloaded. The body copy no longer points at "(top right)".

### BUG-62 — Hiding the save left the workspace dirty and created a brand unasked
Status: FIXED · Previously: U1 · Area: mapper/brands · Reported: 2026-09-09 (live round)

`resetMapping()` cleared the mapping but not the brand: `selectedBrand`, the dropdown and the open brand form all survived, so the "cleared" 40/60 layout still had the previous business selected. It now clears all of it. Separately, `saveMapper()` would implicitly `createNewBrand()` from whatever was left in the form — a record nobody asked for. It now refuses unless the workspace is still live (`sourceParsed`) and a name was actually typed.

### BUG-63 — "Continue Without Saving" did not clear the parse
Status: FIXED · Previously: U4, BB2 · Area: mapper · Reported: 2026-09-09

It only navigated away, so the abandoned parse, its mappings and the brand survived and followed the user between tabs. Declining to save now discards, which is what the button says.

### BUG-64 — Empty Review tab looked broken
Status: FIXED · Previously: U6, BB4 · Area: review/UI · Reported: 2026-09-09

A bare grey line on a blank tab now reads as what it is: a large green success panel with 🎉. **The 0 was correct and self-inflicted** — `error_listings` holds 395 rows, all soft-deleted by the `reset=True` sample load, and the fresh 22,500-row load validated 100% clean.

### BUG-65 — Brand search broken in the UI and absent from the 40/60 window
Status: FIXED · Previously: U10, BB7 · Area: brands/UI · Reported: 2026-09-09

Two faults. `attachSearchableSelect()` inserts its search input as a **sibling** of `#brandSelect`, so it is a child of the same panel — and `syncPreParseWorkspace()` relocates that panel's children by id, sending anything not listed in `brandIds` to the parser host. The search box therefore landed in a *different panel* from the list it filters, which is why it "stopped working". `brandSelectSearch` now travels with its select. Separately the pre-parse picker had no search at all: `syncParserBusinessSelect()` now attaches one, and copies the **full** option list from the search's cache rather than `#brandSelect`'s innerHTML (which is rebuilt as the user types, so copying it while a filter was active handed the pre-parse picker a truncated brand list).

### BUG-66 — Reviewing a template forced "Save before you leave?"
Status: FIXED · Previously: U8, BB6 · Area: templates · Reported: 2026-09-09

`loadTemplateIntoEditor()` never cleared `pendingUnsavedParse`, so a stale `true` from **any earlier parse in the same session** survived and raised the prompt over a template the user had not touched. Cleared on open; re-armed in `applyMappingSelection()` only when a mapping is actually changed.

### BUG-67 — RULE R0 violated: listings had no resolvable template
Status: FIXED (forward) + REPAIRED (sample) · Previously: U11, RULE R0 · Area: templates/warehouse · Reported: 2026-09-09

`template_id` and `business_id` are foreign keys on every listing. Measured: of 28,119 live listings, **zero** resolved to a real template — 22,500 dangling and 5,619 missing. Causes: `__meta` was stamped with `template_id` **only for sample rows**, so every real user upload saved without one; and the sample loader never created the templates whose ids its listings carried. Both fixed; `template_id` is now REQUIRED in the schema. **Repaired live: 456 templates created, dangling 22,500 → 0.**

### BUG-68 — Template preview showed only MAPPED columns
Status: FIXED · Previously: U12, BB6 · Area: templates · Reported: 2026-09-09

The point of the review is to map *more*, and the typed columns only show what is already mapped. Unmapped source data lives in `custom_fields` (written by `_collect_extras`) and was returned as one opaque JSON blob. It is now expanded into real columns, listed in `unmapped_columns`, sorted first in the table and marked, with a typed column always winning a name clash. The template itself now stores `source_fields` **and** `unmapped_fields`, so the structure is recorded at business level rather than re-derived from a re-parse. **Verified live: `ddates`, `fgsgdfhds`, `memberlevel`, `seating_capacity`, `testloyaltytier` surfaced with values.**

### BUG-69 — Template Source Preview showed no rows
Status: FIXED · Previously: U9, BB6 · Area: templates · Reported: 2026-09-09

The endpoint existed and read bronze directly, but matched on `template_id` **alone** — and on a sample-loaded warehouse that key never meets: listings carry the source's template ids (`tmpl_john_standard`), while `workflow_templates` holds its own UUIDs. Measured: 22,500 listings have a template_id, none of them a template's. Now falls back to `business_id` with exact template matches sorted first, straight from bronze with no cache. The UI says which it is, so brand rows are never passed off as the template's. **Verified live: 3 records, `matched_by: "business"`.**

### BUG-70 — Failed enrichment retried immediately, forever
Status: FIXED · Previously: U7, BB5 · Area: enrichment · Reported: 2026-09-09

The run set `state="failed"`, the UI said "it will retry automatically", and the next trigger (any reporting refresh) restarted it at once — a tight loop against the same broken condition. Each consecutive failure now adds 5 minutes up to a 60-minute ceiling; the first success clears it. **A user pressing the button bypasses and clears the backoff**, and per explicit instruction **no retry timing is ever shown** — it is logged only.

### BUG-71 — Merge did not survive a rebuild
Status: FIXED · Previously: — (untracked) · Area: brands · Reported: 2026-09-09

See "Merges are now durable" in `codex.md`.

### BUG-72 — 40/60 layout said "Brand" on the left, "Business" on the right
Status: FIXED · Previously: U20, BB13 · Area: UI/copy · Reported: 2026-09-10

The backend calls it a business; the user should never have to know that. Both sides say **Brand** now, including the aria-label ("Select brand before parsing") and the two stray strings in `templates.js` ("belongs to this brand") and `mapper.js` ("Could not update brand"). Element **ids** deliberately keep `business` — they are backend identifiers, not labels.

### BUG-73 — Map markers vanish when zooming in
Status: FIXED (layer half); follow-up open · Previously: U21, BB14 · Area: reporting/map · Reported: 2026-09-10

`syncMapLayersByZoom()` picks between pins (zoom ≥9.5 or a city/zip filter), city circles (6.0–9.5) and state circles (below). The three are filled from **different payloads** and `map_records` is display-limited, so zooming past 9.5 could hide the populated circles and show a pin layer with **nothing in it** — the dots "went away". New `layerHasContent()` guard: an empty layer is never switched to, it falls back to whichever layer actually has content. Gap ZIPs remain on at every zoom, as before.

**Still open:** filtering to a city or ZIP should zoom the map to that level, and Reset should return to the whole US. `shouldFocusFilteredArea` + `DEFAULT_US_BOUNDS` already exist in `renderReportingMap()` — needs verifying against the reset path rather than assuming.

### BUG-74 — Auto-apply filters missing on the location tab
Status: IN PROGRESS · Previously: U22, BB15 · Area: reporting/filters · Reported: 2026-09-10

The feature exists on the Data Quality tab only (`reporting-tabs.js`: 400ms debounce, `#autoApplyFiltersBtn` toggling "Stop auto apply" / "Restart auto apply"). The Location Intelligence tab has a manual Apply button and no auto-apply at all. Being added to match.

### BUG-75 — Why single-row DB operations are slow
Status: REFERENCE (measured, acted on) · Previously: BB12 · Area: warehouse/performance · Reported: 2026-09-10

**Measured on this warehouse**, not estimated:

| single-row operation | BigQuery |
|---|---|
| INSERT (DML) | **2.36s** |
| SELECT by key | **1.59s** |
| UPDATE (DML) | **2.60s** |
| DELETE (DML) | **2.93s** |
| streaming insert (`insert_rows_json`) | 0.67s — ~3.5x faster than INSERT DML |
| SQLite mirror read | **0.01s** — ~160x faster than the BigQuery SELECT |

**Why:** BigQuery is an analytical warehouse — every statement is a scheduled *query job* with seconds of fixed overhead, so the cost is per **statement**, not per row. This is the same effect that made batching 14 deletes into one DROP script *slower* (9.4s) than 14 individual REST deletes (8.1s) — see BUG-32. There is no configuration that makes single-row DML fast; the only levers are **fewer statements** and **reading from the local mirror**.

Acted on: the BUG-77 duplicate check was **folded into the insert** (`INSERT … SELECT … WHERE NOT EXISTS`) rather than run as its own SELECT — that would have made every brand create ~4s instead of ~2.4s, for no added safety, since a guard in the same statement cannot race the write. The response now carries `created` so the UI never claims it made something it didn't.

**Remaining levers, not yet taken:** streaming inserts for append-only writes (~3.5x, but streamed rows sit in a buffer that cannot be updated or deleted for a while, which conflicts with soft-delete), and moving more single-row reads onto the SQLite mirror.

### BUG-76 — Saved brand not selected, and missing from suggestions
Status: FIXED · Previously: U18, BB9, BB10 · Area: brands/UI · Reported: 2026-09-10

Backend was fine — verified live: create-then-search returns the new brand immediately. **Two client-side causes.** (1) `createNewBrand()`/`updateExistingBrand()` reloaded with the brand's *name* as a search term, so the dropdown held only the matches and every other brand vanished. (2) `attachSearchableSelect()` returned early when that now-short list fell under its threshold — **without refreshing its cache** — so the cache kept a list predating the new brand; the suggestion panel could not offer it, and the next keystroke rebuilt the select from that stale cache. Both save paths now reload the full list, and the cache refreshes before the threshold bail-out.

### BUG-77 — Duplicate brand names could be created
Status: FIXED · Previously: U19, BB11 · Area: brands · Reported: 2026-09-10

Same name, case- and whitespace-insensitively, is now refused **server-side** (`create_brand`, before the INSERT — the UI prompt can be skipped by a retry or a second tab) and the UI selects the existing brand instead. A **≥80% similar** name is a *question*, not a decision: "Did you mean X?" — yes selects it, no proceeds, because "Smith Bakery" and "Smiths Bakery" really can be two businesses. The cheapest duplicate to resolve is the one never created.

### BUG-78 — Review tab "entirely broken" — challenged and checked
Status: NOT A BUG · Previously: — (untracked) · Area: review · Reported: 2026-09-10

Fair challenge, so it was exercised rather than assumed. Every endpoint the tab calls answers 200: `/api/rejected` (the queue), `/api/error-listings/count`, `/api/error-listings/by-brand`, `/api/review/fix-states`, `/api/enrichment/status`. `error_listings` holds **396 rows, all soft-deleted, 0 live** — the queue is genuinely empty, as reported earlier. (An earlier `/api/error-listings` 404 in my own probing was a wrong path guess on my part; the queue endpoint is `/api/rejected`.) A test now pins those endpoint names so a rename cannot silently break the tab.

### BUG-79 — "Aren't you using local db for faster brand search?"
Status: PARTLY — now fixed · Previously: U14 · Area: brands/cache · Reported: 2026-09-10

Two layers, and only one was local. The **search** is client-side (no DB). The **brand list** reads BigQuery — deliberately, not the `mirror_businesses` mirror, because the mirror only refreshes on a gold rebuild and a freshly created brand would be invisible until then — and is cached in SQLite. **Measured: 6.0s cold vs 6ms warm for 1,000 brands / 62KB.** The flaw was that the blanket `invalidate_cache()` threw that cache away on *any* save or background pass, so the next dropdown open paid the full 6s. `list_brands:*` is now spared from the blanket wipe (like `reporting_quality:*`) and cleared explicitly by the six paths that genuinely change the brand list.

### BUG-80 — "Suggestion doesn't show like a standard suggestion list"
Status: FIXED · Previously: U15, BB7 · Area: brands/UI · Reported: 2026-09-10

Filtering the `<select>`'s own options only helps once its dropdown is already open, so typing appeared to do nothing. There is now a real typeahead panel under the input: role=listbox, click to select, Escape/blur to dismiss, and it dispatches `change` so the app reacts as if the select were used. It re-homes itself on relocation, and its container gets a positioning context — the same fault the chart tooltips had.

### BUG-81 — Suggestion list capped at a fixed count
Status: FIXED · Previously: U16, BB8 · Area: brands/UI · Reported: 2026-09-10

I had capped it at 12. Removed: the panel has a fixed height and scrolls, so a one-character query over 1,000 brands reaches every match instead of silently stopping at the twelfth.

### BUG-82 — Notice dialog "too plain"
Status: FIXED · Previously: U17 · Area: UI/dialogs · Reported: 2026-09-10

It was a heading, a rule, and a sentence in a mostly empty box. It now leads with a tone-carrying icon (success / warn / error / info) beside the heading, with the action right-aligned. Only the icon changes per tone — the shell stays the one Birdeye dialog. Existing callers were given the tone they actually are, so a failed export no longer announces itself with a success tick.

### BUG-83 — No way to auto-map when everything is unmapped
Status: FIXED · Previously: U2 · Area: mapper · Reported: 2026-09-09

`renderMappings()` only suggests for target keys **absent** from `mappingSelections`, and clearing a field leaves an empty-string key behind — so once everything was unmapped the suggestions could never return. The new **Auto-map fields** button (right of the Template Components heading, shown only when there are parsed columns and nothing is mapped) deletes the empty entries and re-runs **that same pass** via `forceAutoMapOnce`. Four lines, not a second matching implementation — the test asserts it never calls `suggestField()` itself.

### BUG-84 — One source column filling several target fields
Status: FIXED · Previously: U3, BB1 · Area: mapper · Reported: 2026-09-09

`applyMappingSelection()` enforced one-column-one-target for a dropdown pick, but nothing enforced it for mappings written in **bulk** — presets, restored drafts, templates. Found the shipped instance: `setPizzaHutMappings()` mapped the column `address` to **both** `name` and `address`. New `dedupeMappingSelections()` runs from `renderMappings()`, the single choke point every path passes through; required targets keep the column, later claims are cleared, and the status line says what it dropped. The preset is fixed at source too, and a test scans every preset for the pattern.

### BUG-85 — Demo preset locked you to its own brand
Status: FIXED · Previously: U5, BB3 · Area: mapper/presets · Reported: 2026-09-09

`updatePresetBrandPanel()` set `brandSelect.disabled = true` once the preset's brand existed, so a demo source could only ever be tested against that one business. The **selector** is now free; the brand **form** stays locked, so the preset brand's details still cannot be edited by accident.

### BUG-86 — Brand search still did not appear (follow-up)
Status: FIXED · Previously: U13, BB7 · Area: brands/UI · Reported: 2026-09-09

`syncPreParseWorkspace()` moves nodes using a snapshot of the panel's children taken **once**; an input created after that snapshot is not in the list that moves back, so it was stranded in the hidden panel. `attachSearchableSelect()` now re-homes itself beside its select on every call, and both searches are re-attached after the relocation. Matching was already case-insensitive; it now also normalises whitespace and matches anywhere in the name.

### BUG-87 — `content_hash` backfill
Status: OPEN (critical risk closed; backfill outstanding) · Previously: O8 · Area: warehouse/dedupe · Reported: 2026-09-09

**`business_id` was removed from `CONTENT_HASH_FIELDS` (user instruction).** The hash now answers "is this the same physical place?" independently of which brand filed it, which is what makes a cross-brand duplicate detectable. Per-brand dedupe is unaffected — `_dedupe_listings_against_bronze()` keys on the composite `(business_id, content_hash)`, carrying the brand explicitly. **Removing a field changes every stored hash**, so `LEGACY_CONTENT_HASH_FIELDS` / `legacy_content_hash()` reproduce the old definition and the dedupe matches **either**, upgrading a legacy row to the new hash when it matches. That means **no re-save can insert duplicates** — the critical risk is closed. Still open: a one-shot backfill so rows never re-observed also carry new hashes (needed for cross-brand detection to see them). Approach: SELECT `listing_id` + the hash fields, recompute in **Python** (`content_hash()` — do NOT try to reproduce `json.dumps(sort_keys=True)` + `str()` float formatting in SQL), load pairs to a temp table, MERGE.

### BUG-88 — Test coverage
Status: OPEN · Previously: O7, Q10 · Area: tests · Reported: 2026-09-09

**Re-measured 2026-09-09: 53% overall**, `workflow_server.py` 48% (4151 statements / 2150 missed), 508 tests. The ~110 tests added since the 52% reading moved the total one point — `workflow_server.py` dominates the statement count, so only tests aimed at it will move this.

### BUG-89 — Merge weighting surfaced in enrichment
Status: OPEN (queued) · Previously: Q8 · Area: enrichment · Reported: 2026-09-09

Queued, untouched. Priority 1 in the handoff list above.

### BUG-90 — Non-US / out-of-range coordinate enrichment
Status: OPEN (queued) · Previously: Q11 · Area: geo enrichment · Reported: 2026-09-09

The reported example `(40.776506, -245.22)` is not merely non-US: -245.22 is outside the valid longitude range (-180..180) altogether. But `-245.22 + 360 = 114.78`, i.e. it is a **wrapped** longitude, so it is repairable rather than only flaggable. Plan: normalise wrapped longitudes back into range first, then fall back to the nearest reference city within ~100km and offer it as a suggestion — non-US data is valid data, it is just not US, and today's message treats "outside US bounds" as a failure.

### BUG-91 — App header tool name sits beside the Birdeye logo
Status: FIXED · Previously: — · Area: UI/header · Reported: 2026-09-10

Header title lockup now stacks vertically: Birdeye logo first, then "Competitive Whitespace Tool" below it. CSS-only change in `ui/integrations.html`; no server restart required.

### BUG-92 — Time charts have inconsistent placement, height, and default period
Status: FIXED · Previously: — · Area: reporting/UI · Reported: 2026-09-10

Trends Over Time and Historical Quality & Change Tracking now both use the same heading/control row, the same chart box height (`340px` SVG inside a `360px` chart shell), and default their period toggles/state to `1H`. Follow-up completed: Location Intelligence tab order is first-layer number cards, then Location Map, then Top States/Coverage, then the line charts.

### BUG-93 — Mapper refresh shows the old utility rail instead of the 40/60 start screen
Status: FIXED · Previously: — · Area: mapper/UI · Reported: 2026-09-10

On `/app` or a refresh while already on Mapping, the page now starts clean in the 40/60 pre-parse workflow. Mapper draft restore is skipped only when the boot target is `mapperView`, preserving refresh restore behavior for Reporting, Review, and Template Library. Clarified by BUG-95: utility panels such as Brand Entity Resolution, Job History, and Data Controls remain visible below the 40/60 start surface; they are valid panels, not the older restored workspace. Follow-up fixed: `preparse-booting` now also hides the boot-time full-width `#status` until JS relocates it into the parser panel, so status and utility panels do not paint ahead of the 40/60 containers. Mapper JS cache-buster bumped to `preparse-layout-v6`.

### BUG-94 — Header navigation and utility button sizes compete
Status: FIXED · Previously: BUG-91 follow-up · Area: UI/header · Reported: 2026-09-10

The four main top navigation tabs now render larger (`44px` min-height, `15px` type, stronger padding/weight), while the right-side utility buttons are compact (`24px` min-height, `10px` type). Guarded by a header layout contract test.

### BUG-95 — Selected brand is not locked into the required Brand Name mapping
Status: FIXED · Previously: BUG-93 follow-up · Area: mapper/UI · Reported: 2026-09-10

When a brand is selected from the dropdown before parsing, the Brand Name mapping is now mandatory, mapped to a synthetic selected-brand field, and disabled so it cannot be accidentally remapped. The save payload carries that selected brand value as `__brand` and includes it in `source_fields`, so frontend validation and backend mapper validation agree without a backend/query change. The valid utility panels (Brand Entity Resolution, Job History, Data Controls) remain visible below the 40/60 start surface; the older restored mapping workspace still does not replace the start state on `/app` or Mapper refresh.

### BUG-96 — Reporting intro copy is too generic for the two tabs
Status: FIXED · Previously: — · Area: reporting/UI copy · Reported: 2026-09-10

The Reporting hero and both inner-tab intro blurbs are now medium-length and grounded in the current architecture/goals: hero names the gold reporting layer and filtered views; Location Intelligence names validated location records, map coverage, open ZIPs, and trend movement; Data Quality names rejected listings, quality mirrors, issue patterns, fix progress, freshness risk, and automatic/manual repair. Follow-up completed under the same description-copy bug: Mapping now has a page intro above the 40/60 start workspace, and Template Library now explains saved mappings, source fields, repairs, and repeat-load alignment. Reporting tabs cache-buster bumped to `quality-layout-v4`.

### BUG-97 — Template editor: "This template has no stored source columns. Parse a source file to remap it."
Status: PARTIAL (backend FIXED, frontend flag consumption open — handed to Codex via `AGENT_SYNC.md`) · Previously: — · Area: templates/bronze data · Reported: 2026-09-10

Backend root cause and fix: **461/461** `workflow_templates` rows had empty `components.source_fields` — every template in the warehouse, mostly (456) the `is_sample_data` stub rows the RULE R0 sample-load backfill creates with `components = {"brand": business_id}` and nothing else (`_load_sample_dataset_impl()`, `whitespace_tool/workflow_server.py` ~line 2979). New `backfill_sample_template_source_structure()` derives real `source_fields`/`unmapped_fields` per template from its own listing data and flags the result `components.structure_synthesized = True`. Executed live: 460/461 templates now carry real source_fields; the one true exception (`global_hotels_mixed_csv`, zero listings) carries `components.structure_unavailable = True` instead. Full detail in `codex.md`. Frontend still needs to special-case `structure_unavailable` in `ui/js/templates.js`'s `renderTemplateEditSourcePreview()` instead of showing the generic (and, for a bulk-loaded template, factually wrong — there is no source file to parse) message on any empty `sourceFields` — see the handoff entry in `AGENT_SYNC.md`.

### BUG-98 — Parse click can open the edit-brand form
Status: FIXED · Previously: — · Area: mapper/UI · Reported: 2026-09-10

Clicking Parse can no longer open the edit-brand form. The brand dropdown change handler no longer calls `openBrandEditorForm("edit")`; selecting a brand only sets context and locks the Brand Name mapping. Explicit edit controls still open the form. Guarded by a mapper layout contract test.

### BUG-99 — Source Input uses a dropdown instead of the source-control radio style
Status: FIXED · Previously: — · Area: mapper/UI · Reported: 2026-09-10

The Source input picker now renders as a selected radio group, matching the source-control pattern while using a distinct cyan treatment from the source-format/demo-source radios. The existing `sourceInputMode` select remains hidden as the state holder so parser logic, drafts, presets, and the default `Public URL` behavior stay unchanged.

### BUG-100 — 40/60 brand search and selected value stack across too much space
Status: FIXED · Previously: — · Area: mapper/UI · Reported: 2026-09-10

The 40/60 pre-parse brand selectors now use a two-column layout on wider panes: brand search on the left and selected brand dropdown on the right. The compact left-rail mapping view remains stacked, and the layout collapses back to one column on narrow screens.

---

## Work queue

Superseded by the BUG-N list — this table was tracking the same items under a
second `Q#` scheme, which is exactly the multi-tag confusion the renumbering
was meant to end. Every item that was still open now lives as its own BUG-N
entry with full detail:

- **BUG-88** — Raise test coverage (was Q10)
- **BUG-89** — Merge weighting surfaced in enrichment (was Q8)
- **BUG-90** — Non-US / out-of-range coordinate enrichment (was Q11)

Everything else in the old Q1–Q19 list was marked DONE and needed no entry of
its own; where it fixed something worth remembering long-term, that is
folded into a BUG-N entry or the Landmarks section below. Rule for jumping
the queue is unchanged: **a message starting with `URGENT` goes first.**

## Landmarks worth knowing before editing

- **Route ordering:** `startswith()` routing means a broad prefix swallows a longer sibling. This bit three times (`/api/templates`, `/api/brands`, `/api/reporting`). A test now enforces specific-before-general.
- **Empty ARRAY params become NULL in BigQuery**, so every `ARRAY_LENGTH(@x) = 0` must be `COALESCE(ARRAY_LENGTH(@x), 0) = 0`. An unguarded one silently returns ZERO rows.
- **Schema drift:** a column added to `TABLE_SCHEMAS` only reaches a deployed table via an ensure-pass. `error_listings` had none, which took down the whole quality tab. Gold VIEWS need `GOLD_VIEW_DEFINITION_VERSION` bumped when their SELECT list changes.
- **Never blank on refresh:** `reportHasRenderedOnce` (set once, never reset) gates the empty-skeleton render. Keying it off `reportLoaded` wipes the numbers on every refresh.
- **Counters:** fixing a record soft-deletes its error row, so all cumulative counts read across `is_deleted` rows via `was_ever_invalid` / `resolution_status`.
- **The test suite must never touch `.cache/whitespace_cache.db`.** `unit_tests/conftest.py` sets `WHITESPACE_CACHE_DB` to a temp file in `pytest_configure` (before any test module is imported, because `sqlite_cache` resolves `DB_PATH` at import). Without it, a `pytest` run wipes the running app's reporting mirror — the suite calls the real clear/mirror-swap functions. A guard test asserts this stays true. (See BUG-42.)
- **Orphaned pytest processes outlive their runs** and keep background threads writing to whatever DB they opened. If data is disappearing with nothing in the server log, run `lsof .cache/whitespace_cache.db` before theorising about code paths.
- **`mirror_meta.synced_at` identifies who wrote it.** ISO-8601 with a `T` → `replace_gold_mirror()`. Space-separated (`CURRENT_TIMESTAMP`) → `clear_sample_reporting_mirror()` / `clear_local_cache_db()`.
- **`invalidate_cache()` is a blanket DELETE** of every cached payload except `reporting_quality:*`. Never call it from a loop that runs continuously — use `_invalidate_cache_background()` (rate-limited to 120s). Calling it per batch is what emptied every `reporting_summary:*` entry and made the dashboard feel permanently cold.
- **`container.clientWidth` is 0 while a panel is hidden.** This broke the Top States chart three separate times (BUG-20, BUG-60). Charts that render before their tab is shown must use a fixed viewBox, not a measured width; a `ResizeObserver` workaround can re-enter and stack two charts.
- **One button, three mode flags.** `#createBrandBtn` is driven by `brandEditMode`, `presetBrandEditMode` and `presetCreateMode`, set by different open-paths. Any new path that opens the brand form must set — and every path that closes it must clear — all three.
- **`listings` has no `raw` column.** The `raw.__meta.semantically_cleared_fields` breadcrumb written by semantic cleaning therefore never reaches the warehouse for a *valid* listing — only `error_listings.raw_record` keeps the raw payload. Any plan that reads that marker for saved rows is built on nothing.
- **`business_id` was inside `content_hash`** (`CONTENT_HASH_FIELDS`) until BUG-87 removed it. Any cross-brand dedupe keyed on the *legacy* hash is dead on arrival; `legacy_content_hash()` still reproduces the old definition for compatibility.
- **One dialog shell.** `<dialog class="app-help-dialog"> > .app-help-content > .app-help-header > <h2 id>`, plus `--editor` / `--form` / `--danger` modifiers. A test walks every `<dialog>` in `integrations.html`, so a new bespoke frame fails immediately.
- **Test markers are substrings.** In `FakeClient(query_results={...})`, `` "listings`" `` also matches `` error_listings` `` — qualify markers with the dataset (`` "ds.listings`" ``) or the wrong table's rows come back and the test passes for the wrong reason.

## Standing rules

- **SQL helper adoption: DROPPED (user, 2026-09-10).** "I don't want SQL helper now, as long as queries are working fine and fast." The `run_sql` / `run_sql_rows` / `run_sql_dml` helpers stay where they are already used; do **not** migrate the remaining `client.query()` sites. Do not re-open this.
- **Sample-load halves: SETTLED (user, 2026-09-09).** Keep the automatic second half — half 1 returns fast, half 2 self-starts in a background thread. No second click. Do not re-open or re-ask this.
- **Do not restart the server** unless explicitly asked (2026-09-09).
- **Do not commit or push** unless explicitly asked (I pushed once unprompted; won't recur).
- Backend (`.py`) changes need a restart to take effect — BUG-8's server half and anything in BUG-22 are written but **not live** until then.
