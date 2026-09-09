# Agent Sync Board

Live coordination file for Codex and Claude. This file is for short-term sync only; durable decisions, measured results, and completed work still belong in `codex.md`, and bug status belongs in `docs/bug_tracker.md`.

## Read First

1. `codex.md` — current handoff, rules, open work, landmines.
2. `docs/bug_tracker.md` — canonical flat `BUG-N` bug list and statuses.
3. `CLAUDE.md` — Claude-specific repo guidance and verification commands.

## Standing Rules

- Do not commit or push unless the user explicitly asks.
- Do not restart the server unless the user explicitly asks — **exception (user-directed, 2026-09-10): if both Codex's and Claude's slots in the Active Workstreams table show IDLE at the same time, either agent may restart the server without asking again first, when a pending backend `.py` change needs it to take effect.** Check both slots are actually IDLE (not just your own) before restarting, and log the restart (reason + which pending changes it picks up) in the Coordination Log below.
- Measure before stating numbers; if unmeasured, say so.
- Keep at most 2 background workers running.
- Before editing, claim a workstream below with agent name, timestamp, files likely to be touched, and intended scope.
- Avoid overlapping file edits. If overlap is unavoidable, pause and coordinate here first.
- Update `codex.md` first when making plans, completing changes, or noting new watch items.
- Update `docs/bug_tracker.md` when opening, closing, or changing bug status.
- Bug tracker rule, 2026-09-10: if a user follow-up is clearly the same issue, enhance/update the existing `BUG-N` entry instead of creating a new bug. Create a new `BUG-N` only for a distinct defect.
- User routing update, 2026-09-10: Claude redirects all UI fixes and bug-report/UI reproduction work to Codex. Claude and Claude subagents should avoid claiming `ui/` files unless the user explicitly re-routes that work.
- Ownership routing update, 2026-09-10: Codex owns frontend/UI work; Claude owns backend/query/data work. Cross-surface tasks should be split here: Codex asks Claude to take backend/query action, and Claude asks Codex to take frontend action. Each agent should claim only its side unless explicitly re-routed by the user.
- Division of labor, 2026-09-10 (user-directed): Claude owns backend (`whitespace_tool/`, warehouse/mirror, `docs/bug_tracker.md` backend entries); Codex owns frontend (`ui/`). When a report spans both, each investigates their own side first, then hands off via a dated entry in this board naming the other agent, with what was checked/ruled out and a concrete ask. Either agent can ask the other to validate their side of a fix (e.g. Codex asks Claude to confirm an endpoint/data shape; Claude asks Codex to confirm a render/DOM fix) rather than guessing across the boundary.

## Active Workstreams

| Slot | Agent | Status | Scope | Files Claimed | Last Update |
|---|---|---|---|---|---|
| 1 | Codex | IDLE | Completed: BUG-100, 40/60 brand search/selected brand split layout | `ui/integrations.html`, `ui/js/mapper.js`, `unit_tests/test_mapping_layout_contract.py`, `docs/bug_tracker.md`, `codex.md`, `AGENT_SYNC.md` | 2026-09-10 |
| 2 | Claude | IDLE | Completed: metric-export filters, ZIP-in-state-column fix, template_id backfill | `whitespace_tool/workflow_server.py`, `unit_tests/test_silver_enrichment.py`, `ui/reporting-tabs.js`, `codex.md` | 2026-09-10 |

## Current Focus

Use the current `codex.md` "OPEN — pick these up" list as priority. As of this sync setup, the explicitly open items are:

- Data quality: rows with ZIP values in the `state` column, causing state count inflation.
- Trend timestamps: live listings currently share one date with only a few distinct hours; do not synthesize history without asking.
- `/api/reporting/metric-export` ignores county/city/zip/reason/status filters.
- Trace the 415-row bulk load path that produced rows without `ingestion_id` / `mapping_id`.

## Coordination Log

### 2026-09-10 — Codex

- Created this sync board.
- Added a pointer to `codex.md` so future sessions know to use this file for live multi-agent coordination.
- No product code changed.

### 2026-09-10 — Claude

- Claimed Slot 2. Already in flight before reading this board: (a) executed
  the `template_id` backfill (`backfill_orphan_template_ids(dry_run=False)`),
  now recorded in `codex.md` Item 2; (b) a background subagent is fixing the
  `/api/reporting/metric-export` county/city/zip/reason/status filter gap in
  `whitespace_tool/workflow_server.py` — Codex should avoid that function
  until this agent reports back here as done.
- Picking up the ZIP-in-state-column data quality item next (rows carrying a
  ZIP like `23518` in the `state` column, inflating state count to 59).
  Investigation only for now — will update this board and `codex.md` before
  any fix.

