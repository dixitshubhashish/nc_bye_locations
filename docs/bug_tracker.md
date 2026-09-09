# Bug Tracker — live status

Single place to see what is fixed vs still open, so nothing gets silently
dropped. Detail for each fix lives in `codex.md`'s batch entries.

Status: **FIXED** (done + tested) · **OPEN** (not started) · **PARTIAL** (some
of it landed, rest named).

---

## Fixed this round

| # | Bug | Status | Notes |
|---|-----|--------|-------|
| B1 | Duplicate brands ("Domino's Pizza" twice) shown in the brand dropdown | **FIXED** | Only one survivor per similar-name group reaches `brandSelect`; the rest go to the left rail. A currently-selected duplicate stays visible so the user's own selection is never blanked. |
| B2 | Brand duplicate detection never ran on `/app` load | **FIXED** | `loadAppData()` → `loadBrands()` → `duplicateBusinessGroups()` → `renderDuplicateBrandRail()`. |
| B3 | Merge option was never offered | **FIXED** | New "Duplicate Brands" panel in the 40% left rail, one group at a time, hidden when nothing to merge. |
| B4 | Brand match required byte-identical names | **FIXED** | Dice-coefficient bigram similarity at **≥75%**. Verified: `Dominos Pizza` vs `Domino's Pizza Inc` = 0.85 (merge); `Little Caesars` vs `Little Caesar's LLC` = 0.86 (merge); `Pizza Hut` vs `Domino's Pizza` = 0.38 (no merge). |
| B5 | Brand id / listing count / created_at cluttered the option text | **FIXED** | Detail is hover (`title`) only; visible text stays short. Newest vs oldest marked in the hover. |
| B6 | Two competing merge UIs | **FIXED** | Old "Similar Brands" block inside the Active Brands box removed; the rail owns merging. |
| B7 | Data Controls lost its ⚠️ warning sign | **FIXED** | Restored on the panel heading and the clear-confirm dialog. The amber `.data-danger-panel` styling was never removed — only the sign had been. |
| B8 | Donut/metrics stayed outdated after 5+ minutes on the page | **FIXED** | A warm-but-stale cache was served while a background thread recomputed — and **nothing ever asked for the result**. Server now returns `refreshing: true`; the page re-fetches (max 3×, 6s apart) and re-renders. |
| B9 | The four fix counters "reset to zero" | **FIXED** | Not a data loss and **not** a mirroring failure — verified live: BigQuery `quality_fix_events` = AI 124 / Manual 4, SQLite mirror = exactly the same, `/api/enrichment/status` returns them correctly. The bug was `state.auto_repair?.fixed \|\| 0`: **any** status response omitting `auto_repair` rendered all four as 0, wiping correct numbers off screen. Absent data now leaves the displayed values alone. |
| B10 | Hiding parser progress left the post-parse workspace up | **PARTIAL** | Returns to the 40/60 pre-parse layout (done). **Still open:** see O1. |
| B11 | Review action buttons ("AI Suggested Fix" / "Manual Review") did nothing on click | **FIXED** | Per-button listeners were bound right after `enableSortableTable()`, which rebuilds the tbody on sort — detaching them. Replaced with one delegated listener on the container that survives any re-render, re-bound per load so handlers don't stack. |
| B12 | AI action had a generic lightbulb icon | **FIXED** | Now 🤖 (AI); Manual Review keeps 🛠️. |
| B13 | `reviewActionHandler is not defined` on the review queue | **FIXED** | My own regression: the declaration landed *inside* the preceding function (between its `finally` and its closing brace), so it was function-scoped and invisible to `loadRejectedRecords()`. Moved to module scope; a test now asserts brace-depth 0. The empty-queue path also detaches the handler instead of returning early and leaking the old closure. |
| B14 | Template review let the business be changed, and the top tab jumped to Mapping | **FIXED** | A saved template cannot exist without its `business_id`, so the brand is a fact, not a choice — all three brand pickers are locked while editing (released everywhere `template-edit-mode` ends). Top nav stays on Template Library. |
| B15 | Data Model unusable past ~100 columns | **FIXED** | Search box + independent vertical scrolling (`max-height: 60vh`) above a 100-field threshold; below it the plain list is kept. Search matches the raw column **and** its mapped label ("zip" finds `address.postcode`), and filters both columns so the pairing stays aligned. |
| B16 | Merge picker didn't show which record was new vs old | **FIXED** | The picker now shows `BID · N listings · Newest/Oldest · created <date>` inline (a decision needs visible basis, unlike the dropdown where detail was clutter), plus a stated recommendation. |
| B17 | One click produced many Excel download attempts | **FIXED** | The `<a href=server-url>` was removed from the DOM immediately after `.click()`, which makes some browsers re-issue the request. Now one guarded `fetch` → blob → single save, with an in-flight set that blocks double-clicks and a busy state on the button. |
| B18 | Export was a bare .xlsx; large filters failed | **FIXED** | Now a **ZIP**: workbook + `listings.csv` + `metrics.csv` + `competitors.csv` + `README.txt` (naming the filters that produced it). Filters accept **multiple** values (`IN UNNEST`) instead of one scalar — "20 states" silently matched nothing before. Row ceiling raised 50k → **200k**, and hitting it is reported as `PARTIAL RESULT`, not passed off as complete. |
| B19 | Export had no competitor view | **FIXED** | Third sheet + `competitors.csv`: per-brand listings, share %, states, cities, ZIPs, coordinate/ZIP completeness — derived from the same rows as sheet 1, so they always reconcile. |
| B20 | "Top States by Coverage" rendered as one solid block | **FIXED** | `container.clientWidth` is 0 while the panel is hidden, so `Math.max(360, 0 \|\| 900)` built a 900px viewBox the browser then scaled up. Now waits for a real width via `ResizeObserver`. Bars also got a sequential colour ramp and the track a contrasting tone — one flat blue on a near-identical track was the "same background" confusion. |
| O1 | Background save after hiding progress | **FIXED** | Traced end to end. Success was already announced (dialog + `loadJobHistory()`); **failure was not**. `record_save_event()` ran only after a successful `push_to_bigquery`, so a failed save produced **no Job History row at all** — indistinguishable from never having started. Now recorded on the failure path too (`mapped_rows=0` + rows present is what already derives `FAILED`), narrowly around the push so an argument-validation raise still never becomes a job. The UI now pops the themed dialog and refreshes Job History when a *dismissed* save fails — the old inline `#status` line was invisible after `resetMapping()` returned the user to the pre-parse layout. |
| O2 | `content_hash` near-duplicate dedupe | **WON'T FIX AS SPECIFIED** | Its premise is impossible. `business_id` **is** one of `CONTENT_HASH_FIELDS`, so two brand records can never share a hash — verified: the identical listing under `brand-A` vs `brand-B` yields two different hashes. `duplicateContentHashGroups()` could never have fired; removed, with the reasoning left at the call site and a test asserting its absence *and* the hash property. A real signal needs a physical-identity hash **excluding** `business_id`, computed warehouse-side, plus a product call on whether a shared street address means a duplicate brand or a shared strip mall. Both open. |
| O3 | Merge user-confirmation step | **FIXED** | `merge_brands()` gained `preview: true` — per-table COUNTs instead of the UPDATEs — and the rail runs it for every group before a themed confirm naming listings / templates / review rows. A table whose count can't be read reports **None**, not 0, and the dialog then shows no totals: reporting an unreadable table as zero would let it claim "nothing will move" about data that is there. Mutation-tested. |
| O4 | Per-table downloads (market gap, brand comparison) | **ALREADY FIXED** | Was stale in this tracker. `data-table-export` buttons are live on Top States, Top Cities, Brand Comparison and Market Gaps, served by `/api/reporting/table-export`. |
| O5 | Extended Coverage Metrics panel | **ALREADY FIXED** | Was stale in this tracker. The panel is gone; `loadExtendedMetrics()` now serves only the Top States chart, with the reasoning kept as a comment at `ui/reporting-tabs.js:784`. |
| O6 | Idle-time enrichment loop | **FIXED (differently than specified)** | The plan was to refill from `raw.__meta.semantically_cleared_fields` — but **that breadcrumb never reaches the warehouse for a valid listing**: `listings` has no `raw` column (57 columns, verified); only `error_listings.raw_record` keeps it. So the refill is driven off the blank column itself. New `enrich_location_contact()` queries Overpass **around the listing's own coordinates** and requires a shared meaningful word with the POI name, so a neighbour can't donate its phone number; a name-matched POI with no contact tag isn't an answer either. `_idle_location_enrichment_pass()` fills only blanks and **re-asserts the blank-only guard in SQL**, so a concurrent user edit wins. Shares the existing `brand-enrichment` thread rather than adding a second idle worker. |
| B22 | Five dialogs off the Birdeye shell | **FIXED** | `pythonConnectorDialog`, `editRecordDialog`, `dangerDialog`, `masterDeleteCredentialsDialog`, `masterDeleteConfirmDialog` all moved onto `<dialog class="app-help-dialog"> > .app-help-content > .app-help-header > <h2 id>`. Three modifier classes carry the difference: `--editor` (1200x800), `--form`, `--danger` (red border/rule/title, so destructive stays visibly destructive). Both retired frames (`connector-editor-dialog`, `danger-dialog`) deleted from the CSS; every dialog gained `aria-labelledby`. The test walks every `<dialog>` in the markup and asserts the retired names appear nowhere. |
| B21 | Sample load "always stops at 94%" | **FIXED** | It was never stuck. The bar was `Math.min(94, elapsed / estimate * 100)` — a pure time guess (15s/25s) hard-capped at 94, so any slower load parked there until the fetch returned. It measured nothing. Now shows the estimate only while it is still an estimate, then switches to an honest `Ns elapsed - larger batches take longer, this keeps running`. Trailing `...` removed per the spinner rule. Confirmed the loader already skips a failing brand (`except → continue`) and, since the `bad_row_index` fix, routes malformed rows to review rather than aborting — so nothing is blocking additional data. |

