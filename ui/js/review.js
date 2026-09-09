// Review Error Listings tab: rejected-record search and the edit/retry modal.

let currentEditingRecord = null;
let loadRejectedRecordsPromise = null;
let reviewBrandNames = {};
let autoRepairPollTimer = null;
let aiFixedAnimationTimer = null;
let reviewPage = 0;
// Records currently rendered in the review queue, keyed by event_id::row_number
// (the same pair the button carries in its dataset). The click handler reads
// this instead of closing over a per-render array, so it never depends on a
// listener being re-attached after a re-render.
const reviewRecordsByKey = new Map();
// Templates per business_id. Opening the edit dialog used to fetch these on
// every single click, sequentially after the brands fetch - two round trips
// before anything rendered, which is the delay felt on "Manual Review" /
// "AI Suggested Fix". A template rarely changes mid-session, so one fetch
// per business is enough.
const reviewTemplateCache = new Map();

// ONE document-level listener, installed at load. Deliberately not attached
// per render: any throw between drawing the table and attaching a listener
// used to leave the buttons visible but dead. Capture phase so a stray
// stopPropagation() upstream cannot swallow the click either.
document.addEventListener("click", (event) => {
  const button = event.target?.closest?.("button[data-open-edit]");
  if (!button) return;
  event.preventDefault();
  const record = reviewRecordsByKey.get(`${button.dataset.event}::${button.dataset.openEdit}`);
  if (record) {
    openEditRecordModal(record);
  } else {
    // Surfacing this beats a button that silently does nothing.
    console.warn("review: no record for", button.dataset.event, button.dataset.openEdit);
  }
}, true);
const REVIEW_PAGE_SIZE = 50;