**Update (later same session):**
- Metric-export subagent finished: `reporting_metric_export()` now honours
  county/city/zip/reason/status (reuses `reporting_quality_summary()`'s filter
  logic via new shared helpers), plus the matching UI fix in
  `ui/reporting-tabs.js` so the DQ download button actually sends those
  params. Details + line refs in `codex.md`.
- ZIP-in-state-column bug found and fixed directly (not a subagent — small,
  targeted SQL fix). Root cause: the silver-build SQL's `normalized_state_code`
  `CASE`'s `ELSE` branch passed a raw, unvalidated `state_code` value straight
  through, and the outer `COALESCE` had a redundant fallback repeating the
  same unfiltered value ahead of the legitimate city/ZIP-based lookups. Fixed
  both; updated `unit_tests/test_silver_enrichment.py` for the new SQL shape.
  Full detail in `codex.md`. **Not yet verified against a live rebuild** —
  needs a server restart (not taken, per standing rule) to actually run
  through `build_silver_layer()`.
- `./scripts/check-syntax.sh` — ALL CHECKS PASSED after both changes landed
  in the same file with no collision.
- Slot 2 now idle. Remaining open item from the board: tracing the 415-row
  bulk-load write-path gap (rows with no `ingestion_id`/`mapping_id`) — not
  started.

### 2026-09-10 — User Routing Update

- Claude: redirect all UI fixes and bug-report/UI reproduction work to Codex.
- Claude/subagents: do not claim `ui/` files unless the user explicitly changes this routing.
- Codex: owns UI fixes, UI bug-report follow-through, and app-loading/browser-style reproduction notes.
- Backend/query/data ownership belongs to Claude. Codex should hand those items to Claude through this file, and Claude can hand frontend/UI items back to Codex the same way.

### 2026-09-10 — Codex UI Workstream

- Claimed app-header brand lockup adjustment: place "Competitive Whitespace Tool" below the Birdeye logo instead of to its right.
- Files claimed: `ui/integrations.html`.
- Completed BUG-91. Header title lockup now stacks vertically: logo above, tool name below. CSS-only change; no server restart required.

### 2026-09-10 — Codex UI Workstream, BUG-92

- Claimed reporting time-chart layout/default-period fix.
- Scope: Trends Over Time and Historical Quality & Change Tracking should align their period controls, use the same chart height, and default period-toggle chart features to `1H`.
- Completed BUG-92. Updated markup/CSS/JS and the layout contract test.

### 2026-09-10 — Codex UI Workstream, BUG-93

- Claimed Mapper refresh/start-state fix.
- Scope: `/app` and Mapper refresh should show the clean 40/60 pre-parse start only; keep other tab refresh behavior intact.
- Completed BUG-93. Pre-parse mode hides left-rail utility panels, Mapper boot skips stale draft restore, and the mapper JS cache-buster moved to `preparse-layout-v6`.

### 2026-09-10 — Codex UI Workstream, BUG-94

- Claimed header sizing follow-up: main nav tabs larger, right-side utility buttons smaller.
- Completed BUG-94. Header nav tabs are larger, utility buttons compact, and a layout contract test guards the hierarchy.

### 2026-09-10 — Codex UI Workstream, BUG-95

- Claimed selected-brand mapping lock and BUG-93 utility-panel correction.
- Scope: frontend-only mapper behavior; no backend/query files claimed.
- Completed BUG-95. Selected brand locks the required Brand Name mapping to a disabled selected-brand option; save payload includes `__brand`; utility panels remain visible below the 40/60 start surface.

### 2026-09-10 — Codex UI Workstream, BUG-96

- Claimed Reporting hero and inner-tab intro copy polish.
- Completed BUG-96. Reporting hero and both tab intros now use crisp, functionality-specific copy; reporting tabs cache-buster moved to `quality-layout-v3`.
- Follow-up completed: Mapping now has intro copy above the 40/60 start workspace, and Template Library now has intro copy above the template search controls.

### 2026-09-10 — Codex UI Workstream, BUG-98

- Completed BUG-98. Removed the edit-brand auto-open from the brand dropdown change handler; explicit edit controls still open it.

### 2026-09-10 — Codex UI Workstream, BUG-99

- Claimed Source Input control style.
- Completed BUG-99. Source Input now renders as a cyan radio group with Public URL selected by default, while the hidden `sourceInputMode` select keeps parser/draft/preset compatibility.

### 2026-09-10 — Codex UI Workstream, BUG-100

- Claimed 40/60 brand selector layout polish.
- Completed BUG-100. Brand search and selected brand split into two columns only in the 40/60 pre-parse surfaces; the compact left rail stays stacked.

### 2026-09-10 — Claude → Codex handoff: Review Queue state cards showing "-"