### Reported live this session (2026-09-09), all fixed

| # | Bug | Status | Notes |
|---|-----|--------|-------|
| B23 | "Some clicks lose the create brand form, call the unexpected one" | **FIXED** | **Three** flags decide what the single `#createBrandBtn` means — `brandEditMode` (Edit-brand link + pre-parse Edit radio), `presetBrandEditMode` (the CSV preset panel's "Edit Brand Details") and `presetCreateMode` — each set by a different path that opens the form. The click handler consulted only `brandEditMode`, so the preset edit path left the button on its **create** branch: saving a form showing an existing brand's details filed a **second copy of that brand**. Now dispatches on `(brandEditMode \|\| presetBrandEditMode) && selectedBrand?.business_id`; the `business_id` check stops a stale preset flag turning a genuine create into an update of nothing. Separately, `brandSelect` change and Cancel reset **all three** flags — they reset two of three, so `presetBrandEditMode` survived into a context whose form no longer described the selected brand. |
| B24 | Review cards showed "–" while the donut showed 118 | **FIXED** | Not a data loss. **Measured the live mirror**: `fix_state_counts` held `ai_fixed=110, manual_fixed=155, manual_pending=130, total=395` and reconciled exactly. The cards were read off `/api/reporting/quality` — a heavy multi-query aggregation they had to wait on **and fail with**. New mirror-backed `GET /api/review/fix-states` serves the six numbers directly; a cold mirror now returns `refreshing: true` so the page polls (bounded) instead of leaving dashes for the session. |
| B25 | "AI Fixed by Total Error" read 0.00% beside cards showing 110 AI fixes | **FIXED** | It divided the **current auto-repair batch** (`fixed / fixed+manual_fixed+remaining`), and that batch's counters reset when a batch starts — live values were `fixed:0, manual_fixed:0, remaining:118`, hence 0.00%. Now computed from the same cumulative counts as the cards beside it: 110/395 = **27.85%**. Unmeasured renders "-", never "0.00%" — a zero there claims the AI has fixed nothing. |
| B26 | Donut centre said "total" | **FIXED** | "Total" names nothing. Now "error listings", matching what the slices and tooltips count. |
| B27 | Refresh reporting: spinner kept coming back again and again | **FIXED** | `scheduleReportingWarmupPoll()` was the only poll in the file with **no attempt budget** (the quality tab retries 40x, stale-refetch 3x). Every poll returning `refreshing` scheduled another, forever, re-raising the "Preparing reporting data" line each time it rendered. Budget of 20; exhausted says so once instead of spinning; an explicit Refresh click resets it so a session can always recover. |
| B28 | "Is clear cache happening always — more frequent 0 data" | **FIXED** | Yes, it was. **Measured**: `query_cache` held **only** the exempt `reporting_quality:*` keys — every `reporting_summary:*` entry gone, so each dashboard load paid a full recompute and reported itself still refreshing. `invalidate_cache()` is a blanket DELETE, and the background loops called it every pass (auto-repair fixes 10 rows a cycle; the two enrichment passes fill a field at a time). Background callers now go through `_invalidate_cache_background()`, rate-limited to once per 120s. **User actions still clear immediately** — a save or brand merge must be visible at once — and a test asserts that split. |
| B29 | Head-to-Head: "+ count is red for business, − count is green" | **FIXED** | Inverted. Every row is a **competitor** measured against the primary brand, so a competitor with **more** locations is bad news; the table coloured `diff > 0` green, reading "+278 competitor locations" as an achievement. Now `ahead ? --error : --ok`, with a hover title spelling out which brand is ahead and by how much. One shared helper drives all five columns so two can never disagree again. |
| B30 | Benchmark brand + competitor wrapped onto two lines | **FIXED** | `.comp-bench-brand-cell` was `flex-direction: column` and both names carried `word-break/overflow-wrap`. Now one nowrap row; a name too long truncates with its full text in `title`. Width came from the three metric columns (38%→46% brand; 22/20/20→19/17.5/17.5), which held a short number and a short parenthetical under generous padding. |
| B31 | Top States rendered as overlapping full-height rectangles | **FIXED** | Third occurrence of one root cause: the chart sized itself from `container.clientWidth`, which is **0 while the panel is hidden**. Attempt 1 built a 900px viewBox the browser scaled into one solid block (B20); attempt 2 added a `ResizeObserver` that could re-enter and stack a second chart over the first — the overlapping rectangles. Now a **fixed-viewBox plain SVG**: scales to any width without measuring anything, so neither the zero-width case nor the re-entrancy exists. Birdeye accent hue stepped by rank, labels, and group-level hover. Deliberately the one chart here that is not d3; the test says why. |
| B32 | Download Excel sat in the page hero | **FIXED** | Moved onto the "Location Records Sample" section header (right), beside the table it exports — in the hero it sat next to Refresh Report with nothing saying what it downloaded. The body copy no longer points at "(top right)". |

## Open — named, not started

| # | Bug | Detail |
|---|-----|--------|
| O8 | `content_hash` backfill | **`business_id` was removed from `CONTENT_HASH_FIELDS` (user instruction).** The hash now answers "is this the same physical place?" independently of which brand filed it, which is what makes a cross-brand duplicate detectable. Per-brand dedupe is unaffected — `_dedupe_listings_against_bronze()` keys on the composite `(business_id, content_hash)`, carrying the brand explicitly. **Removing a field changes every stored hash**, so `LEGACY_CONTENT_HASH_FIELDS` / `legacy_content_hash()` reproduce the old definition and the dedupe matches **either**, upgrading a legacy row to the new hash when it matches. That means **no re-save can insert duplicates** — the critical risk is closed. Still open: a one-shot backfill so rows never re-observed also carry new hashes (needed for cross-brand detection to see them). Approach: SELECT `listing_id` + the hash fields, recompute in **Python** (`content_hash()` — do NOT try to reproduce `json.dumps(sort_keys=True)` + `str()` float formatting in SQL), load pairs to a temp table, MERGE. |
| O7 | Test coverage | **Re-measured 2026-09-09: 53% overall**, `workflow_server.py` 48% (4151 statements / 2150 missed), 508 tests. The ~110 tests added since the 52% reading moved the total one point — `workflow_server.py` dominates the statement count, so only tests aimed at it will move this. |

---


## Work queue (one at a time, in order)

Rule: I take these strictly in order. **A message starting with `URGENT` jumps
to the front** and is done before anything else resumes.

| # | Item | State |
|---|------|-------|
| Q1 | Bulk brand merge as a radio table | **DONE** |
| Q2 | Two-row gradient bands on reporting tables | **DONE** |
| Q3 | Auto-apply filters + stop/restart toggle | **DONE** |
| Q4 | Per-table ZIP downloads (market gap, brand comparison, top states/cities) | **DONE** |
| Q5 | Sample reload: partial-resume, parallel load, per-brand deadline, gold promotion | **DONE** |
| Q6 | 5-state review counters (`was_ever_invalid` + status/ai flags), mirror- and DB-backed | **DONE** |
| Q7 | Alternate Manual / AI-suggested rows in the review queue | **DONE** |
| Q8 | Merge weighting surfaced in enrichment | queued |
| Q12 | Terminology: "Listings" canonical everywhere (`total_listings` + alias) | **DONE** |
| Q13 | Pagination on every reporting table (was: one pager + silent `.slice(0,10)`) | **DONE** |
| Q14 | Themed notice/confirm replacing `alert`/`confirm`; brand save acknowledgement | **DONE** |
| Q15 | ZIP suggestions deduped per ZIP | **DONE** |
| Q16 | Keyless brand enrichment (OSM tags + DuckDuckGo), never invents values | **DONE** |
| Q17 | Auto-refresh no longer blanks the report before fetching | **DONE** |
| Q18 | Adopted AI suggestion counts as an AI fix | **DONE** |
| Q19 | Fix-state pivot reports fixed states, not only pending | **DONE** |
| Q9 | Idle-time enrichment loop (fills semantically cleared fields) | queued |
| Q10 | Raise test coverage from 52% | queued |
| Q11 | Non-US / out-of-range coordinate enrichment | queued |

### Q11 note
The reported example `(40.776506, -245.22)` is not merely non-US: -245.22 is
outside the valid longitude range (-180..180) altogether. But
`-245.22 + 360 = 114.78`, i.e. it is a **wrapped** longitude, so it is
repairable rather than only flaggable. Plan: normalise wrapped longitudes
back into range first, then fall back to the nearest reference city within
~100km and offer it as a suggestion - non-US data is valid data, it is just
not US, and today's message treats "outside US bounds" as a failure.

### Q6 spec (as given)
One durable column marking a listing as *ever* invalid, so cumulative totals
survive later fixes. Then five counts:

| bad listing | status | flags | card |
|---|---|---|---|
| true | fixed | ai_fix = true | AI Fixed |
| true | fixed | ai_suggested_fix = true | AI Suggested Fixed |
| true | fixed | both false | Manual Fixed |
| true | pending | ai_suggested = true | AI Suggested Pending |
| true | pending | ai_suggested = false | Manual Pending |


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
| 3 | **SQL helper adoption** | `run_sql` / `run_sql_rows` / `run_sql_dml` + `_sql_params()` exist; `merge_brands` uses them (including the new preview path). A bulk migration of the other ~85 `client.query()` sites was attempted and REVERTED — it broke test doubles whose `query()` takes only SQL. Migrate incrementally, running tests after each batch. `run_sql` deliberately omits `job_config` when there are no params so it stays a drop-in. |
| 4 | **Cross-brand duplicate signal (was O2)** | The `content_hash` approach is impossible — `business_id` is inside the hash. Needs (a) a physical-identity hash excluding `business_id`, computed warehouse-side, and (b) a product call: is a shared street address evidence of a duplicate brand, or a shared strip mall? |
| 5 | **Semantic-clearing refill, second source** | `_idle_location_enrichment_pass()` covers phone/website/email from OSM by coordinates. Other kinds semantic cleaning clears (rating, money, year, boolean) have no external source yet and stay blank — blank being a true statement, not a gap to paper over. |

### Landmarks worth knowing before editing

- **Route ordering:** `startswith()` routing means a broad prefix swallows a longer sibling. This bit three times (`/api/templates`, `/api/brands`, `/api/reporting`). A test now enforces specific-before-general.
- **Empty ARRAY params become NULL in BigQuery**, so every `ARRAY_LENGTH(@x) = 0` must be `COALESCE(ARRAY_LENGTH(@x), 0) = 0`. An unguarded one silently returns ZERO rows.
- **Schema drift:** a column added to `TABLE_SCHEMAS` only reaches a deployed table via an ensure-pass. `error_listings` had none, which took down the whole quality tab. Gold VIEWS need `GOLD_VIEW_DEFINITION_VERSION` bumped when their SELECT list changes.
- **Never blank on refresh:** `reportHasRenderedOnce` (set once, never reset) gates the empty-skeleton render. Keying it off `reportLoaded` wipes the numbers on every refresh.
- **Counters:** fixing a record soft-deletes its error row, so all cumulative counts read across `is_deleted` rows via `was_ever_invalid` / `resolution_status`.
- **`invalidate_cache()` is a blanket DELETE** of every cached payload except `reporting_quality:*`. Never call it from a loop that runs continuously — use `_invalidate_cache_background()` (rate-limited to 120s). Calling it per batch is what emptied every `reporting_summary:*` entry and made the dashboard feel permanently cold.
- **`container.clientWidth` is 0 while a panel is hidden.** This broke the Top States chart three separate times. Charts that render before their tab is shown must use a fixed viewBox, not a measured width; a `ResizeObserver` workaround can re-enter and stack two charts.
- **One button, three mode flags.** `#createBrandBtn` is driven by `brandEditMode`, `presetBrandEditMode` and `presetCreateMode`, set by different open-paths. Any new path that opens the brand form must set — and every path that closes it must clear — all three.
- **`listings` has no `raw` column.** The `raw.__meta.semantically_cleared_fields` breadcrumb written by semantic cleaning therefore never reaches the warehouse for a *valid* listing — only `error_listings.raw_record` keeps the raw payload. Any plan that reads that marker for saved rows is built on nothing.
- **`business_id` is inside `content_hash`** (`CONTENT_HASH_FIELDS`), so two brand records can never collide on a hash. Any cross-brand dedupe keyed on `content_hash` is dead on arrival.
- **One dialog shell.** `<dialog class="app-help-dialog"> > .app-help-content > .app-help-header > <h2 id>`, plus `--editor` / `--form` / `--danger` modifiers. A test walks every `<dialog>` in `integrations.html`, so a new bespoke frame fails immediately.
- **Test markers are substrings.** In `FakeClient(query_results={...})`, `"listings`"` also matches `` error_listings` `` — qualify markers with the dataset (`"ds.listings`"`) or the wrong table's rows come back and the test passes for the wrong reason.

## Standing rules

- **Sample-load halves: SETTLED (user, 2026-09-09).** Keep the automatic second half — half 1 returns fast, half 2 self-starts in a background thread. No second click. Do not re-open or re-ask this.
- **Do not restart the server** unless explicitly asked (2026-09-09).
- **Do not commit or push** unless explicitly asked (I pushed once unprompted; won't recur).
- **Do not restart the server** unless asked.
- Backend (`.py`) changes need a restart to take effect — B8's server half and
  anything in O2 are written but **not live** until then.
