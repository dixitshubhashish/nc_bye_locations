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

| O1 | Background save after hiding progress | Confirm the save genuinely runs to completion after the layout resets, that completion/failure is announced, and that it is tracked in Job History. The layout reset landed; this half is unverified. |
| O2 | `content_hash` near-duplicate dedupe | `duplicateContentHashGroups()` helper is written but **not wired to any UI or endpoint**. Needs a backend source of listing-level `content_hash` overlap across brands, then surfacing next to the brand-merge rail. |
| O3 | Merge user-confirmation step | The rail's "Merge Others Into Keep" button is currently a direct action. An explicit themed confirm dialog naming what moves (listings/templates/review rows) is not built. |
| B21 | Sample load "always stops at 94%" | **FIXED** | It was never stuck. The bar was `Math.min(94, elapsed / estimate * 100)` — a pure time guess (15s/25s) hard-capped at 94, so any slower load parked there until the fetch returned. It measured nothing. Now shows the estimate only while it is still an estimate, then switches to an honest `Ns elapsed - larger batches take longer, this keeps running`. Trailing `...` removed per the spinner rule. Confirmed the loader already skips a failing brand (`except → continue`) and, since the `bad_row_index` fix, routes malformed rows to review rather than aborting — so nothing is blocking additional data. |

## Open — named, not started

| # | Bug | Detail |
|---|-----|--------|
| O4 | Per-table downloads (market gap, brand comparison) | Each reporting **table** should be downloadable with table-level relevancy — gap and comparison tables have their own shape and should not carry raw listing rows. Only the metric **cards** are downloadable today. |
| O5 | Extended Coverage Metrics panel duplicates/contradicts the top row | Verified: 3 exact duplicates (Active Brands, Total Stores, Covered Markets) and 4 **wrong** labels — "States covered 57" and "Cities covered 21,844" and "ZIP codes covered 41,618" are universe totals mislabelled as covered, and "Whitespace ZIPs 100" is `data.gaps.length`, i.e. the **page size**, not the real 33,840. Recommend deleting the panel; not yet removed. |
| O6 | Idle-time enrichment loop | Semantic cleaning now **clears** bad values and records them on `raw.__meta.semantically_cleared_fields`, but nothing yet runs on idle to **fill them back in**. |
| O7 | Test coverage | 52% overall; `workflow_server.py` at 48% with 66 functions never executed — including `reporting_metric_export` itself (which is why the live smoke, not a test, caught the `is_covered` SQL bug). |

---

## Standing rules

- **Do not restart the server** unless explicitly asked (2026-09-09).
- **Do not commit or push** unless explicitly asked.
- Backend (`.py`) changes need a restart to take effect — B8's server half and
  anything in O2 are written but **not live** until then.