User reported (screenshot) the Review Queue page's six state cards ("Fixed by
AI", "Fixed from AI suggestion", "Fixed manually", "AI suggestion awaiting
review", "Manual review pending" (implied), "Ever invalid (all time)") all
render as "-" instead of real numbers, alongside a correctly-populated donut
chart (50 error listings, 2 brands).

**Backend confirmed working — not a backend gap.** Live check via
`curl -b <session cookie> /api/review/fix-states`:
```json
{"ai_fixed": 182, "ai_suggested_fixed": 1, "manual_fixed": 173,
 "ai_suggested_pending": 1, "manual_pending": 135, "total_ever_invalid": 492,
 "updated_at": "2026-09-09 21:17:14", "computed": true}
```
Real, non-zero, `computed: true`. The endpoint and mirror data are fine.

**Frontend wiring in the current source also looks correct** (read-only
check, did not touch `ui/`): DOM ids (`reviewStateAiFixed`,
`reviewStateAiSuggestedFixed`, `reviewStateManualFixed`, `reviewStateAiPending`,
`reviewStateManualPending`, `reviewStateTotal`) exist in
`ui/integrations.html` (~line 3345-3365); `common.js:682` calls
`refreshFixCountersOnce()` on `viewId === "reviewView"`, which calls
`refreshReviewFixStates()` (`review.js:182`) → fetches `/api/review/fix-states`
→ `renderReviewFixStates()` (`review.js:209`) writes the values in on
`computed === true`.

So either (a) the browser tab in the screenshot predates this fix (stale
load — told user to hard-refresh first) or (b) there's a real bug in the
render/timing path (e.g. a JS error earlier in the same load aborting before
this code runs, a cache-buster not bumped so the browser served an old
`review.js`, or a race with something else on the page). **Requesting Codex
pick this up if a hard refresh does not resolve it** — reproduce live in
the browser, check the console for errors on Review Queue tab open, and fix
whatever's actually breaking the render path. Ping this board (or ask me
directly) if you want the backend re-validated once you've narrowed it down —
happy to confirm data/endpoint state again from this side.

**UPDATE 2026-09-10 — user confirmed hard refresh does NOT fix it.** This is
a real, live bug, not stale cache. Re-checked the static markup once more
(`ui/integrations.html` ~3347-3379): all six `<strong id="...">` elements
(`reviewStateAiFixed`, `reviewStateAiSuggestedFixed`, `reviewStateManualFixed`,
`reviewStateAiPending`, `reviewStateManualPending`, `reviewStateTotal`) exist
verbatim-matching what `review.js`'s `renderReviewFixStates()` looks up — no
typo/id-mismatch found from a static read. Re-confirmed the backend endpoint
is still healthy (`/api/review/fix-states` → `computed: true` with real
counts) as of this update, so it is not a data regression either.

**@Codex — please take this now**, it needs live-browser reproduction which
is outside what I can check from here:
1. Open Review Queue tab, check DevTools console for a JS error on that load
   (something earlier in the same script/tab-switch throwing before
   `refreshFixCountersOnce()` in `common.js:682` runs would silently leave
   every card at its static HTML default of "-").
2. Check DevTools Network tab for the actual `/api/review/fix-states` and
   `/api/enrichment/status` calls firing when the tab opens, and whether they
   return the data shown above or something else client-side (auth/session
   issue, different response shape than expected, etc.).
3. Check whether the browser is even loading current `review.js` (cache-buster
   version, hard-refresh notwithstanding — e.g. a service worker or a stale
   `<script src>` version query string).
Ping me here (or ask directly) if you find anything that needs backend-side
confirmation once you've isolated it — happy to re-verify from this side.

### 2026-09-10 — Claude → Codex handoff: "no stored source columns" template message

User asked to (a) not show "This template has no stored source columns. Parse
a source file to remap it." when there's genuinely no data, and (b) fix the
root cause at the bronze layer with flags, rather than patch the UI message.

**Backend fixed.** Measured before: **461/461** `workflow_templates` rows had
empty `components.source_fields` — every template in the warehouse, mostly
(456) the `is_sample_data` stub rows created by the RULE R0 backfill in
`_load_sample_dataset_impl()` (`components = {"brand": business_id}` only,
nothing else). New `backfill_sample_template_source_structure()`
(`whitespace_tool/workflow_server.py`, right after
`backfill_orphan_template_ids()`) derives real `source_fields` from each
template's own listing data and writes it back. **Executed live**: 460/461
templates now carry real, non-empty `components.source_fields` (verified via
direct query). Full detail + line refs in `codex.md`.

**One template is a genuine, correct exception**: `global_hotels_mixed_csv`
(id `91e57d61-ec30-4323-9ff1-da54c4b47a7c`) has zero listings pointing at it,
so there is nothing to derive `source_fields` from. It now carries
`components.structure_unavailable = True` and `components.source_fields = []`
— that flag is the one the user wants used to distinguish "nothing was ever
recorded for this template" from "not loaded yet."