async function reviewFetch(url, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

function formatAiFixedCount(value, exact = false) {
  const count = Math.max(0, Number(value) || 0);
  if (exact || count < 1000) return Math.round(count).toLocaleString();
  const compact = count / 1000;
  return `${compact.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}k`;
}

function animateAiFixedCount(targetValue) {
  const target = el("reviewAiFixedCount");
  if (!target) return;
  const finalValue = Math.max(0, Number(targetValue) || 0);
  const currentText = target.dataset.exactValue || "0";
  let current = Number(currentText) || 0;
  if (aiFixedAnimationTimer) window.clearInterval(aiFixedAnimationTimer);
  if (current >= finalValue) {
    target.dataset.exactValue = String(finalValue);
    target.textContent = formatAiFixedCount(finalValue, true);
    return;
  }
  aiFixedAnimationTimer = window.setInterval(() => {
    const remaining = finalValue - current;
    current += Math.max(1, Math.ceil(remaining / 12));
    if (current >= finalValue) {
      current = finalValue;
      window.clearInterval(aiFixedAnimationTimer);
      aiFixedAnimationTimer = null;
    }
    target.dataset.exactValue = String(current);
    target.textContent = formatAiFixedCount(current, current === finalValue);
  }, 80);
}

async function autoRepairReviewBatch() {
      const button = el("autoRepairReviewBtn");
      const target = el("reviewAutoRepairStatus") || el("reviewResults");
      const previousButton = setButtonBusy(button, "Auto-Fixing");
      try {
        const response = await fetch("/api/review/auto-repair", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Automatic repair could not be started.");
        if (result.status === "started" || result.status === "running") {
          button.dataset.autoRepairing = "true";
          target.className = "status";
          target.innerHTML = `${busyMarkup("Auto-Fixing review records")} Processing 1 record at a time. ${result.processed || 0} processed so far. The next record will continue automatically.`;
          if (!autoRepairPollTimer) autoRepairPollTimer = window.setInterval(pollAutoRepairStatus, 2000);
          return;
        }
        const remaining = Number(result.remaining || 0);
        target.className = "status ok";
        target.textContent = result.attempted
          ? `${result.resolved} of ${result.attempted} records fixed automatically. ${remaining} still need manual review.`
          : "No review records are currently available for automatic fixing.";
        await loadRejectedRecords();
      } catch (error) {
        target.className = "status error";
        target.textContent = productSafeError(error.message, "Automatic repair could not be completed.");
        addStatusClose(target);
      } finally {
        if (button?.dataset.autoRepairing !== "true") clearButtonBusy(button, previousButton);
      }

// Cumulative five-state counts for the review tab's cards.
let reviewFixStates = null;

let reviewFixStateRetries = 0;
const REVIEW_FIX_STATE_RETRY_LIMIT = 5;
const REVIEW_FIX_STATE_RETRY_DELAY_MS = 4000;

async function refreshReviewFixStates() {
      try {
        // Dedicated mirror-backed endpoint, NOT /api/reporting/quality: these
        // six numbers live in SQLite and must not wait on - or fail with -
        // that endpoint's heavy aggregation. That coupling is why every card
        // showed "-" while the correct values sat on disk.
        const response = await fetch("/api/review/fix-states", { cache: "no-store" });
        const data = await response.json();
        if (!response.ok) return;
        if (data.computed === true) {
          reviewFixStateRetries = 0;
          reviewFixStates = data;
          renderReviewFixStates();
          return;
        }
        // Not computed yet, but a recount is running - come back for it
        // rather than leaving dashes on screen for the rest of the session.
        if (data.refreshing && reviewFixStateRetries < REVIEW_FIX_STATE_RETRY_LIMIT) {
          reviewFixStateRetries += 1;
          window.setTimeout(refreshReviewFixStates, REVIEW_FIX_STATE_RETRY_DELAY_MS);
        }
      } catch (_) {
        // Leave whatever is displayed; a transient failure must not blank
        // correct numbers (the same mistake the old `|| 0` default made).
      }
    }

function renderReviewFixStates() {
      const states = reviewFixStates;
      const cards = [
        ["reviewStateAiFixed", "ai_fixed"],
        ["reviewStateAiSuggestedFixed", "ai_suggested_fixed"],
        ["reviewStateManualFixed", "manual_fixed"],
        ["reviewStateAiPending", "ai_suggested_pending"],
        ["reviewStateManualPending", "manual_pending"],
        ["reviewStateTotal", "total_ever_invalid"],
      ];
      // "Not computed yet" is shown as a dash, never as zero - a zero here
      // would read as "nothing has ever been invalid", which is a claim.
      const computed = states && states.computed === true;
      cards.forEach(([id, key]) => {
        const node = el(id);
        if (node) node.textContent = computed ? Number(states[key] || 0).toLocaleString() : "-";
      });
      renderAiFixedShare();
    }

function renderFixCounters(state) {
  // RPT-13 follow-up: `state.auto_repair?.x || 0` meant ANY status response
  // that omitted auto_repair (an early poll, a partial/errored payload, a
  // response shape without it) rendered all four counters as 0 - wiping
  // correct, durable numbers off the screen and making it look like the
  // fixes had been lost. They never were: BigQuery quality_fix_events and
  // the SQLite mirror both hold them. Absent data must leave the existing
  // numbers alone; only a real payload may update them.
  const stats = state && typeof state.auto_repair === "object" && state.auto_repair ? state.auto_repair : null;
  if (!stats) return;
  // Five-state cards: the same cumulative counts the reporting tab shows, so
  // the two can never disagree. Read from the quality payload's fix_states,
  // which is mirror-backed (instant paint, BigQuery authoritative).
  renderReviewFixStates();
  const fixedCount = el("reviewAiFixedCount");
  if (fixedCount) animateAiFixedCount(Number(stats.fixed) || 0);
  const manualFixedCount = el("reviewManualFixedCount");
  if (manualFixedCount) manualFixedCount.textContent = formatAiFixedCount(Number(stats.manual_fixed) || 0, true);
  renderAiFixedShare();
}

// "AI Fixed by Total Error" sits directly beside the five cumulative cards,
// so it has to be computed from the SAME numbers or it contradicts them on
// screen. It used to divide the CURRENT auto-repair batch's counters
// (fixed / fixed+manual_fixed+remaining) - which reset to 0 whenever a new
// batch starts, so it read "0.00%" next to cards showing 110 AI fixes.
// Cumulative AI fixes over everything that was ever invalid is the figure
// the label actually claims.
function renderAiFixedShare() {
  const aiPercent = el("reviewAiFixedPercent");
  if (!aiPercent) return;
  const states = reviewFixStates;
  if (!states || states.computed !== true) {
    // Not measured yet is a dash, never "0.00%" - a zero here is a claim
    // that the AI has fixed nothing, which is a different statement.
    aiPercent.textContent = "-";
    return;
  }
  const total = Number(states.total_ever_invalid || 0);
  const ai = Number(states.ai_fixed || 0);
  const manual = Number(states.manual_fixed || 0);
  aiPercent.textContent = total ? `${(ai / total * 100).toFixed(2)}%` : "-";
  const manualPercent = el("reviewManualFixedPercent");
  if (manualPercent) manualPercent.textContent = total ? `${(manual / total * 100).toFixed(2)}%` : "-";
}
async function refreshFixCountersOnce() {
  // These counters only ever updated while an active auto-repair run was
  // polling - a fresh page load (including right after logging back in)
  // left them frozen at their static HTML default of "0" until the user
  // happened to start a new run, even though the real, persisted count
  // (reconciled from the durable quality_fix_events BigQuery log) was
  // available the whole time. One fetch on load/tab-open is enough; no
  // interval needed outside of an active run.
  if (!el("reviewAiFixedCount")) return;
  try {
    const response = await fetch("/api/enrichment/status", { cache: "no-store" });
    const state = await response.json();
    if (response.ok) renderFixCounters(state);
  } catch (_) {}
  // Cumulative five-state counts come from the quality payload, not the
  // live auto-repair status - fetched alongside so both land together.
  refreshReviewFixStates();
}
async function pollAutoRepairStatus() {
  const button = el("autoRepairReviewBtn");
  const target = el("reviewAutoRepairStatus") || el("reviewResults");
  try {
    const response = await fetch("/api/enrichment/status", { cache: "no-store" });
    const state = await response.json();
    renderFixCounters(state);
    if (state.state === "running") {
      if (target) target.innerHTML = `${busyMarkup("Auto-Fixing review records")} ${Number(state.processed || 0)} records processed. The next record will continue automatically. ${Number(state.auto_repair?.remaining || 0).toLocaleString()} need manual review.`;
      const manualCount = el("reviewManualCount");
      if (manualCount) manualCount.textContent = `${Number(state.auto_repair?.remaining || 0).toLocaleString()} need manual review`;
      return;
    }
    window.clearInterval(autoRepairPollTimer);
    autoRepairPollTimer = null;
    if (button) { delete button.dataset.autoRepairing; button.disabled = false; button.innerHTML = "Try Auto-Fixing with AI"; }
    if (target) {
      target.className = state.state === "failed" ? "status error" : "status ok";
      const remaining = Number(state.auto_repair?.remaining || 0);
      target.textContent = state.state === "stopped" ? `${remaining.toLocaleString()} need manual review. Automatic fixing stopped.` : `${remaining.toLocaleString()} need manual review. Automatic fixing completed.`;
      const manualCount = el("reviewManualCount");
      if (manualCount) manualCount.textContent = `${remaining.toLocaleString()} need manual review`;
    }
    await loadRejectedRecords();
  } catch (_) {}
}
    }

async function loadReviewBrandFilter() {
      const select = el("reviewBrandFilter");
      if (!select || select.options.length > 1) return;
      try {
        // Review filtering is intentionally based only on impacted brands;
        // the global brand catalog belongs to Mappings and Template Library.
        const res = await reviewFetch("/api/error-listings/by-brand", { cache: "no-store" });
        const data = await res.json();
        if (res.ok && Array.isArray(data.brands)) {
          const impactedBrands = data.brands.filter((brand) => Number(brand.count || 0) > 0);
          reviewBrandNames = Object.fromEntries(impactedBrands.map(b => [b.business_id, formatBrandName(b.brand || b.business_id)]));
          const currentVal = select.value;
          select.innerHTML = '<option value="">All Brands</option>' + impactedBrands.map(b => `<option value="${escapeHtml(b.business_id)}">${escapeHtml(formatBrandName(b.brand || b.business_id))}</option>`).join("");
          select.value = currentVal || "";
        }
      } catch (err) {
        // Soft fail
      }
    }

// login-hotfix.js and integrations.html's own bootstrap script can each
// independently call switchView("reviewView") on the same page load (the
// hotfix script loads async, so ordering isn't guaranteed) - without this
// guard, two concurrent runs race on the Search button's "restore original
// html" step: whichever finishes last can restore the OTHER call's
// mid-spin snapshot, leaving the button stuck spinning even though
// #reviewResults already rendered real records from the call that won.
function loadRejectedRecords() {
      if (loadRejectedRecordsPromise) return loadRejectedRecordsPromise;
      loadRejectedRecordsPromise = _loadRejectedRecordsOnce().finally(() => {
        loadRejectedRecordsPromise = null;
      });
      return loadRejectedRecordsPromise;
    }
async function _loadRejectedRecordsOnce() {
      const target = el("reviewResults");
      const searchBtn = el("reviewSearchBtn");
      const originalSearchBtnHtml = searchBtn ? searchBtn.innerHTML : "Search Records";

      if (searchBtn) setButtonBusy(searchBtn, "Searching");

      target.className = "status";
      target.textContent = "Loading error listings";
      try {
        await loadReviewBrandFilter();
        const eventId = el("reviewEventId").value.trim();
        const brandFilter = el("reviewBrandFilter")?.value || "";
        const response = await reviewFetch(`/api/rejected?event_id=${encodeURIComponent(eventId)}&business_id=${encodeURIComponent(brandFilter)}&limit=${REVIEW_PAGE_SIZE}&offset=${reviewPage * REVIEW_PAGE_SIZE}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load review records.");
        // Client-side, on this page's already-fetched batch - the same
        // heuristic that colors each row's action button, so "AI Suggested
        // Fix" here always matches what the filter picked.
        const fixTypeFilter = el("reviewFixTypeFilter")?.value || "";
        if (fixTypeFilter) {
          result.records = result.records.filter((record) => {
            const isSuggested = recordHasSuggestionAvailable(record);
            return fixTypeFilter === "ai_suggested" ? isSuggested : !isSuggested;
          });
        } else {
          // No explicit filter: interleave AI-suggested and manual rows so
          // both get equal attention. The server orders by event_id/row_number,
          // which clusters a whole brand's suggested rows together - so the
          // first page could be entirely one kind and the other kind never
          // got looked at. Whichever list is longer supplies the tail.
          const suggested = result.records.filter(recordHasSuggestionAvailable);
          const manual = result.records.filter((record) => !recordHasSuggestionAvailable(record));
          if (suggested.length && manual.length) {
            const interleaved = [];
            for (let i = 0; i < Math.max(suggested.length, manual.length); i += 1) {
              if (i < suggested.length) interleaved.push(suggested[i]);
              if (i < manual.length) interleaved.push(manual[i]);
            }
            result.records = interleaved;
          }
        }
        if (!result.records.length) {
          // Nothing to act on - drop the store so a stale record can never
          // be reopened from a previous page of results.
          reviewRecordsByKey.clear();
          target.textContent = "No error listings found.";
          return;
        }
        target.className = "";
        target.innerHTML = `<table><thead><tr><th data-sort-key="event">Event</th><th data-sort-key="brand">Brand</th><th data-sort-key="row" data-sort-type="number">Row</th><th>Issues & Hints</th><th>Source Record</th><th>Action</th></tr></thead><tbody>${result.records.map((record) => {
          let errs = record.errors;
          if (typeof errs === 'string') {
            try { errs = JSON.parse(errs); } catch (e) { errs = []; }
          }
          const hintsHtml = Array.isArray(errs) ? errs.map(e => `
            <div style="background: #fff1f0; border: 1px solid #ffa39e; border-radius: 4px; padding: 4px 8px; margin-bottom: 4px; font-size: 12px; color: #cf1322;">
              <strong>⚠️ ${escapeHtml(formatFieldLabel(e.field) || 'Field')}</strong>: ${escapeHtml(e.hint || e.reason || 'Invalid value')} <em>(${escapeHtml(e.value || 'empty')})</em>
            </div>
          `).join('') : escapeHtml(JSON.stringify(record.errors));

          const rawBrand = record.raw_record && typeof record.raw_record === "object" ? (record.raw_record.brand || record.raw_record.Brand || "") : "";
          const brandDisplayName = reviewBrandNames[record.business_id] || formatBrandName(rawBrand || record.business_id || "—");

          const hasSuggestionAvailable = recordHasSuggestionAvailable(record);
          const attemptCount = Number(record.attempt_count || 0);
          // Effort icon (figure pushing a boulder uphill) instead of the words
          // "Attempt N" - it reads at a glance in a dense table. Drawn inline
          // rather than linked: the page's CSP blocks external images, and an
          // inline path carries no third-party licensing question. The full
          // sentence stays in the tooltip for anyone who needs it.
          const attemptBadge = attemptCount > 0
            ? `<span class="review-attempt-badge" title="Reviewed ${attemptCount} time${attemptCount === 1 ? "" : "s"} already" aria-label="Reviewed ${attemptCount} time${attemptCount === 1 ? "" : "s"} already">
                 <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
                   <line x1="2" y1="21" x2="21" y2="8"></line>
                   <circle cx="16.5" cy="10" r="4"></circle>
                   <circle cx="6.2" cy="6.6" r="1.7"></circle>
                   <path d="M5 9.4h4.3l-1.6 3.4 2.2 1.9-.5 3.6"></path>
                   <path d="M4.2 18.9l1.4-3.1"></path>
                 </svg>${attemptCount}</span>`
            : "";
          const actionButtonHtml = hasSuggestionAvailable
            ? `<button type="button" class="review-fix-suggested" data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}" style="background:#1677ee; border-color:#1677ee; color:#fff;">🤖 AI Suggested Fix</button>`
            : `<button type="button" class="review-fix-manual" data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}" style="background:#fff; border-color:#d97706; color:#b45309;">🛠️ Manual Review</button>`;

          return `<tr>
            <td data-sort-value="${escapeHtml(record.event_id)}" style="font-family: monospace; font-size: 11px;">${escapeHtml(record.event_id)}</td>
            <td data-sort-value="${escapeHtml(brandDisplayName)}"><strong>${escapeHtml(brandDisplayName)}</strong></td>
            <td data-sort-value="${escapeHtml(record.row_number)}"><strong>#${escapeHtml(record.row_number)}</strong></td>
            <td style="max-width: 320px;">${hintsHtml}</td>
            <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace; font-size: 11px;">${escapeHtml(JSON.stringify(record.raw_record))}</td>
            <td class="review-row-actions">
              ${actionButtonHtml}${attemptBadge}
            </td>
          </tr>`;
        }).join("")}</tbody></table>`;
        enableSortableTable(target.querySelector("table"));
        target.insertAdjacentHTML("beforeend", `<div class="review-pagination" style="display:flex; justify-content:center; gap:8px; margin-top:12px;"><button type="button" class="secondary" data-review-page="prev" ${reviewPage === 0 ? "disabled" : ""}>Previous</button><span style="padding:8px 4px; color:var(--muted);">Page ${reviewPage + 1}</span><button type="button" class="secondary" data-review-page="next" ${result.has_more ? "" : "disabled"}>Next</button></div>`);
        target.querySelector('[data-review-page="prev"]')?.addEventListener("click", () => { reviewPage -= 1; loadRejectedRecords(); });
        target.querySelector('[data-review-page="next"]')?.addEventListener("click", () => { reviewPage += 1; loadRejectedRecords(); });
        // Publish the rendered records for the document-level click handler
        // (installed once at load, see reviewRecordsByKey). Binding a
        // listener HERE was fragile: anything that threw between rendering
        // the table and reaching this line - a sort helper, the pagination
        // insert - left visible buttons with no listener at all, which is
        // exactly how "Manual Review" / "AI Suggested Fix" ended up dead on
        // click. A handler that is already attached cannot be skipped.
        reviewRecordsByKey.clear();
        (result.records || []).forEach((record) => {
          reviewRecordsByKey.set(`${record.event_id}::${record.row_number}`, record);
        });
      } catch (error) {
        target.className = "status error";
        target.textContent = error.name === "AbortError"
          ? "Loading review records took too long. Please try Search Records again."
          : productSafeError(error.message, "Could not load review records.");
        addStatusClose(target);
      } finally {
        if (searchBtn) {
          clearButtonBusy(searchBtn, originalSearchBtnHtml);
        }
      }
    }
function getNestedRawValue(row, path) {
      if (!path) return "";
      let current = row;
      for (const part of path.split(".")) {
        if (current && typeof current === "object") current = current[part];
        else return "";
      }
      return current !== null && current !== undefined ? current : "";
    }
// A rough, list-view approximation of the edit dialog's own needsZip/
// needsLatLon check (openEditRecordModal's suggestion box) - good enough to
// decide whether a record routes to "AI Suggested Fix" or "Manual Review"
// (both the button color/label and the review-queue filter dropdown use
// this same function, so they never disagree) without loading full mapper
// field config per row. When a city is known but the ZIP looks incomplete,
// the same quick-fill suggestion the dialog offers will very likely have
// something to offer.
function recordHasSuggestionAvailable(record) {
      const raw = record.raw_record && typeof record.raw_record === "object" ? record.raw_record : {};
      const cityGuess = raw.city || raw.City || raw.city_name || "";
      const zipGuess = String(raw.zip || raw.postal_code || raw.Zip || raw.PostalCode || "");
      return Boolean(cityGuess) && zipGuess.length < 5;
    }

// Set true when the user one-click-adopts a system suggestion (the
// "Suggested ZIP + coordinates" quick-fill) rather than typing a manual
// correction - the submit handler reads this to attribute the fix to AI
// Fixed instead of Fixed Manually, matching the decision that an adopted
// suggestion counts as an automatic fix even though a human clicked it.
let suggestionAdopted = false;

// Renders the two-option hierarchy-conflict picker (ZIP-derived vs
// coordinate-derived location) inside the edit form when reprocess_rejected()
// detects the record's ZIP and lat/lon disagree by more than the 50km snap
// cap. Picking either option fills the form fields and marks the fix as
// AI-resolved (via suggestionAdopted) rather than silently guessing one side.
// When a record's coordinates genuinely fall outside the US (not a
// mismatch to resolve, but real worldwide data), the backend already
// looked up what's actually at that lat/lon via the worldwide cities
// reference. Offer it as an explicit "accept as non-US" choice rather than
// silently rejecting the record or guessing - picking it fills country/
// state/city/ZIP and marks the fix AI-resolved (via suggestionAdopted),
// and setting country here is what lets validate_normalized_location()
// exempt the record from the US-boundary check on the next attempt instead
// of asking the same question again.
function renderNonUsSuggestion(suggestion) {
      const formEl = el("editRecordForm");
      if (!formEl || !suggestion || (!suggestion.city && !suggestion.country)) return;
      const existing = document.getElementById("nonUsSuggestionBox");
      if (existing) existing.remove();

      const box = document.createElement("div");
      box.id = "nonUsSuggestionBox";
      box.style.gridColumn = "1 / -1";
      box.style.background = "#eff6ff";
      box.style.border = "1px solid #93c5fd";
      box.style.borderRadius = "6px";
      box.style.padding = "10px 12px";
      box.style.fontSize = "12px";
      box.style.color = "#1e40af";
      box.style.marginBottom = "8px";
      const distanceNote = suggestion.distance_km ? ` (~${escapeHtml(suggestion.distance_km)} km away)` : "";
      box.innerHTML = `<strong>🌍 These coordinates look like real data outside the US${distanceNote}: ${escapeHtml(suggestion.city || "—")}, ${escapeHtml(suggestion.state || "—")}, ${escapeHtml(suggestion.country || "—")}${suggestion.zip_code ? ` · ${escapeHtml(suggestion.zip_code)}` : ""}.</strong>
        <button type="button" id="saveAsNonUsBtn" class="secondary" style="display:block; width:100%; text-align:left; margin-top:6px; padding:6px 10px; border:1px solid #93c5fd; background:#fff; cursor:pointer; color:#1e40af;">Save as Non-US Data</button>`;
      formEl.insertBefore(box, formEl.firstChild);

      box.querySelector("#saveAsNonUsBtn")?.addEventListener("click", () => {
        suggestionAdopted = true;
        const setField = (type, value) => {
          const input = formEl.querySelector(`[data-field-type='${type}']`);
          if (input && value !== null && value !== undefined) input.value = value;
        };
        setField("city", suggestion.city);
        setField("state", suggestion.state);
        setField("country", suggestion.country);
        if (suggestion.zip_code) setField("postal_code", suggestion.zip_code);
        box.remove();
      });
    }

function renderHierarchyConflictPicker(conflict) {
      const formEl = el("editRecordForm");
      if (!formEl || !conflict) return;
      const existing = document.getElementById("hierarchyConflictBox");
      if (existing) existing.remove();

      const renderOption = (key, label, option) => {
        if (!option) return "";
        return `<button type="button" class="secondary" data-hierarchy-option="${key}" style="display:block; width:100%; text-align:left; margin-top:6px; padding:6px 10px; border:1px solid #fcd34d; background:#fff; cursor:pointer;">
          <strong>${escapeHtml(label)}</strong><br>
          <span style="font-size:11px; color:#78350f;">${escapeHtml(option.city || "—")}, ${escapeHtml(option.state || "—")}, ${escapeHtml(option.country || "—")} &middot; ZIP ${escapeHtml(option.zip_code || "—")} &middot; (${option.latitude}, ${option.longitude})</span>
        </button>`;
      };

      const box = document.createElement("div");
      box.id = "hierarchyConflictBox";
      box.style.gridColumn = "1 / -1";
      box.style.background = "#fffbeb";
      box.style.border = "1px solid #fcd34d";
      box.style.borderRadius = "6px";
      box.style.padding = "10px 12px";
      box.style.fontSize = "12px";
      box.style.color = "#92400e";
      box.style.marginBottom = "8px";
      box.innerHTML = `<strong>⚠️ ZIP and coordinates disagree (~${escapeHtml(conflict.distance_km)} km apart). Pick which one is right:</strong>
        ${renderOption("zip_based", "Use the ZIP's location", conflict.zip_based)}
        ${renderOption("coordinate_based", "Use the coordinates' location", conflict.coordinate_based)}`;
      formEl.insertBefore(box, formEl.firstChild);

      box.querySelectorAll("[data-hierarchy-option]").forEach((button) => {
        button.addEventListener("click", () => {
          const option = conflict[button.dataset.hierarchyOption];
          if (!option) return;
          suggestionAdopted = true;
          const setField = (type, value) => {
            const input = formEl.querySelector(`[data-field-type='${type}']`);
            if (input && value !== null && value !== undefined) input.value = value;
          };
          setField("city", option.city);
          setField("state", option.state);
          setField("country", option.country);
          setField("postal_code", option.zip_code);
          setField("latitude", option.latitude);
          setField("longitude", option.longitude);
          box.remove();
        });
      });
    }

async function openEditRecordModal(record) {
      suggestionAdopted = false;
      currentEditingRecord = record;
      let rawObj = record.raw_record;
      if (typeof rawObj === 'string') {
        try { rawObj = JSON.parse(rawObj); } catch (e) { rawObj = {}; }
      }
      let errs = record.errors;
      if (typeof errs === 'string') {
        try { errs = JSON.parse(errs); } catch (e) { errs = []; }
      }

      const hintsEl = el("editRecordHints");
      hintsEl.innerHTML = `<strong>Flagged Issues for Row #${record.row_number}:</strong><ul style="margin: 6px 0 0 18px; padding: 0;">` +
        (Array.isArray(errs) ? errs.map(e => `<li><strong>${escapeHtml(e.field)}</strong>: ${escapeHtml(e.hint || e.reason)}</li>`).join('') : '<li>Issue found.</li>') +
        `</ul>`;

      // Fetch saved brands directly from DB API if not already cached
      let savedBrandsList = [];
      try {
        savedBrandsList = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      } catch (e) {
        savedBrandsList = [];
      }
      if (!savedBrandsList.length) {
        try {
          const res = await fetch("/api/brands?search=");
          const data = await res.json();
          if (res.ok && Array.isArray(data.brands)) {
            savedBrandsList = data.brands;
            if (el("brandSelect")) el("brandSelect").dataset.brands = JSON.stringify(savedBrandsList);
          }
        } catch (err) {
          // fallback to empty
        }
      }

      // Use this record's OWN saved template mapping, not whatever happens
      // to be loaded in the Mapper tab's live UI state right now
      // (getMapper()) - those can easily disagree (a different brand open,
      // or nothing parsed this session at all), which is why fields the
      // error text names (e.g. "Seating Capacity") often never showed up
      // as an editable box: getMapper().fields was empty/unrelated, so
      // that field fell through to the raw-key fallback loop below under
      // its raw source column name instead of a recognizable label.
      let mapperFields = {};
      try {
        // template_id is frequently null (only set when a save explicitly
        // created/updated a template) - business_id is the reliable key,
        // so look up by that and only use template_id to pick the exact
        // match out of several candidates when both are present.
        // list_templates() already orders by updated_at DESC, so the first
        // result is the most recent one for this business - a reasonable
        // default when there's no exact template_id to match.
        if (record.business_id) {
          let templates = reviewTemplateCache.get(record.business_id);
          if (!templates) {
            const templatesRes = await fetch(`/api/templates?business_id=${encodeURIComponent(record.business_id)}`);
            const templatesData = await templatesRes.json();
            templates = Array.isArray(templatesData.templates) ? templatesData.templates : [];
            reviewTemplateCache.set(record.business_id, templates);
          }
          const matched = (record.template_id && templates.find((t) => t.workflow_template_id === record.template_id)) || templates[0];
          const components = matched?.components?.mapper || matched?.components || {};
          if (components && typeof components.fields === "object" && !Array.isArray(components.fields)) {
            mapperFields = components.fields;
          }
        }
      } catch (_) {}
      if (!Object.keys(mapperFields).length) {
        const activeMapper = typeof getMapper === "function" ? getMapper() : { fields: {} };
        mapperFields = activeMapper.fields || {};
      }
      // Raw source column -> target field key, so a raw JSON key that IS
      // part of this brand's real mapping (e.g. "seats" mapped to
      // seating_capacity) renders under its human field label instead of
      // its raw source name - matching what the flagged error actually calls it.
      const sourceKeyToTargetKey = {};
      Object.entries(mapperFields).forEach(([targetKey, sourcePath]) => {
        if (sourcePath) sourceKeyToTargetKey[sourcePath] = targetKey;
      });

      // Match similar brand from existing data:
      // Check record.business_id, rawObj business_id/brand, active mapper brand, or name matching
      // String() on an object yields "[object Object]", which formatBrandName
      // then title-cased into "Object Object" - shown to the user in place of
      // a real brand like "Casa Verde". The raw record's brand can legitimately
      // be a nested object (e.g. {name: "..."}), so unwrap it before
      // stringifying and fall back to the resolved brand rather than printing
      // the placeholder.
      const brandCandidate = getNestedRawValue(rawObj, mapperFields.brand || "brand");
      const unwrapBrand = (value) => {
        if (value === null || value === undefined) return "";
        if (typeof value === "object") {
          // Common shapes: {name}, {value}, {brand}, or a single-entry object.
          const nested = value.name ?? value.value ?? value.brand ?? value.label;
          if (nested !== undefined && typeof nested !== "object") return String(nested);
          const first = Object.values(value).find((v) => v !== null && typeof v !== "object");
          return first === undefined ? "" : String(first);
        }
        return String(value);
      };
      const rawBrandVal = (unwrapBrand(brandCandidate) || String(record.brand ?? activeMapper.brand ?? "")).trim();
      const rawNameVal = String(getNestedRawValue(rawObj, mapperFields.name || "name") || "").trim();
      const targetBusinessId = String(record.business_id || activeMapper.business_id || "").trim();

      let matchedBrand = savedBrandsList.find(b => targetBusinessId && b.business_id === targetBusinessId);
      if (!matchedBrand && rawBrandVal) {
        matchedBrand = savedBrandsList.find(b => b.name && b.name.toLowerCase() === rawBrandVal.toLowerCase());
      }
      if (!matchedBrand && rawNameVal) {
        matchedBrand = savedBrandsList.find(b => b.name && (rawNameVal.toLowerCase().includes(b.name.toLowerCase()) || b.name.toLowerCase().includes(rawNameVal.toLowerCase())));
      }

      const LOCATION_FIELD_SPECS = {
        brand: { label: "Brand Name", path: mapperFields.brand || "brand", note: "Select the brand to associate with this record.", required: true },
        name: { label: "Location Name", path: mapperFields.name || "name", note: "Required.", required: true },
        address: { label: "Address", path: mapperFields.address || "address", note: "Required.", required: true },
        city: { label: "City", path: mapperFields.city || "city", note: "Required.", required: true },
        state: { label: "State", path: mapperFields.state || "state", note: "Required (2-letter code or state name).", required: true },
        postal_code: { label: "ZIP Code", path: mapperFields.postal_code || "postal_code", note: "Required (5-digit US ZIP code).", required: true },
        country: { label: "Country", path: mapperFields.country || "country", note: "Optional. Validation can infer it when enough location data is available.", required: false },
        latitude: { label: "Latitude", path: mapperFields.latitude || "latitude", note: `Decimal latitude coordinate (e.g. ${(Math.random() * 180 - 90).toFixed(4)}).`, required: false },
        longitude: { label: "Longitude", path: mapperFields.longitude || "longitude", note: `Decimal longitude coordinate (e.g. ${(Math.random() * 360 - 180).toFixed(4)}).`, required: false },
      };
      const renderedPaths = new Set();

      const requiredFieldHtml = ["brand", "name", "address", "city", "state", "postal_code", "latitude", "longitude", "country"]
        .map((key) => {
          const { label, path, note, required } = LOCATION_FIELD_SPECS[key];
          renderedPaths.add(path);
          if (key === "brand") {
            // A record's brand is fixed by its event_id -> business_id
            // relation (see reprocess_rejected(), which now always
            // re-resolves brand from business_id server-side regardless of
            // what's submitted) - so once this record already belongs to a
            // known business, brand can't be changed here. Re-mapping a
            // record to a different brand means moving it to a different
            // business_id, which this dialog doesn't do.
            const brandLocked = Boolean(targetBusinessId);
            if (brandLocked) {
              const lockedLabel = formatBrandName(matchedBrand ? matchedBrand.name : rawBrandVal);
              return `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: var(--muted);">(${escapeHtml(path)})</span></label>
          <select id="editRecordBrandSelect" data-raw-key="${escapeHtml(path)}" data-field-type="brand" disabled style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px; background: #f4f6f8; color: var(--muted);">
            <option value="${escapeHtml(matchedBrand ? matchedBrand.name : rawBrandVal)}" selected>${escapeHtml(lockedLabel || 'Unknown brand')}</option>
          </select>
          <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">Brand is fixed by this record's business and can't be changed here.</span>
        </div>
      `;
            }
            const optionsHtml = ['<option value="">Select a saved brand</option>']
              .concat(savedBrandsList.map(b => {
                const isSelected = matchedBrand ? b.business_id === matchedBrand.business_id : (b.name.toLowerCase() === rawBrandVal.toLowerCase());
                return `<option value="${escapeHtml(b.name)}" data-business-id="${escapeHtml(b.business_id)}" ${isSelected ? 'selected' : ''}>${escapeHtml(formatBrandName(b.name))}</option>`;
              }))
              .join('');
            return `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: ${required ? '#cf1322' : 'var(--muted)'};">(${escapeHtml(path)})${required ? ' *' : ''}</span></label>
          <select id="editRecordBrandSelect" data-raw-key="${escapeHtml(path)}" data-field-type="brand" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px; background: #fff;">
            ${optionsHtml}
          </select>
          <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">${escapeHtml(note)}</span>
        </div>
      `;
          }
          const rawVal = getNestedRawValue(rawObj, path);
          return `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: ${required ? '#cf1322' : 'var(--muted)'};">(${escapeHtml(path)})${required ? ' *' : ''}</span></label>
          <input type="text" data-raw-key="${escapeHtml(path)}" data-field-type="${escapeHtml(key)}" value="${escapeHtml(rawVal !== null && rawVal !== undefined ? String(rawVal) : '')}" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px;">
          <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">${escapeHtml(note)}</span>
        </div>
      `;
        }).join('');

      const formEl = el("editRecordForm");
      formEl.innerHTML = requiredFieldHtml + Object.entries(rawObj).filter(([key]) => {
        if (renderedPaths.has(key)) return false;
        const isLat = key.toLowerCase().includes("lat");
        const isLon = key.toLowerCase().includes("lon") || key.toLowerCase().includes("lng");
        const isZip = key.toLowerCase().includes("zip") || key.toLowerCase().includes("postal");
        if ((isLat && renderedPaths.has("latitude")) || (isLon && renderedPaths.has("longitude")) || (isZip && renderedPaths.has("postal_code"))) return false;
        return true;
      }).sort(([keyA], [keyB]) => {
        // Flagged (the field the error text names) first, then anything
        // else that's part of this brand's real mapping, then the rest -
        // so the box the user actually needs isn't buried in raw JSON key order.
        const rank = (key) => {
          const targetKey = sourceKeyToTargetKey[key];
          if (targetKey && Array.isArray(errs) && errs.some((e) => e.field === targetKey)) return 0;
          if (targetKey) return 1;
          return 2;
        };
        return rank(keyA) - rank(keyB);
      }).map(([key, val]) => {
        const isLat = key.toLowerCase().includes("lat");
        const isLon = key.toLowerCase().includes("lon") || key.toLowerCase().includes("lng");
        const isZip = key.toLowerCase().includes("zip") || key.toLowerCase().includes("postal");
        const fieldType = isLat ? "latitude" : (isLon ? "longitude" : (isZip ? "postal_code" : ""));
        // A raw column that IS part of this brand's real mapping shows
        // under its human field label (matching what the flagged error
        // calls it) instead of its raw source name, and is flagged if it's
        // the actual field the error text named.
        const mappedTargetKey = sourceKeyToTargetKey[key];
        const displayLabel = mappedTargetKey && typeof formatFieldLabel === "function" ? formatFieldLabel(mappedTargetKey) : key;
        const isFlagged = mappedTargetKey && Array.isArray(errs) && errs.some((e) => e.field === mappedTargetKey);
        return `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: ${isFlagged ? '#cf1322' : 'var(--ink)'}; margin-bottom: 4px;">${isFlagged ? '⚠️ ' : ''}${escapeHtml(displayLabel)} <span style="font-weight: 400; color: var(--muted); font-size: 11px;">(${escapeHtml(key)})</span></label>
          <input type="text" data-raw-key="${escapeHtml(key)}" data-field-type="${escapeHtml(fieldType)}" value="${escapeHtml(val !== null && val !== undefined ? String(val) : '')}" style="padding: 6px; border: 1px solid ${isFlagged ? '#ffa39e' : 'var(--line)'}; border-radius: 4px; font-size: 13px;">
        </div>
      `;
      }).join('');

      const feedbackEl = el("editRecordFeedback");
      if (feedbackEl) {
        feedbackEl.style.display = "none";
        feedbackEl.textContent = "";
        feedbackEl.className = "action-feedback";
      }

      // City/State level ZIP & lat/long suggestion helper. Coordinates come
      // straight from us_zipcodes.latitude/longitude - real ZIP-centroid
      // reference data already stored for every ZIP, not fabricated - so a
      // suggestion is an honest "somewhere in this ZIP", not an exact
      // address-level fix.
      const cityVal = String(getNestedRawValue(rawObj, mapperFields.city || "city") || rawObj.city || rawObj.City || "").trim();
      const stateVal = String(getNestedRawValue(rawObj, mapperFields.state || "state") || rawObj.state || rawObj.State || "").trim();
      const zipVal = String(getNestedRawValue(rawObj, mapperFields.postal_code || "postal_code") || rawObj.zip || rawObj.postal_code || "").trim();
      const latVal = String(getNestedRawValue(rawObj, mapperFields.latitude || "latitude") || rawObj.latitude || "").trim();
      const lonVal = String(getNestedRawValue(rawObj, mapperFields.longitude || "longitude") || rawObj.longitude || "").trim();
      const needsZip = !zipVal || zipVal.length < 5;
      const needsLatLon = !latVal || !lonVal || isNaN(parseFloat(latVal)) || isNaN(parseFloat(lonVal));

      if (cityVal && (needsZip || needsLatLon)) {
        try {
          fetch(`/api/zips/search?q=${encodeURIComponent(cityVal)}&state=${encodeURIComponent(stateVal)}&limit=5`)
            .then(res => res.json())
            .then(data => {
              if (data && Array.isArray(data.zips) && data.zips.length > 0) {
                // A city can legitimately have several ZIPs, but showing
                // multiple near-identical "(city, state)" buttons that only
                // differ by ZIP reads as duplicated noise - the (city, state)
                // combination is what the user is actually choosing between,
                // so keep only the first (best-ranked) ZIP per combination.
                const seenCityState = new Set();
                data.zips = data.zips.filter((z) => {
                  const key = `${(z.city_name || "").toLowerCase()}|${(z.state_code || "").toLowerCase()}`;
                  if (seenCityState.has(key)) return false;
                  seenCityState.add(key);
                  return true;
                });
                const suggestionBox = document.createElement("div");
                suggestionBox.id = "zipSuggestionsBox";
                suggestionBox.style.gridColumn = "1 / -1";
                suggestionBox.style.background = "#e6f7ff";
                suggestionBox.style.border = "1px solid #91d5ff";
                suggestionBox.style.borderRadius = "6px";
                suggestionBox.style.padding = "8px 12px";
                suggestionBox.style.fontSize = "12px";
                suggestionBox.style.color = "#0050b3";
                suggestionBox.style.marginBottom = "8px";

                const zipsListHtml = data.zips.slice(0, 4).map(z => `
                  <button type="button" class="secondary" style="padding: 2px 8px; font-size: 11px; margin: 2px 4px 2px 0; border: 1px solid #91d5ff; background: #fff; cursor: pointer;"
                    onclick="(function(){
                      suggestionAdopted = true;
                      const zipInput = document.querySelector('input[data-field-type=\\'postal_code\\']');
                      if (zipInput) zipInput.value = '${escapeHtml(z.zip_code)}';
                      const cityInput = document.querySelector('input[data-field-type=\\'city\\']');
                      if (cityInput && !cityInput.value) cityInput.value = '${escapeHtml(z.city_name || '')}';
                      const stateInput = document.querySelector('input[data-field-type=\\'state\\']');
                      if (stateInput && !stateInput.value) stateInput.value = '${escapeHtml(z.state_code || '')}';
                      const latInput = document.querySelector('input[data-field-type=\\'latitude\\']');
                      if (latInput && ${z.latitude !== null && z.latitude !== undefined}) latInput.value = '${z.latitude ?? ''}';
                      const lonInput = document.querySelector('input[data-field-type=\\'longitude\\']');
                      if (lonInput && ${z.longitude !== null && z.longitude !== undefined}) lonInput.value = '${z.longitude ?? ''}';
                    })()">📍 ${escapeHtml(z.zip_code)} (${escapeHtml(z.city_name || cityVal)}, ${escapeHtml(z.state_code || stateVal)})</button>
                `).join('');

                suggestionBox.innerHTML = `<strong>💡 Suggested ZIP + coordinates for ${escapeHtml(cityVal)}:</strong> <div style="margin-top: 4px;">${zipsListHtml}</div><div style="margin-top: 4px; font-size: 11px; color: #0050b3;">Coordinates are that ZIP's approximate center, not an exact address - fine for a nearby fix, not a precise pin.</div>`;
                formEl.insertBefore(suggestionBox, formEl.firstChild);
              }
            })
            .catch(() => {});
        } catch (e) {}
      }

      el("editRecordForm").querySelectorAll("input, select").forEach(input => {
        input.addEventListener("input", () => {
          if (feedbackEl && feedbackEl.className.includes("error")) {
            feedbackEl.style.display = "none";
            feedbackEl.textContent = "";
          }
        });
        input.addEventListener("change", () => {
          if (feedbackEl && feedbackEl.className.includes("error")) {
            feedbackEl.style.display = "none";
            feedbackEl.textContent = "";
          }
        });
      });

      el("editRecordForm").scrollTop = 0;
      el("editRecordDialog").showModal();
    }
el("closeEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("cancelEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("submitEditRecordBtn")?.addEventListener("click", async () => {
      if (!currentEditingRecord) return;
      const feedbackEl = el("editRecordFeedback");
      const showDialogError = (msg) => {
        if (feedbackEl) {
          feedbackEl.className = "action-feedback error";
          feedbackEl.style.color = "#cf1322";
          feedbackEl.style.background = "#fff1f0";
          feedbackEl.style.border = "1px solid #ffa39e";
          feedbackEl.style.borderRadius = "4px";
          feedbackEl.style.padding = "8px 12px";
          feedbackEl.textContent = msg;
          feedbackEl.style.display = "block";
        } else {
          showAppNotice(msg, "Review record");
        }
      };

      const inputs = el("editRecordForm").querySelectorAll("input[data-raw-key], select[data-raw-key]");
      const updatedRaw = {};
      const validationErrors = [];
      let selectedBusinessId = "";
      let selectedBrandName = "";

      inputs.forEach(input => {
        const val = input.value.trim();
        const rawKey = input.dataset.rawKey;
        const fieldType = input.dataset.fieldType || "";
        updatedRaw[rawKey] = input.value;

        if (fieldType === "brand") {
          selectedBrandName = val;
          if (input.tagName === "SELECT") {
            const opt = input.selectedOptions[0];
            selectedBusinessId = opt?.dataset.businessId || "";
          }
        }

        // Field specific data validation
        if (fieldType === "latitude" && val) {
          const num = parseFloat(val);
          if (isNaN(num)) {
            validationErrors.push(`Latitude '${val}' for '${rawKey}' must be a valid decimal number.`);
          } else if (num < 13.0 || num > 72.0) {
            validationErrors.push(`Latitude ${num} is outside standard US territory boundaries (13.0 to 72.0). Please correct coordinate.`);
          }
        } else if (fieldType === "longitude" && val) {
          const num = parseFloat(val);
          if (isNaN(num)) {
            validationErrors.push(`Longitude '${val}' for '${rawKey}' must be a valid decimal number.`);
          } else if (!((num >= -180.0 && num <= -64.0) || (num >= 144.0 && num <= 146.0))) {
            validationErrors.push(`Longitude ${num} is outside standard US territory boundaries (-180.0 to -64.0). Please correct coordinate.`);
          }
        } else if (fieldType === "postal_code" && val) {
          const digits = val.replace(/\D/g, "");
          if (digits.length < 5) {
            validationErrors.push(`ZIP Code '${val}' for '${rawKey}' must contain at least 5 digits.`);
          }
        }
      });

      if (validationErrors.length > 0) {
        showDialogError(validationErrors[0]);
        return;
      }

      if (feedbackEl) feedbackEl.style.display = "none";

      const activeMapper = typeof getMapper === "function" ? getMapper() : {};
      const finalBrandName = selectedBrandName || activeMapper.brand || currentEditingRecord.brand || "";
      const finalBusinessId = selectedBusinessId || currentEditingRecord.business_id || activeMapper.business_id || "";

      const retryMapper = {
        ...activeMapper,
        business_id: finalBusinessId,
        source_type_id: currentEditingRecord.source_type_id || activeMapper.source_type_id || "",
        brand: finalBrandName,
        source_name: activeMapper.source_name || "error_listings_review",
        source_type: activeMapper.source_type || "csv",
        fields: activeMapper.fields && typeof activeMapper.fields === "object" && !Array.isArray(activeMapper.fields) && Object.keys(activeMapper.fields).length ? activeMapper.fields : {
          name: "name",
          address: "address",
          city: "city",
          state: "state",
          postal_code: "postal_code",
          country: "country",
          latitude: "latitude",
          longitude: "longitude"
        }
      };

      const showDialogSuccess = (msg) => {
        if (feedbackEl) {
          feedbackEl.className = "action-feedback ok";
          feedbackEl.style.color = "#389e0d";
          feedbackEl.style.background = "#f6ffed";
          feedbackEl.style.border = "1px solid #b7eb8f";
          feedbackEl.style.borderRadius = "4px";
          feedbackEl.style.padding = "8px 12px";
          feedbackEl.textContent = msg;
          feedbackEl.style.display = "block";
        }
      };

      const submitBtn = el("submitEditRecordBtn");
      const cancelBtn = el("cancelEditRecordBtn");
      const originalBtnHtml = submitBtn ? submitBtn.innerHTML : "Retry Record";

      try {
        if (submitBtn) setButtonBusy(submitBtn, "Retrying");
        if (cancelBtn) cancelBtn.disabled = true;

        const response = await fetch("/api/reprocess", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            event_id: currentEditingRecord.event_id,
            row_numbers: [currentEditingRecord.row_number],
            mapper: retryMapper,
            rows: [updatedRaw],
            // Set only by "Save anyway, review later": keeps the user's edit
            // and defers re-validation to enrichment instead of bouncing it
            // back for a value the system cannot confirm right now.
            accept_as_reviewed: window.__acceptAsReviewed === true,
            // An adopted system suggestion counts as an automatic fix (AI
            // Fixed), not a manual one, even though a person clicked
            // Retry - reprocess_rejected() branches its fix-count
            // attribution on this same flag it already uses for the
            // background auto-repair worker.
            is_ai_enriched: suggestionAdopted
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not reprocess record.");

        if (result.mapped_rows > 0) {
          const cleanup = result.error_listings_cleanup;
          if (cleanup && cleanup.attempted && !cleanup.ok) {
            // The row is safely in listings, but the old error entry didn't
            // get cleared - say so plainly instead of a blanket "success"
            // that would leave the count silently stuck.
            showDialogError(`Record moved to listings, but the old error entry could not be cleared (still counted in Review Error Listings). ${cleanup.error ? escapeHtml(cleanup.error) : "Please retry or check server logs."}`);
          } else {
            showDialogSuccess(`✅ Record #${currentEditingRecord.row_number} successfully validated & moved from error listings to listings.`);
            setTimeout(() => {
              el("editRecordDialog").close();
            }, 1200);
          }
          await loadRejectedRecords();
          // reprocess already re-counted from BigQuery and wrote it back to
          // SQLite; use the returned total directly for an instant, correct
          // badge, falling back to a forced refresh if it wasn't returned.
          if (typeof result.error_count_total === "number") {
            el("reviewCount").textContent = result.error_count_total;
          } else {
            await refreshReviewCount(true);
          }
          await loadErrorBrandBreakdown();
          setStatus(`Record #${currentEditingRecord.row_number} reprocessed successfully and moved to listings.`, "ok");
          if (typeof loadJobHistory === "function") loadJobHistory();
        } else {
          // Still invalid: the queue didn't shrink, but a fresh error row may
          // have replaced the old one - re-count from source and refresh the
          // brand breakdown so both stay truthful.
          if (typeof result.error_count_total === "number") {
            el("reviewCount").textContent = result.error_count_total;
          } else {
            await refreshReviewCount(true);
          }
          await loadErrorBrandBreakdown();
          const attemptCount = Number(result.attempt_count || 0);
          const suggestion = result.suggested_fix && typeof result.suggested_fix === "object" ? result.suggested_fix : null;
          const suggestionText = suggestion && Object.keys(suggestion).length
            ? ` The enricher suggests: ${Object.entries(suggestion).map(([field, value]) => `${escapeHtml(field)} = "${escapeHtml(value)}"`).join(", ")}.`
            : "";
          // Name the fields that actually failed. The old blanket "check
          // required fields, ZIP Code, and coordinates" made the user re-read
          // every input looking for the one that mattered.
          const failed = Array.isArray(result.failed_fields) ? result.failed_fields : [];
          const failedText = failed.length
            ? `${failed.length === 1 ? "This field still" : "These fields still"} need${failed.length === 1 ? "s" : ""} attention: ${failed.map((f) => escapeHtml(formatFieldLabel(f) || f)).join(", ")}.`
            : "This record still doesn't validate. Please check the highlighted fields.";
          showDialogError(`Review Again (attempt ${attemptCount || 1}): ${failedText}${suggestionText}`);
          // Offer the escape hatch only once a retry has actually failed -
          // showing it up front would invite skipping validation that would
          // have passed.
          const acceptBtn = el("acceptAsReviewedBtn");
          if (acceptBtn) acceptBtn.classList.remove("hidden");
          if (result.hierarchy_conflict) renderHierarchyConflictPicker(result.hierarchy_conflict);
          if (result.non_us_suggestion) renderNonUsSuggestion(result.non_us_suggestion);
        }
      } catch (error) {
        showDialogError(productSafeError(error.message, "Could not reprocess this record."));
      } finally {
        if (submitBtn) {
          clearButtonBusy(submitBtn, originalBtnHtml);
        }
        if (cancelBtn) cancelBtn.disabled = false;
      }
    });
// The tab badge shows the overall Review Error Listings total (all
// businesses), not a per-brand slice - the per-brand split lives in the
// brand-impact breakdown inside the tab. `refresh` forces a live BigQuery
// re-count (and rewrites the SQLite cache); leave it false for cheap lazy
// reads (tab open, app boot) that just want the last-known number instantly.
async function refreshReviewCount(refresh = false) {
      try {
        const response = await fetch(`/api/error-listings/count?business_id=&refresh=${refresh ? "1" : "0"}`);
        const result = await response.json();
        if (response.ok && typeof result.count === "number") {
          const count = result.count;
          if (el("reviewCount")) el("reviewCount").textContent = count;
          localStorage.setItem("review_error_count_last", String(count));
        }
      } catch (error) {
        // Keep whatever the badge already showed rather than blanking to 0 -
        // a transient fetch failure shouldn't wipe a valid cached count.
      }
    }

// Accessible, distinct categorical hues for the brand-impact donut. Reused
// slice-to-slice so the table swatch and the arc always agree.
const ERROR_BRAND_COLORS = ["#2f6f6a", "#c26a3d", "#4c6ef5", "#b5559e", "#3c9a5f", "#c0392b", "#8a6d3b", "#6741d9", "#128fb0", "#9c6b1f"];

function _donutSvg(slices, total, size = 320) {
      // slices: [{value, color, label}]. Renders an SVG donut; a single 100% slice
      // is drawn as a full ring (an arc path can't express a 360 deg sweep).
      const radius = size / 2;
      const inner = radius * 0.58;
      const cx = radius;
      const cy = radius;
      if (!total) return "";
      const nonZero = slices.filter((s) => s.value > 0);
      if (nonZero.length === 1) {
        const pct = Math.round(nonZero[0].value / total * 100);
        return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="One brand accounts for all error listings">
          <circle class="review-chart-slice" data-brand="${escapeHtml(nonZero[0].label || 'Brand')}" data-count="${nonZero[0].value}" data-share="${pct}%" cx="${cx}" cy="${cy}" r="${(radius + inner) / 2}" fill="none" stroke="${nonZero[0].color}" stroke-width="${radius - inner}">
            <title>${escapeHtml(nonZero[0].label || 'Brand')}\n${nonZero[0].value} records\n${pct}% of errors</title>
          </circle>
          <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="22" font-weight="700" fill="#1f2937">${total}</text>
          <text x="${cx}" y="${cy + 17}" text-anchor="middle" font-size="11" fill="#6b7280">error listings</text>
        </svg>`;
      }
      let angle = -Math.PI / 2;
      const arcs = slices.map((slice) => {
        if (slice.value <= 0) return "";
        const sweep = (slice.value / total) * Math.PI * 2;
        const a0 = angle;
        const a1 = angle + sweep;
        angle = a1;
        const large = sweep > Math.PI ? 1 : 0;
        const x0 = cx + radius * Math.cos(a0), y0 = cy + radius * Math.sin(a0);
        const x1 = cx + radius * Math.cos(a1), y1 = cy + radius * Math.sin(a1);
        const xi1 = cx + inner * Math.cos(a1), yi1 = cy + inner * Math.sin(a1);
        const xi0 = cx + inner * Math.cos(a0), yi0 = cy + inner * Math.sin(a0);
        const pct = Math.round(slice.value / total * 100);
        return `<path class="review-chart-slice" data-brand="${escapeHtml(slice.label || 'Brand')}" data-count="${slice.value}" data-share="${pct}%" d="M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} L ${xi1.toFixed(2)} ${yi1.toFixed(2)} A ${inner} ${inner} 0 ${large} 0 ${xi0.toFixed(2)} ${yi0.toFixed(2)} Z" fill="${slice.color}"><title>${escapeHtml(slice.label || 'Brand')}\n${slice.value} records\n${pct}% of errors</title></path>`;
      }).join("");
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Error listings by brand">
        ${arcs}
        <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="22" font-weight="700" fill="#1f2937">${total}</text>
        <text x="${cx}" y="${cy + 17}" text-anchor="middle" font-size="11" fill="#6b7280">error listings</text>
      </svg>`;
    }

function attachDonutTooltips() {
      const chart = el("reviewBrandChart");
      if (!chart) return;
      chart.querySelector(".review-chart-tooltip")?.remove();
      const tooltip = document.createElement("div");
      tooltip.className = "review-chart-tooltip";
      chart.appendChild(tooltip);
      chart.querySelectorAll(".review-chart-slice").forEach((slice) => {
        const show = (event) => {
          tooltip.innerHTML = `<strong>${escapeHtml(slice.dataset.brand || "Brand")}</strong><br>${escapeHtml(slice.dataset.count || "0")} errors (${escapeHtml(slice.dataset.share || "0%")})`;
          tooltip.style.display = "block";
          const bounds = chart.getBoundingClientRect();
          tooltip.style.left = `${Math.max(4, Math.min(event.clientX - bounds.left + 12, chart.clientWidth - tooltip.offsetWidth - 4))}px`;
          tooltip.style.top = `${Math.max(4, event.clientY - bounds.top - tooltip.offsetHeight - 10)}px`;
        };
        slice.addEventListener("mouseenter", show);
        slice.addEventListener("mousemove", show);
        slice.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
      });
    }

async function loadErrorBrandBreakdown() {
      const container = el("reviewBrandBreakdown");
      if (!container) return;
      try {
        const response = await fetch("/api/error-listings/by-brand");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load brand breakdown.");
        const brands = Array.isArray(result.brands) ? result.brands.filter((b) => b.count > 0) : [];
        const total = result.total || brands.reduce((sum, b) => sum + b.count, 0);
        if (!brands.length) {
          container.style.display = "none";
          return;
        }
        const withColor = brands.map((b, i) => ({ ...b, color: ERROR_BRAND_COLORS[i % ERROR_BRAND_COLORS.length] }));
        el("reviewBrandChart").innerHTML = _donutSvg(withColor.map((b) => ({ value: b.count, color: b.color, label: b.brand || b.business_id })), total);
        attachDonutTooltips();
        el("reviewBrandBreakdownTotal").textContent = `${total} across ${brands.length} brand${brands.length === 1 ? "" : "s"}`;
        el("reviewBrandTable").innerHTML = `<table style="width:100%; border-collapse: collapse; font-size: 12px;"><thead><tr>
            <th data-sort-key="brand" style="text-align:left; padding:4px 8px; border-bottom:1px solid var(--line);">Brand</th>
            <th data-sort-key="errors" data-sort-type="number" style="text-align:right; padding:4px 8px; border-bottom:1px solid var(--line);">Errors</th>
            <th data-sort-key="share" data-sort-type="number" style="text-align:right; padding:4px 8px; border-bottom:1px solid var(--line);">Share</th>
          </tr></thead><tbody>${withColor.map((b) => `<tr>
            <td data-sort-value="${escapeHtml(formatBrandName(b.brand || b.business_id))}" style="padding:4px 8px;"><span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:${b.color}; margin-right:6px; vertical-align:middle;"></span>${escapeHtml(formatBrandName(b.brand || b.business_id))}</td>
            <td data-sort-value="${b.count}" style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">${b.count}</td>
            <td data-sort-value="${total ? (b.count / total * 100) : 0}" style="padding:4px 8px; text-align:right; color: var(--muted); font-variant-numeric: tabular-nums;">${total ? (b.count / total * 100).toFixed(2) : "0.00"}%</td>
          </tr>`).join("")}</tbody></table>`;
        enableSortableTable(el("reviewBrandTable").querySelector("table"));
        container.style.display = "block";
      } catch (error) {
        container.style.display = "none";
      }
    }


// "Save anyway, review later": keeps the user's edit as user_reviewed and
// hands re-validation to enrichment. Reuses the normal submit path so the
// two can never diverge - the only difference is the accept_as_reviewed flag.
el("acceptAsReviewedBtn")?.addEventListener("click", async () => {
  window.__acceptAsReviewed = true;
  try {
    el("submitEditRecordBtn")?.click();
  } finally {
    // Cleared immediately: the flag must never leak into the next retry.
    window.__acceptAsReviewed = false;
  }
});