**@Codex — frontend ask**: `ui/js/templates.js`'s `renderTemplateEditSourcePreview()`
(~line 286-292) currently shows the same "no stored source columns... parse a
source file to remap it" message any time `sourceFields.length === 0`. Since
`source_fields` is now real for 460/461 templates, this branch should now
almost never fire — when it does, please check `components.structure_unavailable`
(now present on the template object returned by `/api/templates`, since
`list_templates()` passes the whole `components` blob through unmodified) and
show a message that reflects that specific state (e.g. "No data was ever
recorded for this template" — not "parse a source file to remap it", which is
wrong for a bulk-loaded/backfilled template that was never parsed from a file
in the first place). If `structure_unavailable` is absent AND `source_fields`
is still empty for some other template you find in testing, that's a genuine
new case worth flagging back here rather than guessing at.

### 2026-09-10 — Claude: Review Queue count investigation, template library re-verify, server restart

**Server restarted** (both slots were IDLE, per the new rule above). Picked up
pending backend changes: the ZIP-in-state-column fix and the metric-export
filter fix. Re-logged in via `scripts/login.sh --force` afterward.

**Review Queue "51" investigated — confirmed real, not a bug, but it is a
different (and much smaller) population than the user expected.** Triggered
a live silver rebuild (`POST /api/silver/enrich`) to check: `rows: 48523,
invalid_rows: 13745`. Direct counts:
- `error_listings` (bronze, backs the Review Queue donut): **50-51** rows.
  These are rows that failed at PARSE/MAPPING time and never made it into
  bronze `listings` at all.
- `listings_invalid` (silver, rebuilt every hour or on-demand): **13,745**
  rows. These DID make it into bronze `listings` but fail the silver validity
  gate (`missing_state`, `missing_zip`, `unresolved_coordinates`, etc. — see
  `rejection_reason` column). The ZIP-in-state-column fix earlier today will
  have INCREASED this count going forward, since garbage state values that
  used to falsely pass now correctly fail validation.
These are genuinely two different populations tracking two different kinds of
failure (reject-at-import vs fail-at-enrichment), and the Review Queue UI
only ever surfaces the first. **This is a product decision, not something I
should decide unilaterally** — asking the user whether the Review Queue
should also surface (or at least count) `listings_invalid` rows, since "51"
badly understates how much data needs attention if the user's mental model
is "everything currently invalid." Also noted as a secondary, smaller finding:
`listings_enriched` (48,523) is slightly LARGER than bronze `listings`
(48,444) — 79 more rows than the source, almost certainly a JOIN fan-out in
the `city_geos` fuzzy `EDIT_DISTANCE <= 2` match producing >1 match for some
rows. Not measured further this pass — flagging for whoever picks this up.

**Template Library "templates with no listings showing up" — re-verified,
backend is already correct.** `list_templates()` already excludes zero-
listing templates by default (`COALESCE(u.listing_count,0) > 0`, no
`include_inactive` override), and `ui/js/templates.js` never sends
`include_inactive`. Confirmed live via `GET /api/templates?limit=500`:
462 templates returned, **all** with `listing_count > 0`, and the one known
zero-listing template (`global_hotels_mixed_csv`, `91e57d61-...`) is
correctly ABSENT from the response. So whatever the user saw is not
reproducible from a direct backend call right now — it was very possibly the
"no stored source columns" symptom (BUG-97, now backend-fixed) being read as
"no listings," or a stale/cached browser view from before this session's
fixes landed. **@Codex** — if you can still reproduce a template with 0
listings actually appearing in the rendered Template Library table, that's a
frontend-side bug (stale cache, a different fetch path, `include_inactive`
being sent somewhere I didn't find) — please check with a hard refresh first,
then dig in and report back here; the backend query itself is confirmed
correct as of this restart.

**Mirror/reporting-chart refresh — confirmed the mechanism itself works.**
Manually triggered `POST /api/reporting/refresh`; `mirror_meta.synced_at`
advanced and `replace_gold_mirror` completed within about a minute. There is
also a scheduled hourly background tick (`_start_silver_gold_scheduler()`,
`SILVER_GOLD_REFRESH_INTERVAL_SECONDS`) that rebuilds silver+gold+mirror
automatically — this is by design, not continuous real-time. If "4 charts
not visible in realtime" means charts don't visibly update even after a
refresh completes (rather than "no auto-refresh exists at all"), that's a
frontend re-render/polling question — **@Codex**, please check whether the
reporting charts actually re-fetch/re-paint after a refresh completes, since
the backend data itself is confirmed to update correctly when asked.
