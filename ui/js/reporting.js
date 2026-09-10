// Reporting tab: filters, KPI/table rendering, and the Leaflet location map.

let reportLoaded = false;
// Whether the report has EVER been painted. reportLoaded is reset on purpose
// to force a re-fetch (auto-refresh, manual refresh, filter change), so it
// cannot also decide whether to blank the screen - keying the blank off it
// meant every refresh wiped the numbers to 0 and left a screen of empty
// space behind the status line. This one is set once and never reset.
let reportHasRenderedOnce = false;
let reportingBrands = [];
let enrichmentStatusTimer = null;
let reportingCountdownTimer = null;
let reportingCountdownSeconds = 300;
let reportingWarmupTimer = null;
// The Location Intelligence filter rail's auto-apply switch, created by
// setupReportAutoApply(). Module level because the geographic filters keep
// their own change handlers in integrations.html (they also have to refresh
// the dependent dropdowns) and hand only the reload itself to the toggle.
let reportAutoApply = null;

const canonicalBrandMap = new Map();
const canonicalToRawMap = new Map();

function getCanonicalBrandName(name) {
  if (!name) return "";
  let clean = String(name).trim();
  clean = clean.replace(/,\s*/g, " ").replace(/\s+/g, " ").trim();
  return clean;
}

function registerBrandMappings(rawBrands = []) {
  canonicalBrandMap.clear();
  canonicalToRawMap.clear();
  const uniqueCanonical = [];
  const seenKeys = new Map();

  rawBrands.forEach((raw) => {
    if (!raw) return;
    const trimmed = String(raw).trim();
    if (!trimmed) return;
    const canonical = getCanonicalBrandName(trimmed);
    const key = canonical.toLowerCase().replace(/[^a-z0-9]/g, "");

    let chosenCanonical = canonical;
    if (seenKeys.has(key)) {
      chosenCanonical = seenKeys.get(key);
    } else {
      seenKeys.set(key, canonical);
      uniqueCanonical.push(canonical);
    }

    canonicalBrandMap.set(raw, chosenCanonical);
    canonicalBrandMap.set(trimmed, chosenCanonical);
    if (!canonicalToRawMap.has(chosenCanonical)) {
      canonicalToRawMap.set(chosenCanonical, new Set());
    }
    canonicalToRawMap.get(chosenCanonical).add(raw);
    canonicalToRawMap.get(chosenCanonical).add(trimmed);
  });

  uniqueCanonical.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  return uniqueCanonical;
}

function getRawVariantsForBrand(brand) {
  if (!brand) return [];
  if (canonicalToRawMap.has(brand)) {
    return Array.from(canonicalToRawMap.get(brand));
  }
  return [brand];
}

function resolveCanonicalBrand(brand) {
  if (!brand) return "";
  return formatBrandName(canonicalBrandMap.get(brand) || getCanonicalBrandName(brand));
}

function formatBrandList(value) {
  return String(value || "")
    .split(/[~,]/)
    .map((brand) => formatBrandName(brand))
    .filter(Boolean)
    .join(" ~ ");
}

function renderEmptyReportingStructure() {
      el("reportContent").classList.remove("hidden");
      ["reportLocations", "reportBrands", "reportStates", "reportCities", "reportZips", "reportStores", "reportBrandStates", "reportWhitespaceGaps"].forEach((id) => {
        if (el(id)) el(id).textContent = "0";
      });
      renderReportingMap([], [], []);
      if (el("reportCompetitorBenchmarkContent")) {
        el("reportCompetitorBenchmarkContent").innerHTML = `
          <div style="color: var(--muted); font-size: 13px; padding: 24px; text-align: center; background: #f8fafc; border: 1px solid var(--line); border-radius: 8px;">
            Loading competitor benchmark view
          </div>
        `;
      }
      if (el("reportTopStateCards")) {
        el("reportTopStateCards").innerHTML = [1, 2, 3].map(() => `
          <div style="border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 14px; text-align: center;">
            <h3 style="margin: 0 0 4px; font-size: 18px; color: var(--ink);">State</h3>
            <div style="font-size: 26px; font-weight: 700; color: var(--accent);">0 <span style="font-size: 13px; color: var(--muted); font-weight: 500;">(0.0%)</span></div>
            <p style="margin: 8px 0 0; font-size: 12px; color: var(--muted); line-height: 1.4;">Pop. per listing: <strong>0</strong>. Population: 0</p>
          </div>
        `).join("");
      }
      renderSimpleTable("reportTopStates", [
        { key: "state_name", label: "State / Territory" },
        { key: "locations", label: "Listings", format: formatNumber },
        { key: "pct", label: "Listing Share" },
        { key: "state_population", label: "State Population", format: formatNumber },
        { key: "pop_per_store", label: "Population Per Listing", format: formatNumber },
        { key: "median_household_income", label: "Median Income", format: formatNumber },
        { key: "cities", label: "Cities Covered", format: formatNumber }
      ], []);
      renderSimpleTable("reportTopCities", [
        { key: "city", label: "City" },
        { key: "state_name", label: "State / Territory" },
        { key: "locations", label: "Listings", format: formatNumber },
        { key: "city_population", label: "Population", format: formatNumber },
        { key: "pop_per_listing", label: "Population Per Listing", format: formatNumber },
        { key: "median_household_income", label: "Median Income", format: formatNumber }
      ], []);
      renderSimpleTable("reportBrandsTable", [
        { key: "brand", label: "Brand" },
        { key: "locations", label: "Number of Locations", format: formatNumber },
        { key: "states", label: "Number of States", format: formatNumber },
        { key: "counties", label: "Counties Covered", format: formatNumber },
        { key: "cities", label: "Cities Covered", format: formatNumber },
        { key: "zips", label: "ZIP Codes Covered", format: formatNumber }
      ], []);
      renderSimpleTable("reportGapsTable", [
        { key: "state_name", label: "State" },
        { key: "county", label: "County" },
        { key: "city", label: "City" },
        { key: "zip_code", label: "ZIP Code" },
        { key: "competitor_locations", label: "Competitor Listings", format: formatNumber },
        { key: "brands_present", label: "Competitor Brands", format: formatBrandList },
        { key: "population", label: "Census Population", format: formatNumber },
        { key: "median_household_income", label: "Median Income", format: formatNumber },
        { key: "median_age", label: "Median Age", format: formatNumber }
      ], []);
      el("reportEmptyStates").innerHTML = '<span>0</span>';
      renderSimpleTable("reportSampleRecords", [
        { key: "name", label: "Name" },
        { key: "address", label: "Street" },
        { key: "city", label: "City" },
        { key: "state_name", label: "State" },
        { key: "county", label: "County" },
        { key: "zip_code", label: "Zip Code" },
        { key: "phone_number", label: "Phone" },
        { key: "latitude", label: "Latitude" },
        { key: "longitude", label: "Longitude" },
        { key: "country", label: "Country" },
        { key: "last_observed_at", label: "Last Updated" }
      ], []);
    }

function reportHasBusinessData(totals = {}) {
      return Number((totals.total_listings ?? totals.total_stores) || 0) > 0
        || Number(totals.total_brands || 0) > 0
        || Number(totals.active_market_locations || 0) > 0;
    }

// Every other poll in the app has an attempt budget (the quality tab retries
// 40x, the stale-refetch 3x). This one had none: each poll that came back
// still "refreshing" scheduled another, forever - so a background pass that
// never settles left the page re-fetching every few seconds and re-raising
// the "Preparing reporting data" spinner each time it rendered. A poll that
// has not converged after this many tries is not going to; say so once and
// stop rather than spinning for the rest of the session.
const REPORTING_WARMUP_POLL_LIMIT = 20;
let reportingWarmupPolls = 0;

function resetReportingWarmupPolls() {
      reportingWarmupPolls = 0;
      if (reportingWarmupTimer) {
        clearTimeout(reportingWarmupTimer);
        reportingWarmupTimer = null;
      }
    }

function scheduleReportingWarmupPoll(delayMs = 5000) {
      if (reportingWarmupTimer) return;
      if (reportingWarmupPolls >= REPORTING_WARMUP_POLL_LIMIT) return;
      reportingWarmupPolls += 1;
      reportingWarmupTimer = window.setTimeout(() => {
        reportingWarmupTimer = null;
        if (document.getElementById("reportingView")?.classList.contains("hidden")) return;
        loadReporting({ interactive: false });
      }, delayMs);
    }
// ---- Auto-apply filters: one switch, shared by both reporting tabs ------
//
// Location Intelligence and Data Quality both carry a filter rail that
// should behave like a live dashboard - move a control, see the result -
// plus an escape hatch for anyone setting several filters at once who does
// not want a query fired between each one. The two tabs differ only in
// which controls they watch and what "apply" means, so they pass those in
// and this owns the switch, the debounce and the deferral rules; the
// alternative is the same plumbing maintained in two files, which is what
// attachSearchableSelect() in common.js exists to avoid.
//
// It is a switch rather than a button that renames itself ("Stop auto
// apply" / "Restart auto apply", which is what the Data Quality tab used to
// have): that label describes what a click would do, i.e. the opposite of
// the current state, so reading it told you nothing at a glance.
const autoApplyToggles = new Map();

function injectAutoApplyToggleStyles() {
  if (el("autoApplyToggleStyles")) return;
  // Carried by the component, not by either tab's stylesheet: the Location
  // rail is styled inline in integrations.html and the Quality rail by
  // reporting-tabs.js injectStyles(), and a shared control cannot depend on
  // which of those happens to own the page it lands in.
  const style = document.createElement("style");
  style.id = "autoApplyToggleStyles";
  style.textContent = `
    .auto-apply-toggle{box-sizing:border-box;width:100%;min-width:0}
    .auto-apply-toggle-label{position:relative;display:flex;align-items:center;gap:8px;box-sizing:border-box;width:100%;margin:0;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font-size:12px;font-weight:600;cursor:pointer;user-select:none}
    /* Hidden, not replaced: it stays a real checkbox so the switch keeps
       keyboard focus, Space to flip it, and role="switch" for screen
       readers. Class-scoped because both rails have a broad
       "every input in this panel" rule that would otherwise size it. */
    .auto-apply-toggle .auto-apply-toggle-input{position:absolute;width:1px;height:1px;padding:0;margin:0;border:0;opacity:0;pointer-events:none}
    .auto-apply-toggle-track{position:relative;flex:0 0 auto;width:34px;height:18px;border-radius:999px;background:#cbd5e1;transition:background .15s ease}
    .auto-apply-toggle-thumb{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;background:#fff;box-shadow:0 1px 2px rgba(15,23,42,.35);transition:transform .15s ease}
    .auto-apply-toggle .auto-apply-toggle-input:checked+.auto-apply-toggle-track{background:var(--accent,#2563eb)}
    .auto-apply-toggle .auto-apply-toggle-input:checked+.auto-apply-toggle-track .auto-apply-toggle-thumb{transform:translateX(16px)}
    .auto-apply-toggle .auto-apply-toggle-input:focus-visible+.auto-apply-toggle-track{outline:2px solid var(--accent,#2563eb);outline-offset:2px}
    .auto-apply-toggle-text{flex:1 1 auto;min-width:0}
    .auto-apply-toggle-state{flex:0 0 auto;font-size:11px;font-weight:750;letter-spacing:.02em;text-transform:uppercase;color:var(--accent,#2563eb)}
    /* Off is a state the user chose and will then forget: the amber card
       (kept from the button this replaced) keeps "filters are not applying"
       visible while they work down the rest of the rail. */
    .auto-apply-toggle[data-auto='off'] .auto-apply-toggle-label{background:#fff7ed;border-color:#f59e0b;color:#b45309}
    .auto-apply-toggle[data-auto='off'] .auto-apply-toggle-state{color:#b45309}
  `;
  document.head.appendChild(style);
}

// hostId          - empty element the switch is mounted into.
// watchIds        - controls that need nothing but "changed, reload"; a tab
//                   with controls that do more (cascading dropdowns) wires
//                   those itself and calls schedule() at the end.
// shouldDefer()   - true while applying would be disruptive; the change is
//                   held and run by resume() once that passes.
// Returns { element, input, isEnabled, schedule, resume, cancel } - cancel()
// is for an explicit Apply/Reset, which subsumes anything queued here.
function attachAutoApplyToggle(hostId, { id = "", label = "Auto apply filters", title = "", watchIds = [], onApply = null, shouldDefer = null, delayMs = 400 } = {}) {
  const host = el(hostId);
  if (!host) return null;
  if (autoApplyToggles.has(hostId)) return autoApplyToggles.get(hostId);
  injectAutoApplyToggleStyles();
  const inputId = id || `${hostId}Input`;
  const wrapper = document.createElement("div");
  wrapper.className = "auto-apply-toggle";
  wrapper.dataset.auto = "on";
  wrapper.innerHTML = `
    <label class="auto-apply-toggle-label" for="${inputId}"${title ? ` title="${escapeHtml(title)}"` : ""}>
      <input type="checkbox" role="switch" class="auto-apply-toggle-input" id="${inputId}" checked>
      <span class="auto-apply-toggle-track" aria-hidden="true"><span class="auto-apply-toggle-thumb"></span></span>
      <span class="auto-apply-toggle-text">${escapeHtml(label)}</span>
      <span class="auto-apply-toggle-state" aria-hidden="true">On</span>
    </label>
  `;
  host.appendChild(wrapper);
  const input = wrapper.querySelector(".auto-apply-toggle-input");
  const stateText = wrapper.querySelector(".auto-apply-toggle-state");
  let timer = null;
  // Set when a change arrived that shouldDefer() asked us to hold, so
  // resume() can tell "something is waiting" from "nothing happened".
  let deferred = false;

  const cancel = () => {
    window.clearTimeout(timer);
    timer = null;
    deferred = false;
  };

  const schedule = () => {
    if (!input.checked) return;
    if (typeof shouldDefer === "function" && shouldDefer()) {
      window.clearTimeout(timer);
      deferred = true;
      return;
    }
    deferred = false;
    // Debounced: setting three filters in a row is one query, not three.
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      if (typeof onApply === "function") onApply();
    }, delayMs);
  };

  const resume = () => {
    // Only fires if something actually changed while deferred, so opening
    // and closing a dropdown without touching it costs nothing.
    if (deferred) schedule();
  };

  input.addEventListener("change", () => {
    wrapper.dataset.auto = input.checked ? "on" : "off";
    stateText.textContent = input.checked ? "On" : "Off";
    if (input.checked) {
      // Switching back on applies whatever moved while it was off, so the
      // view can never sit out of step with the controls.
      schedule();
    } else {
      cancel();
    }
  });

  watchIds.forEach((watchId) => el(watchId)?.addEventListener("change", schedule));

  const controller = { element: wrapper, input, isEnabled: () => input.checked, schedule, resume, cancel };
  autoApplyToggles.set(hostId, controller);
  return controller;
}

function checkedValues(name) {
      return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
    }
function renderBrandChecks(containerId, name, brands, checkedBrands, emptyMessage = "No brands available.") {
      const selected = new Set(checkedBrands || []);
      el(containerId).innerHTML = brands.length
        ? brands.map((brand) => `<label><input type="checkbox" name="${name}" value="${escapeHtml(brand)}" ${selected.has(brand) ? "checked" : ""}>${escapeHtml(brand)}</label>`).join("")
        : `<div class="report-status">${escapeHtml(emptyMessage)}</div>`;
    }
function renderBrandChecksWithSelectAll(containerId, name, brands, checkedBrands, emptyMessage = "No brands available.") {
      const container = el(containerId);
      if (!container) return;
      const selected = new Set(checkedBrands || []);
      if (brands.length === 0) {
        container.innerHTML = `<div class="report-status" style="padding: 10px 8px; font-size: 11px; color: var(--muted);">${escapeHtml(emptyMessage)}</div>`;
        return;
      }

      const allChecked = brands.length > 0 && brands.every((b) => selected.has(b));
      const someChecked = brands.some((b) => selected.has(b));

      let html = `
        <div class="competitor-dropdown-toolbar" style="display: flex; justify-content: space-between; align-items: center; padding: 4px 6px 8px; border-bottom: 1px solid var(--line); margin-bottom: 6px; position: sticky; top: 0; background: var(--panel); z-index: 2;">
          <label style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 11px; cursor: pointer; user-select: none; margin: 0;">
            <input type="checkbox" name="${name}_selectAll" ${allChecked ? "checked" : ""} style="cursor: pointer; margin: 0;">
            <span class="select-all-label">${allChecked ? "Deselect All" : "Select All"}</span>
          </label>
          <div style="display: flex; gap: 6px; font-size: 11px;">
            <button type="button" data-action="select-all" style="background: none; border: 0; color: #2563eb; font-weight: 600; cursor: pointer; padding: 0;">All</button>
            <span style="color: var(--line);">|</span>
            <button type="button" data-action="deselect-all" style="background: none; border: 0; color: #64748b; font-weight: 600; cursor: pointer; padding: 0;">None</button>
          </div>
        </div>
        <input type="search" class="competitor-brand-search" autocomplete="off" aria-label="Search competitor brands" placeholder="Type 2+ letters to search brands" style="width: 100%; box-sizing: border-box; padding: 5px 8px; margin-bottom: 6px; border: 1px solid var(--line); border-radius: 6px; font-size: 11px; font-family: inherit;">
        <div class="competitor-brand-items" style="display: grid; gap: 4px;">
      `;

      html += brands.map((brand) => `
        <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; cursor: pointer; padding: 3px 4px; border-radius: 4px; user-select: none;">
          <input type="checkbox" name="${name}" value="${escapeHtml(brand)}" ${selected.has(brand) ? "checked" : ""} style="cursor: pointer; margin: 0; flex-shrink: 0;">
          <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 240px;" title="${escapeHtml(formatBrandName(brand))}">${escapeHtml(formatBrandName(brand))}</span>
        </label>
      `).join("");

      html += `</div>`;
      container.innerHTML = html;

      const selectAllCheckbox = container.querySelector(`input[name="${name}_selectAll"]`);
      const selectAllLabel = container.querySelector(".select-all-label");
      const checkBoxes = container.querySelectorAll(`input[name="${name}"]`);

      const brandSearch = container.querySelector(".competitor-brand-search");
      if (brandSearch) {
        brandSearch.addEventListener("input", () => {
          const query = brandSearch.value.trim().toLowerCase();
          // Rows are hidden, never removed - a brand that is checked but
          // filtered out of view must still count as selected, so its
          // checkbox has to stay in the DOM.
          checkBoxes.forEach((checkbox) => {
            const row = checkbox.closest("label");
            if (!row) return;
            const matches = query.length < 2 || String(checkbox.value || "").toLowerCase().includes(query) || row.textContent.toLowerCase().includes(query);
            row.style.display = matches ? "" : "none";
          });
        });
      }

      function syncSelectAllState() {
        const total = checkBoxes.length;
        const checkedCount = [...checkBoxes].filter((cb) => cb.checked).length;
        if (selectAllCheckbox) {
          if (checkedCount === 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
            if (selectAllLabel) selectAllLabel.textContent = "Select All";
          } else if (checkedCount === total) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
            if (selectAllLabel) selectAllLabel.textContent = "Deselect All";
          } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
            if (selectAllLabel) selectAllLabel.textContent = "Select All";
          }
        }
        updateCompetitorDropdownText();
      }

      if (selectAllCheckbox && someChecked && !allChecked) {
        selectAllCheckbox.indeterminate = true;
      }

      if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener("change", (e) => {
          const isChecked = e.target.checked;
          checkBoxes.forEach((cb) => { cb.checked = isChecked; });
          if (selectAllLabel) selectAllLabel.textContent = isChecked ? "Deselect All" : "Select All";
          updateCompetitorDropdownText();
        });
      }

      const allBtn = container.querySelector('[data-action="select-all"]');
      if (allBtn) {
        allBtn.addEventListener("click", () => {
          checkBoxes.forEach((cb) => { cb.checked = true; });
          syncSelectAllState();
        });
      }

      const noneBtn = container.querySelector('[data-action="deselect-all"]');
      if (noneBtn) {
        noneBtn.addEventListener("click", () => {
          checkBoxes.forEach((cb) => { cb.checked = false; });
          syncSelectAllState();
        });
      }

      checkBoxes.forEach((cb) => {
        cb.addEventListener("change", syncSelectAllState);
      });
    }
let reportingMap = null;
let mapMarkerLayerGroup = null;
let stateBoundaryLayerGroup = null;
let stateCirclesLayerGroup = null;
let cityCirclesLayerGroup = null;
// ZIP-level drill-down tier (BUG-102): sits between the city circles and the
// raw per-listing pins. Same aggregate-circle-with-tooltip pattern as the
// city tier below, just keyed by zip_code instead of city+state.
let zipCirclesLayerGroup = null;
// These two were cross-named for a long time: the loop over map_records (the
// individual listings) filled the group called "gap", and the loop over the
// whitespace gap ZIPs filled the group called "pin". syncMapLayersByZoom()
// then reasoned about them BY NAME and did the exact opposite of what its own
// comment claimed - it zoom-gated the gaps and always-showed the listings.
// That is the defect behind BB14 ("when zoom in sometimes the red green and
// gaps dot are going away"). Named for their contents now, so the next reader
// cannot be misled the same way.
let gapMarkersLayerGroup = null;    // whitespace candidate ZIPs (orange)
let storeMarkersLayerGroup = null;  // individual listings (blue/green/red)
// National whitespace-strength heatmap overlay (opt-in, off by default - see
// heatmapToggleBtn). Backed by GET /api/reporting/heatmap, ~31.6k square
// cells nationwide (3km half-width from each cell's centroid). Two
// perf choices, both deliberate given that cell count:
//  1. A dedicated L.canvas() renderer instead of the default SVG one - SVG
//     would mean 31k+ real DOM nodes (one per rectangle), which is the kind
//     of thing that visibly freezes a browser tab; canvas draws all of them
//     into one bitmap, so cost stays roughly constant regardless of how many
//     shapes are in the layer.
//  2. Every rectangle is built with `interactive: false`. Canvas hit-testing
//     for mouse events on an interactive canvas layer is O(shapes-on-screen)
//     PER mousemove - with 31k shapes that turns "hover the map" into a
//     stutter. A per-cell tooltip was not worth that cost, so this overlay
//     reads as pure color instead (bindHeatmapLegend() supplies the
//     red-weak/green-strong key so the color still means something without
//     hovering).
// Data is fetched once and cached in heatmapCellsCache - toggling the layer
// off/on again re-shows the already-built layer group rather than re-fetching
// or rebuilding 31k rectangles a second time.
let heatmapLayerGroup = null;
let heatmapCanvasRenderer = null;
let heatmapCellsCache = null;   // full /api/reporting/heatmap payload, once fetched
let heatmapFetchPromise = null; // in-flight fetch, so a fast double-click can't fire two requests
let heatmapVisible = false;
let heatmapToggleListenerAttached = false;
let staticMapZoom = 1;
// Keep the complete contiguous US in view, with enough scale to read the
// state-level layer without opening on an overly distant national view.
const DEFAULT_US_MAP_VIEW = { center: [39.8283, -98.5795], zoom: 5 };
const DEFAULT_US_BOUNDS = [[24.3963, -125.0], [49.3844, -66.9346]];
// How many listings the server will hand this map, at most: the reporting
// query ends in LIMIT 1000 and the SQLite mirror takes the same 1000-row
// slice. Neither orders the rows first, so on a dataset larger than that the
// map receives an arbitrary block rather than a spread - on the current cache
// (42,869 listings, all with coordinates, across 59 states) the first 1000
// rows are 973 Massachusetts, which is exactly the reported "only 1 area
// showing solid dots". Raising or ordering that limit is a server change; all
// this map can do is not present the sample as the whole picture.
const MAP_RECORD_DISPLAY_CAP = 1000;
// Zooming into a single state (or narrower) means the national round-robin
// sample is the wrong data source - it deliberately spreads only ~1/state
// worth of rows nationwide, so a state with real depth reads as sparse. Once
// the user is at state tier or closer, fetch that area's own full listing
// set instead (see fetchFullScopeMapRecords / maybeFetchFullScopeMapData).
// A hard per-scope ceiling still applies server-side (spec handed to the
// backend owner alongside this change) because even one state can carry
// several thousand rows and the browser still has to render every marker.
const SCOPED_MAP_ZOOM_THRESHOLD = 6.0;
const SCOPED_MAP_FETCH_DEBOUNCE_MS = 450;
// The four-tier zoom drill-down (BUG-102 adds the ZIP tier between city and
// listing): nation -> state bubbles (< CITY_TIER_ZOOM_THRESHOLD) -> city
// bubbles (< ZIP_TIER_ZOOM_THRESHOLD) -> ZIP bubbles (< LISTING_TIER_ZOOM_THRESHOLD)
// -> individual listing pins. See syncMapLayersByZoom().
const CITY_TIER_ZOOM_THRESHOLD = 6.0;
const ZIP_TIER_ZOOM_THRESHOLD = 9.5;
const LISTING_TIER_ZOOM_THRESHOLD = 13.0;
// Per-scope caches so panning/zooming within a state already fetched does
// not refire the request, and so switching scopes never mixes their rows.
const scopedMapRecordsCache = new Map(); // scopeKey -> records[]
const scopedMapFetchInFlight = new Set();
let scopedMapFetchTimer = null;
// The state a marker click or the state filter put the map "inside" of. Read
// alongside the zoom level so the scoped fetch fires from either path (a
// direct filter pick or a bubble click that only calls setView).
let currentMapScopeState = "";
// The last payload renderReportingMap was actually given, so a scoped fetch
// landing later can re-render with the fuller records for the SAME gaps/
// state bubbles/filters without re-running the whole loadReporting() cycle.
let lastRenderedMapPayload = { gapRecords: [], stateRecords: [], filters: {} };
const stateNameToCode = {
      Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA", Colorado: "CO", Connecticut: "CT", Delaware: "DE",
      Florida: "FL", Georgia: "GA", Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA", Kansas: "KS",
      Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD", Massachusetts: "MA", Michigan: "MI", Minnesota: "MN", Mississippi: "MS",
      Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
      "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH", Oklahoma: "OK", Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI",
      "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX", Utah: "UT", Vermont: "VT", Virginia: "VA",
      Washington: "WA", "West Virginia": "WV", Wisconsin: "WI", Wyoming: "WY", "District of Columbia": "DC",
      "Puerto Rico": "PR", "Guam": "GU", "Virgin Islands": "VI", "American Samoa": "AS", "Northern Mariana Islands": "MP"
    };
const stateCodeToName = Object.fromEntries(Object.entries(stateNameToCode).map(([name, code]) => [code, name]));
const stateCentroids = {
      AL: [32.8067, -86.7911], AK: [61.3707, -152.4044], AZ: [33.7298, -111.4312], AR: [34.9697, -92.3731],
      CA: [36.1162, -119.6816], CO: [39.0598, -105.3111], CT: [41.5978, -72.7554], DE: [39.3185, -75.5071],
      FL: [27.7663, -81.6868], GA: [33.0406, -83.6431], HI: [21.0943, -157.4983], ID: [44.2405, -114.4788],
      IL: [40.3495, -88.9861], IN: [39.8494, -86.2583], IA: [42.0115, -93.2105], KS: [38.5266, -96.7265],
      KY: [37.6681, -84.6701], LA: [31.1695, -91.8678], ME: [44.6939, -69.3819], MD: [39.0639, -76.8021],
      MA: [42.2302, -71.5301], MI: [43.3266, -84.5361], MN: [45.6945, -93.9002], MS: [32.7416, -89.6787],
      MO: [38.4561, -92.2884], MT: [46.9219, -110.4544], NE: [41.1254, -98.2681], NV: [38.3135, -117.0554],
      NH: [43.4525, -71.5639], NJ: [40.2989, -74.521], NM: [34.8405, -106.2485], NY: [42.1657, -74.9481],
      NC: [35.6301, -79.8064], ND: [47.5289, -99.784], OH: [40.3888, -82.7649], OK: [35.5653, -96.9289],
      OR: [44.572, -122.0709], PA: [40.5908, -77.2098], RI: [41.6809, -71.5118], SC: [33.8569, -80.945],
      SD: [44.2998, -99.4388], TN: [35.7478, -86.6923], TX: [31.0545, -97.5635], UT: [40.15, -111.8624],
      VT: [44.0459, -72.7107], VA: [37.7693, -78.17], WA: [47.4009, -121.4905], WV: [38.4912, -80.9545],
      WI: [44.2685, -89.6165], WY: [42.756, -107.3025], DC: [38.9072, -77.0369],
      PR: [18.2208, -66.5901], GU: [13.4443, 144.7937], VI: [18.3358, -64.8963], MP: [15.0979, 145.6739], AS: [-14.2710, -170.1322]
    };
const defaultStateRecords = Object.entries(stateCodeToName).map(([state, state_name]) => ({ state, state_name, locations: 0 }));
const staticStateLayout = [
      "WA", "", "MT", "ND", "MN", "", "WI", "MI", "", "NY", "VT", "ME",
      "OR", "ID", "WY", "SD", "IA", "IL", "IN", "OH", "PA", "NJ", "NH", "MA",
      "CA", "NV", "UT", "NE", "MO", "KY", "WV", "VA", "MD", "DE", "CT", "RI",
      "AZ", "CO", "KS", "AR", "TN", "NC", "SC", "", "", "", "", "",
      "NM", "OK", "LA", "MS", "AL", "GA", "", "", "", "", "", "",
      "AK", "HI", "TX", "", "", "FL", "DC", "", "", "", "", ""
    ];
let usStatesGeoJSONPromise = null;
function selectedPrimaryBrand(fallbackFilters = {}) {
      const fromSelect = el("reportMainBrandSelect")?.value || "";
      const fromFilters = Array.isArray(fallbackFilters.main_brands) ? (fallbackFilters.main_brands[0] || "") : "";
      return fromSelect || fromFilters;
    }
function getUSStatesGeoJSON() {
      if (!usStatesGeoJSONPromise) {
        usStatesGeoJSONPromise = fetch("vendor/geo/us-states-10m.json")
          .then((response) => (response.ok ? response.json() : null))
          .then((topo) => {
            if (!topo || !window.topojson) return null;
            return topojson.feature(topo, topo.objects.states);
          })
          .catch(() => null);
      }
      return usStatesGeoJSONPromise;
    }
function isUSLatLong(lat, lon) {
      if (isNaN(lat) || isNaN(lon)) return false;
      if (lat < 13.0 || lat > 72.0) return false;
      const isWestUS = (lon >= -180.0 && lon <= -64.0);
      const isEastUSTerritory = (lon >= 144.0 && lon <= 146.0);
      return isWestUS || isEastUSTerritory;
    }
function renderStaticUSMap(stateRecords = []) {
      const target = el("reportingMap");
      if (!target) return;
      const stateCounts = new Map((stateRecords || []).filter((row) => Number(row.locations || 0) > 0).map((row) => [String(row.state || "").toUpperCase(), Number(row.locations || 0)]));
      target.innerHTML = `
        <div class="static-us-map-wrap">
          <div class="static-us-map-controls" aria-label="Map zoom controls">
            <button type="button" data-static-map-zoom="in" title="Zoom in">+</button>
            <button type="button" data-static-map-zoom="out" title="Zoom out">-</button>
            <button type="button" data-static-map-zoom="reset" title="Reset zoom">1</button>
          </div>
          <div class="static-us-map-stage" style="transform: scale(${staticMapZoom});">
            <div class="static-us-map">${staticStateLayout.map((code) => {
              if (!code) return '<div></div>';
              const count = stateCounts.get(code) || 0;
              if (!count) return `<div class="static-state-cell empty-state-cell" title="${escapeHtml(stateCodeToName[code] || code)}">${escapeHtml(code)}</div>`;
              return `<div class="static-state-cell" title="${escapeHtml(stateCodeToName[code] || code)}">${escapeHtml(code)}<br>${formatNumber(count)} Listings</div>`;
            }).join("")}</div>
          </div>
        </div>
      `;
      target.querySelectorAll("[data-static-map-zoom]").forEach((button) => {
        button.addEventListener("click", () => {
          const action = button.dataset.staticMapZoom;
          if (action === "in") staticMapZoom = Math.min(2.2, Math.round((staticMapZoom + 0.2) * 10) / 10);
          else if (action === "out") staticMapZoom = Math.max(0.8, Math.round((staticMapZoom - 0.2) * 10) / 10);
          else staticMapZoom = 1;
          renderStaticUSMap(stateRecords);
        });
      });
    }
// A layer with nothing in it is not a layer worth switching to.
function layerHasContent(group) {
  if (!group) return false;
  try { return group.getLayers().length > 0; } catch (_) { return false; }
}

// ...and neither is a layer whose content is all somewhere else. This is what
// makes the state -> city drill-down behave: clicking a state bubble flies to
// that state at zoom 7, which is city tier, but the city bubbles are built
// from map_records - a capped payload that may hold nothing at all for that
// state (see MAP_RECORD_DISPLAY_CAP). Handing over to a tier whose markers
// are two thousand miles away is what "clicking the state leads nowhere"
// actually was: the state bubbles came off and nothing replaced them on
// screen. Checking the CURRENT VIEW instead keeps the state bubble up when
// there is no city detail to drill into here.
function layerHasContentInView(group) {
  if (!reportingMap || !group) return false;
  try {
    const view = reportingMap.getBounds();
    return group.getLayers().some((layer) => {
      const position = typeof layer.getLatLng === "function" ? layer.getLatLng() : null;
      return position ? view.contains(position) : true;
    });
  } catch (_) {
    return layerHasContent(group);
  }
}

// Add/remove without asking the caller to remember which state a layer is in.
// The old add/remove pairs, written out three times per branch, are how the
// two marker groups ended up being treated inconsistently in the first place.
// A sticky hover tooltip tracks the mouse via a listener the tooltip itself
// owns, not something that is torn down for free just because its marker is
// about to be hidden/removed - if the user zooms (mouse never moves, e.g.
// scroll-wheel/pinch) right as this group's tier is hidden, or a scoped
// re-fetch rebuilds the layers under an open tooltip, an already-open
// tooltip/popup on one of its markers can be left rendered on screen with
// the OLD tier's aggregate count, while the layer actually now underneath
// the cursor is a different tier (e.g. individual listing pins) - the "hover
// info doesn't match what's in the background" report. Close them explicitly
// before the layer is removed/cleared so nothing stale can linger.
function closeGroupOverlays(group) {
  if (!group) return;
  group.eachLayer((layer) => {
    if (typeof layer.closeTooltip === "function") layer.closeTooltip();
    if (typeof layer.closePopup === "function") layer.closePopup();
  });
}

// clearLayers() alone can leave the same stale-tooltip trace as removeLayer()
// does below - always close what is open on a group before wiping it.
function clearMapLayerGroup(group) {
  if (!group) return;
  closeGroupOverlays(group);
  group.clearLayers();
}

function toggleMapLayer(group, visible) {
  if (!group || !reportingMap) return;
  const attached = reportingMap.hasLayer(group);
  if (visible && !attached) {
    reportingMap.addLayer(group);
  } else if (!visible && attached) {
    closeGroupOverlays(group);
    reportingMap.removeLayer(group);
  }
}

// Red (score 0, weak market) -> green (score 1, strong market), a simple HSL
// hue sweep (0=red to 120=green). Fixed, readable saturation/lightness so the
// scale stays legible over the light OSM basemap at typical zoom levels
// rather than washing out pale or turning near-black.
// Exact 10-color decile palette, user-specified (2026-09-10) - discrete
// bins by percentile rank ("Ntile"), not a continuous gradient. Index 0 is
// RED and is used for the HIGHEST-scoring decile; index 9 is GREEN, for the
// LOWEST-scoring decile - user-directed ordering ("red having highest
// score and ending green"), the reverse of the red=weak/green=strong
// framing this map used earlier today. If that reads backwards later,
// this is the one place to flip: reverse HEATMAP_DECILE_COLORS.
const HEATMAP_DECILE_COLORS = [
  "#E53935", "#F4511E", "#FB8C00", "#FFA726", "#FDD835",
  "#D4E157", "#9CCC65", "#7CB342", "#43A047", "#2E7D32",
];
function heatmapScoreColor(percentile) {
  const clamped = Math.max(0, Math.min(1, Number(percentile) || 0));
  // 10 even bins: [0, .1) -> bin 0, ... [.9, 1] -> bin 9. Math.min guards
  // the exact percentile===1 edge case (which would otherwise compute
  // bin 10, one past the array).
  const bin = Math.min(9, Math.floor(clamped * 10));
  // Reversed: bin 9 (top decile, highest scores) -> palette index 0 (red).
  return HEATMAP_DECILE_COLORS[9 - bin];
}

// State/city strength coloring (2026-09-10): the state/city zoom-tier bubbles
// reuse the EXACT SAME 0..1 score `/api/reporting/heatmap` already computes
// per 6km cell (backend rolls it up with a listing_count+zip_count weighted
// average - see reporting_heatmap()'s docstring in workflow_server.py for the
// weighting reasoning), rescaled through the SAME percentile ranking as the
// square-cell layer below so a state/city bubble's color means exactly the
// same thing as a cell's color on the same map.
//
// Percentile rank, not linear min-max (user-directed): this dataset's raw
// scores cluster tightly (measured live: 0.0-0.54, most cells well under
// 0.3), so a straight (value-lo)/(hi-lo) rescale still leaves the bulk of
// cells crammed into a narrow slice of the color range if that bulk itself
// is skewed toward one end - exactly what "auto broken into percentile, not
// hardcoded" is asking to fix. Ranking by WHERE a score falls among every
// other score (its percentile) guarantees the visible color range is always
// used evenly, regardless of how skewed the underlying value distribution
// is. heatmapScoreSorted is set once buildHeatmapLayer() has seen the
// payload; until then rescaleHeatmapScore() returns a neutral midpoint and
// callers fall back to their pre-existing static styling.
let heatmapScoreSorted = [];

function computeHeatmapScoreRange(payload) {
  const cells = Array.isArray(payload?.cells) ? payload.cells : [];
  const usCells = cells.filter((cell) => isUSLatLong(Number(cell.lat), Number(cell.lon)));
  const rawScores = usCells.map((cell) => Number(cell.score) || 0);
  rawScores.sort((a, b) => a - b);
  return rawScores;
}

// Percentile rank of `score` within the sorted distribution, via binary
// search - O(log n) per lookup, done once per cell/state/city at render
// time (tens of thousands of cells, this stays fast).
function rescaleHeatmapScore(score) {
  const sorted = heatmapScoreSorted;
  if (!sorted.length) return 0.5;
  const value = Number(score) || 0;
  let lo = 0, hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (sorted[mid] < value) lo = mid + 1; else hi = mid;
  }
  return sorted.length > 1 ? lo / (sorted.length - 1) : 0.5;
}

function heatmapColorForState(stateCode) {
  const rows = heatmapCellsCache && Array.isArray(heatmapCellsCache.state_scores) ? heatmapCellsCache.state_scores : null;
  if (!rows) return null;
  const row = rows.find((r) => String(r.state || "").toUpperCase() === String(stateCode || "").toUpperCase());
  if (!row) return null; // no cell data resolved for this state - fall back to static styling
  return { color: heatmapScoreColor(rescaleHeatmapScore(row.score)), row };
}

function heatmapColorForCity(cityName, stateCode) {
  const rows = heatmapCellsCache && Array.isArray(heatmapCellsCache.city_scores) ? heatmapCellsCache.city_scores : null;
  if (!rows) return null;
  const wantCity = String(cityName || "").trim().toLowerCase();
  const wantState = String(stateCode || "").toUpperCase();
  const row = rows.find((r) => String(r.city || "").trim().toLowerCase() === wantCity && String(r.state || "").toUpperCase() === wantState);
  if (!row) return null;
  return { color: heatmapScoreColor(rescaleHeatmapScore(row.score)), row };
}

// Rebuilds one state bubble's divIcon in place (color only) once heatmap
// scores land after the bubble was already drawn - see
// applyHeatmapScoreColorsToCircleTiers().
function buildStateBubbleIcon(stateCode, hasRecords, size, bg, border, textColor) {
  const html = hasRecords
    ? `<div style="width:${size}px; height:${size}px; line-height:${size - 4}px; border-radius:50%; background:${bg}; border:2px solid ${border}; color:${textColor}; font-size:11px; font-weight:800; text-align:center; box-sizing:border-box; cursor:pointer; box-shadow:0 1px 4px rgba(0,0,0,0.15);">${escapeHtml(stateCode)}</div>`
    : `<div style="width:${size}px; height:${size}px; line-height:${size - 2}px; border-radius:50%; background:${bg}; border:1px solid ${border}; color:${textColor}; font-size:10px; font-weight:700; text-align:center; box-sizing:border-box; cursor:pointer; box-shadow:0 1px 2px rgba(0,0,0,0.08);">${escapeHtml(stateCode)}</div>`;
  return L.divIcon({ className: "", html, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
}

// Registries populated fresh on every renderReportingMap() call, so a
// heatmap payload landing AFTER that render (the common case - it's fetched
// once, async, in showHeatmapLayerByDefault) can still recolor the
// already-drawn bubbles in place instead of waiting for the next full
// re-render. Keyed by state code / "city|STATE".
let stateBubbleRegistry = new Map();
let cityCircleRegistry = new Map();

// Called once after fetchHeatmapCells() first resolves, and harmlessly a
// no-op if the state/city layers have not been built yet or already carry
// the right colors from being built after the payload landed.
function applyHeatmapScoreColorsToCircleTiers() {
  stateBubbleRegistry.forEach((entry, stateCode) => {
    const scored = entry.hasRecords ? heatmapColorForState(stateCode) : null;
    if (!scored) return;
    const bg = scored.color;
    entry.marker.setIcon(buildStateBubbleIcon(stateCode, entry.hasRecords, entry.size, bg, bg, "#ffffff"));
    entry.marker.setTooltipContent(stateBubbleTooltipHtml(entry.stateName, entry.storeCount, entry.hasRecords, scored.row));
  });
  cityCircleRegistry.forEach((entry) => {
    const scored = heatmapColorForCity(entry.city, entry.state);
    if (!scored) return;
    entry.marker.setStyle({ fillColor: scored.color, color: scored.color });
    entry.marker.setTooltipContent(cityBubbleTooltipHtml(entry.city, entry.state, entry.count, scored.row));
  });
}

// Shared tooltip builders so the initial render and the post-fetch recolor
// above produce byte-identical markup - a whitespace-strength line is only
// added when a rolled-up score actually exists for that state/city.
function heatmapStrengthLine(row) {
  if (!row) return "";
  const pct = Math.round((Number(row.score) || 0) * 100);
  return `<br/><span style="color:#334155; font-size:12px;">Whitespace strength: <strong>${pct}%</strong> <span style="color:#94a3b8;">(${formatNumber(row.zip_count || 0)} ZIPs, ${formatNumber(row.cell_count || 0)} cells)</span></span>`;
}

function stateBubbleTooltipHtml(stateName, storeCount, hasRecords, scoreRow) {
  return `
    <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4; padding: 2px 4px;">
      <strong style="color: #0f172a; font-size: 14px;">${escapeHtml(stateName)}</strong><br/>
      <span style="color: ${hasRecords ? '#2563eb' : '#64748b'}; font-weight: 700; font-size: 13px;">${formatNumber(storeCount)} Listing${storeCount === 1 ? "" : "s"}</span>
      ${heatmapStrengthLine(scoreRow)}
    </div>
  `;
}

function cityBubbleTooltipHtml(city, state, count, scoreRow) {
  return `
    <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4; padding: 2px 4px;">
      <strong style="color: #0f172a; font-size: 14px;">${escapeHtml(city)}, ${escapeHtml(state)}</strong><br/>
      <span style="color: #7c3aed; font-weight: 700; font-size: 13px;">${formatNumber(count)} Listing${count === 1 ? "" : "s"}</span>
      ${heatmapStrengthLine(scoreRow)}
    </div>
  `;
}

// Builds the 31k-ish rectangles once from a cached /api/reporting/heatmap
// payload. See the heatmapLayerGroup comment above for why canvas +
// non-interactive shapes were chosen over the default SVG/interactive path.
function buildHeatmapLayer(payload) {
  if (!heatmapLayerGroup) return;
  clearMapLayerGroup(heatmapLayerGroup);
  const cells = Array.isArray(payload?.cells) ? payload.cells : [];
  const halfWidthKm = Number(payload?.cell_half_width_km) || 3.0;
  const KM_PER_DEGREE_LAT = 111.32;
  // The backend's score is min-max normalized across ALL cells nationwide,
  // but the real spread of that normalization (measured live) only reaches
  // about 0.0-0.54, never approaching 1.0 - no single 6km cell is uniformly
  // "the strongest possible" on every one of listings/income/population at
  // once. Feeding that narrow band straight into a 0=red/1=green hue scale
  // meant almost every cell landed in the red-to-orange third of the scale,
  // which is why this read as "all squares the same color." Re-stretching
  // the OBSERVED min/max of THIS payload across the full color range (not
  // the theoretical 0..1) is what actually makes weak vs. strong markets
  // visually distinguishable - a relative "strongest area on the current
  // map" comparison, same spirit as the backend's own per-payload
  // normalization, just carried one step further for the part a human eye
  // actually has to be able to tell apart.
  const usCells = cells.filter((cell) => isUSLatLong(Number(cell.lat), Number(cell.lon)));
  // Shared with the state/city bubble coloring below (heatmapColorForState/
  // heatmapColorForCity) so a state bubble's color and a cell's color mean
  // exactly the same position on the same rescaled 0..1 range - "consistent
  // strength story at every zoom level" per the 2026-09-10 ask, not two
  // scales that happen to look similar.
  heatmapScoreSorted = computeHeatmapScoreRange(payload);
  usCells.forEach((cell) => {
    const lat = Number(cell.lat);
    const lon = Number(cell.lon);
    if (!isFinite(lat) || !isFinite(lon)) return;
    const halfLatDeg = halfWidthKm / KM_PER_DEGREE_LAT;
    // Degrees of longitude shrink toward the poles - computed per-cell off
    // that cell's own latitude so every square reads approximately square in
    // real-world km, from the Gulf Coast up to the Canadian border, matching
    // how the backend gridded these cells in the first place.
    const halfLonDeg = halfWidthKm / (KM_PER_DEGREE_LAT * Math.max(0.01, Math.cos(lat * Math.PI / 180)));
    const bounds = [[lat - halfLatDeg, lon - halfLonDeg], [lat + halfLatDeg, lon + halfLonDeg]];
    const color = heatmapScoreColor(rescaleHeatmapScore(Number(cell.score) || 0));
    L.rectangle(bounds, {
      renderer: heatmapCanvasRenderer,
      stroke: false,
      fillColor: color,
      fillOpacity: 0.55,
      interactive: false
    }).addTo(heatmapLayerGroup);
  });
}

async function fetchHeatmapCells() {
  if (heatmapCellsCache) return heatmapCellsCache;
  if (heatmapFetchPromise) return heatmapFetchPromise;
  heatmapFetchPromise = fetch("/api/reporting/heatmap")
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (data && Array.isArray(data.cells)) heatmapCellsCache = data;
      return heatmapCellsCache;
    })
    .catch(() => null)
    .finally(() => { heatmapFetchPromise = null; });
  return heatmapFetchPromise;
}

// Default ON, no toggle button (user-directed, 2026-09-10 - this used to
// be opt-in behind #heatmapToggleBtn; the button and every reference to it
// are gone now, this just shows the layer the first time the map itself is
// ready). Still fetched/built only once and cached, same performance
// approach as before (L.canvas(), non-interactive rectangles) - showing it
// by default doesn't change the cost of building it, only when that cost
// is paid.
let heatmapRetryCount = 0;
const HEATMAP_RETRY_LIMIT = 4;

async function showHeatmapLayerByDefault() {
  if (!reportingMap || !heatmapLayerGroup || heatmapVisible) return;
  const payload = await fetchHeatmapCells();
  if (!payload) {
    // A failed/empty fetch used to be a dead end: heatmapVisible stayed
    // false forever with nothing scheduled to try again, so the layer
    // silently never appeared unless something else (a manual Refresh
    // Report click) happened to call this function a second time. Right
    // after a restart the first attempt can easily land mid-rebuild
    // (silver/gold rebuild takes a few seconds) - that is exactly the
    // transient case worth retrying on its own, same warmup-poll pattern
    // loadReporting() already uses for the rest of the tab.
    if (heatmapRetryCount < HEATMAP_RETRY_LIMIT) {
      heatmapRetryCount += 1;
      window.setTimeout(showHeatmapLayerByDefault, 5000);
    }
    return;
  }
  heatmapRetryCount = 0;
  if (heatmapLayerGroup.getLayers().length === 0) buildHeatmapLayer(payload);
  heatmapVisible = true;
  reportingMap.addLayer(heatmapLayerGroup);
  // The state/city bubbles for the CURRENT render were almost certainly
  // built already (this fetch is async and this is the only place it's
  // triggered) using their pre-heatmap fallback colors - recolor them now
  // that state_scores/city_scores actually exist, in place, without waiting
  // for the next full renderReportingMap() call.
  applyHeatmapScoreColorsToCircleTiers();
}

// The drill-down: nation -> state bubbles, state -> city bubbles, city -> ZIP
// bubbles (BUG-102), ZIP -> individual listings. Only the three AGGREGATE
// layers are zoom-gated; the markers that represent real rows are not.
//
// The listing markers (blue when no primary brand is chosen, green for the
// primary brand, red for competitors) and the whitespace gap ZIPs (orange)
// stay on at every zoom, including the default national view. That is the
// explicit ask - "blue solid should be shown when zooming in as well" - and
// it is also what stops markers from vanishing mid-zoom (BB14). Aggregates
// are a summary of those markers, so they hand over as you zoom in rather
// than replacing them.
function syncMapLayersByZoom() {
  if (!reportingMap) return;
  const currentZoom = reportingMap.getZoom();
  const activeCityFilter = String(el("reportCityFilter")?.value || "").trim();
  const activeZipFilter = String(el("reportZipFilter")?.value || "").trim();
  // Filtering to one city or ZIP means the user is already "there", whatever
  // the zoom reads - summarising a single city/ZIP as one bubble helps nobody.
  const isListingLevel = Boolean(activeCityFilter || activeZipFilter) || currentZoom >= LISTING_TIER_ZOOM_THRESHOLD;
  let tier = isListingLevel
    ? "listing"
    : (currentZoom >= ZIP_TIER_ZOOM_THRESHOLD
        ? "zip"
        : (currentZoom >= CITY_TIER_ZOOM_THRESHOLD ? "city" : "state"));

  // BB14 guard, kept and extended for the new ZIP tier: never hand over to a
  // tier that has nothing in it. The layers are built from different
  // payloads (state bubbles from top_states, city/ZIP bubbles and listing
  // markers from map_records, which the server caps), so a tier can
  // legitimately be empty while the one below it is full. Falling back beats
  // handing the user a blank map.
  if (tier === "listing" && !layerHasContentInView(storeMarkersLayerGroup)) {
    tier = currentZoom >= ZIP_TIER_ZOOM_THRESHOLD ? "zip" : (currentZoom >= CITY_TIER_ZOOM_THRESHOLD ? "city" : "state");
  }
  if (tier === "zip" && !layerHasContentInView(zipCirclesLayerGroup)) {
    tier = currentZoom >= CITY_TIER_ZOOM_THRESHOLD ? "city" : "state";
  }
  if (tier === "city" && !layerHasContentInView(cityCirclesLayerGroup)) {
    tier = "state"; // and if the state bubbles are empty too, there was genuinely nothing to draw
  }

  toggleMapLayer(stateCirclesLayerGroup, tier === "state");
  toggleMapLayer(cityCirclesLayerGroup, tier === "city");
  toggleMapLayer(zipCirclesLayerGroup, tier === "zip");
  // Real bug, 2026-09-10 (user: "show less markers... more UI beautiful"):
  // the section-3 comment above ("INDIVIDUAL STORE & GAP PIN MARKERS: Shown
  // at zoom >= LISTING_TIER_ZOOM_THRESHOLD") documented the INTENT of a
  // tier gate that was never actually wired here - both layers were
  // unconditionally `true` regardless of `tier`, so ~1,000 individual
  // listing pins rendered on top of the state bubbles even at the default
  // national zoom. The state/city/zip drill-down above was already correct;
  // this just makes the listing-level layers respect the same `tier` they
  // were always supposed to.
  toggleMapLayer(storeMarkersLayerGroup, tier === "listing");
  toggleMapLayer(gapMarkersLayerGroup, tier === "listing");

  if (tier === "state") {
    // Zoomed back out to national tier: the sampled payload is the right
    // data source again, and a scope picked up from a bubble click (not the
    // filter dropdown) no longer applies.
    if (!String(el("reportStateFilter")?.value || "").trim()) currentMapScopeState = "";
  } else {
    maybeFetchFullScopeMapData();
  }
}

// Debounced so a rapid pan/zoom inside a state does not fire a request per
// frame - only once movement settles does this check run (called from the
// same zoomend/moveend path as syncMapLayersByZoom).
function maybeFetchFullScopeMapData() {
  if (!reportingMap) return;
  if (scopedMapFetchTimer) clearTimeout(scopedMapFetchTimer);
  scopedMapFetchTimer = setTimeout(() => {
    scopedMapFetchTimer = null;
    if (!reportingMap || reportingMap.getZoom() < SCOPED_MAP_ZOOM_THRESHOLD) return;
    const activeStateFilter = String(el("reportStateFilter")?.value || "").trim().toUpperCase();
    const scopeState = activeStateFilter || currentMapScopeState;
    if (!scopeState) return; // no narrower-than-national area identified yet
    fetchFullScopeMapRecords(scopeState);
  }, SCOPED_MAP_FETCH_DEBOUNCE_MS);
}

// Fetches the FULL (server-capped, not nationally-sampled) listing set for
// one state, so zooming into it shows its real depth instead of the ~1/state
// slice the national round-robin sample hands out. See reportingQueryString
// for the shared filter params this reuses - only `state` and the new
// `map_scope=full` flag are added on top.
async function fetchFullScopeMapRecords(scopeState) {
  const cacheKey = `${scopeState}|${reportingQueryString()}`;
  if (scopedMapRecordsCache.has(cacheKey) || scopedMapFetchInFlight.has(cacheKey)) return;
  scopedMapFetchInFlight.add(cacheKey);
  try {
    const params = new URLSearchParams(reportingQueryString());
    params.set("state", scopeState);
    // Backend contract (see workflow_server.py map_query spec): when a
    // state/county/city/zip filter narrows scope, skip the national
    // round-robin ranking/limit entirely and return that area's full set up
    // to its own (higher) ceiling instead of the 5,000-row national cap.
    params.set("map_scope", "full");
    const response = await fetch(`/api/reporting?${params.toString()}`);
    if (!response.ok) return;
    const result = await response.json();
    const records = result.map_records || [];
    scopedMapRecordsCache.set(cacheKey, records);
    // Only redraw if the user is still looking at this same scope - a slow
    // response landing after the user panned away should not yank the map.
    const activeStateFilter = String(el("reportStateFilter")?.value || "").trim().toUpperCase();
    const stillRelevant = (activeStateFilter || currentMapScopeState) === scopeState
      && reportingMap && reportingMap.getZoom() >= SCOPED_MAP_ZOOM_THRESHOLD;
    if (stillRelevant) {
      renderReportingMap(
        records,
        lastRenderedMapPayload.gapRecords,
        lastRenderedMapPayload.stateRecords,
        lastRenderedMapPayload.filters,
        { fullScope: true, scopeLabel: stateCodeToName[scopeState] || scopeState }
      );
    }
  } catch (_) {
    // Silent - the already-rendered sampled data stays on screen.
  } finally {
    scopedMapFetchInFlight.delete(cacheKey);
  }
}

let mapZoomListenerAttached = false;

function renderReportingMap(mapRecords = [], gapRecords = [], stateRecords = [], filters = {}, opts = {}) {
      if (!el("reportingMap")) return;
      lastRenderedMapPayload = { gapRecords, stateRecords, filters };
      // A fresh national render (not a scoped follow-up fetch) means the
      // scope caches and any narrowed-by-click state no longer necessarily
      // match what is on screen - the filters could have changed underneath
      // them. Clearing here (not on every call) keeps a scoped re-render
      // from wiping its own just-fetched cache entry.
      if (!opts.fullScope) {
        scopedMapRecordsCache.clear();
        if (!String(el("reportStateFilter")?.value || "").trim()) currentMapScopeState = "";
      }
      const displayStates = (stateRecords || []).filter((row) => Number(row.locations || 0) > 0);
      if (!window.L) {
        renderStaticUSMap(displayStates);
        return;
      }
      if (!reportingMap) {
        el("reportingMap").innerHTML = "";
        reportingMap = L.map("reportingMap", {
          zoomSnap: 0.1,
          zoomDelta: 0.5,
          minZoom: 2,
          maxZoom: 18
        }).setView(DEFAULT_US_MAP_VIEW.center, DEFAULT_US_MAP_VIEW.zoom);
        window.reportingMap = reportingMap; // reporting-tabs.js looks up the map via window.reportingMap
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(reportingMap);
        mapMarkerLayerGroup = L.layerGroup().addTo(reportingMap);
        stateBoundaryLayerGroup = L.layerGroup().addTo(reportingMap);
        stateCirclesLayerGroup = L.layerGroup().addTo(reportingMap);
        cityCirclesLayerGroup = L.layerGroup().addTo(reportingMap);
        zipCirclesLayerGroup = L.layerGroup().addTo(reportingMap);
        gapMarkersLayerGroup = L.layerGroup().addTo(reportingMap);
        storeMarkersLayerGroup = L.layerGroup().addTo(reportingMap);
        // Not added to the map yet - showHeatmapLayerByDefault() (below)
        // fetches and attaches it once the map itself is ready. Built once
        // and left attached from then on, never rebuilt.
        heatmapCanvasRenderer = L.canvas({ padding: 0.5 });
        heatmapLayerGroup = L.layerGroup();
      }
      showHeatmapLayerByDefault();
      if (!mapZoomListenerAttached && reportingMap) {
        // moveend as well as zoomend: which tier is worth showing now depends
        // on what is in the current view (layerHasContentInView), so panning
        // from a state with city detail to one without has to re-decide it,
        // exactly as zooming does. Leaflet fires moveend after a programmatic
        // setView too, which is how the state-bubble click lands on the right
        // tier.
        reportingMap.on("zoomend", syncMapLayersByZoom);
        reportingMap.on("moveend", syncMapLayersByZoom);
        mapZoomListenerAttached = true;
      }
      clearMapLayerGroup(mapMarkerLayerGroup);
      clearMapLayerGroup(stateBoundaryLayerGroup);
      clearMapLayerGroup(stateCirclesLayerGroup);
      clearMapLayerGroup(cityCirclesLayerGroup);
      // Rebuilt fresh below - stale entries here would recolor markers that
      // no longer exist if a heatmap fetch resolves after this render.
      stateBubbleRegistry = new Map();
      cityCircleRegistry = new Map();
      clearMapLayerGroup(zipCirclesLayerGroup);
      clearMapLayerGroup(gapMarkersLayerGroup);
      clearMapLayerGroup(storeMarkersLayerGroup);

      const primaryBrand = selectedPrimaryBrand(filters);
      const primaryBrandKey = primaryBrand.toLowerCase();
      // Two collections, because "everything on the map" and "what the user
      // just filtered to" are not the same set. bounds is the whole drawing;
      // focusBounds holds only the things that actually honour a city/ZIP
      // filter - the listing markers and the city bubbles built from them.
      // State centroids and whitespace gap ZIPs are deliberately kept OUT of
      // focusBounds: the gap payload is filtered by state but not by county,
      // city or ZIP, so including it made "filter to one city" fit the whole
      // state and the map never actually drilled in.
      const bounds = [];
      const focusBounds = [];
      const activeStateFilter = String(el("reportStateFilter")?.value || "").toUpperCase();
      const activeCountyFilter = String(el("reportCountyFilter")?.value || "");
      const activeCityFilter = String(el("reportCityFilter")?.value || "");
      const activeZipFilter = String(el("reportZipFilter")?.value || "");
      const shouldFocusFilteredArea = Boolean(activeStateFilter || activeCountyFilter || activeCityFilter || activeZipFilter);
      const boundaryStateCounts = new Map(
        (displayStates || [])
          .filter((row) => stateCentroids[String(row.state || "").toUpperCase()])
          .map((row) => [String(row.state || "").toUpperCase(), Number(row.locations || 0)])
      );

      getUSStatesGeoJSON()
        .then((geojson) => {
          if (!geojson || !stateBoundaryLayerGroup) return;
          clearMapLayerGroup(stateBoundaryLayerGroup);
          L.geoJSON(geojson, {
            style: (feature) => {
              const code = stateNameToCode[feature?.properties?.name] || "";
              const isSelected = activeStateFilter && code === activeStateFilter;
              const hasData = (boundaryStateCounts.get(code) || 0) > 0;
              // Paint the ENTIRE state shape with its strength-decile color
              // (user-directed, 2026-09-10 - "paint entire state on that
              // layer color", not just the small centroid bubble/circle
              // elsewhere on this map). heatmapColorForState() returns null
              // until the heatmap payload has loaded, or if this state
              // resolved no cells at all - the pre-existing blue/gray
              // styling below is the fallback for both cases.
              const heat = typeof heatmapColorForState === "function" ? heatmapColorForState(code) : null;
              if (heat) {
                return {
                  color: isSelected ? "#16a34a" : "#374151",
                  weight: isSelected ? 2.4 : 0.9,
                  fillColor: heat.color,
                  fillOpacity: isSelected ? 0.85 : 0.65
                };
              }
              return {
                color: isSelected ? "#16a34a" : (hasData ? "#2563eb" : "#94a3b8"),
                weight: isSelected ? 2.2 : (hasData ? 1.4 : 0.8),
                fillColor: isSelected ? "#bbf7d0" : (hasData ? "#dbeafe" : "#f8fafc"),
                fillOpacity: isSelected ? 0.32 : (hasData ? 0.22 : 0.08)
              };
            },
            onEachFeature: (feature, layer) => {
              const code = stateNameToCode[feature?.properties?.name] || "";
              if (!code) return;
              const count = boundaryStateCounts.get(code) || 0;
              const fullStateName = feature.properties.name || stateCodeToName[code] || code;

              layer.bindPopup(`
                <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4;">
                  <strong>${escapeHtml(fullStateName)}</strong><br/>
                  <span style="color: ${count > 0 ? '#2563eb' : '#64748b'}; font-weight: 700;">${formatNumber(count)} Listing${count === 1 ? "" : "s"}</span>
                </div>
              `);
            }
          }).addTo(stateBoundaryLayerGroup);
        })
        .catch(() => {});

      // 1. STATE BUBBLES / LABELS: Shown with 2-digit state code at national zoom, hover tooltip shows full state name and listing count
      // Always visible for all states irrespective of whether they have records or not
      const allStateCodes = Object.keys(stateCentroids);
      allStateCodes.forEach((stateCode) => {
        const [lat, lon] = stateCentroids[stateCode];
        const storeCount = boundaryStateCounts.get(stateCode) || 0;
        const stateName = stateCodeToName[stateCode] || stateCode || "Unknown state";
        const hasRecords = storeCount > 0;
        const isSelected = activeStateFilter && stateCode === activeStateFilter;

        if (hasRecords || isSelected) {
          bounds.push([lat, lon]);
        }

        const radius = hasRecords ? Math.max(13, Math.min(26, Math.round(Math.sqrt(storeCount) * 1.5 + 9))) : 12;
        const size = radius * 2;
        // Whitespace-strength score (2026-09-10 ask): color the bubble by
        // the SAME red-green score the square-cell heatmap uses, rolled up
        // to state level server-side (reporting_heatmap()'s state_scores,
        // weighted by zip_count+listing_count - see its docstring). Falls
        // back to the original flat blue/gray styling when no heatmap
        // payload has loaded yet or no cell data resolved to this state
        // (e.g. a state with listings but no coordinate-resolved ZIPs).
        const scored = hasRecords ? heatmapColorForState(stateCode) : null;
        const bubbleBg = scored ? scored.color : (hasRecords ? "#e7f0ff" : "rgba(255,255,255,0.85)");
        const bubbleBorder = scored ? scored.color : (hasRecords ? "#2563eb" : "#cbd5e1");
        const bubbleText = scored ? "#ffffff" : (hasRecords ? "#1e40af" : "#475569");

        const marker = L.marker([lat, lon], {
          icon: buildStateBubbleIcon(stateCode, hasRecords, size, bubbleBg, bubbleBorder, bubbleText)
        });

        // Interactive hover tooltip showing full state name, exact listing
        // count, and (once available) the rolled-up whitespace-strength score.
        marker.bindTooltip(stateBubbleTooltipHtml(stateName, storeCount, hasRecords, scored?.row), {
          permanent: false,
          sticky: true,
          opacity: 0.96,
          offset: [0, -10]
        });

        // Click on state bubble zooms into state at city level. Record the
        // scope so maybeFetchFullScopeMapData() (fired from the resulting
        // zoomend) knows which state's full listing set to fetch - setView
        // alone carries no state identity by the time that handler runs.
        marker.on("click", () => {
          currentMapScopeState = stateCode;
          if (reportingMap) reportingMap.setView([lat, lon], 7);
        });

        stateCirclesLayerGroup.addLayer(marker);
        stateBubbleRegistry.set(stateCode, { marker, hasRecords, size, storeCount, stateName });
      });

      // 2. CITY CIRCLES: Aggregated at city level, shown between CITY_TIER_ZOOM_THRESHOLD and ZIP_TIER_ZOOM_THRESHOLD
      const cityAggregates = new Map();
      mapRecords.forEach((rec) => {
        const lat = parseFloat(rec.latitude);
        const lon = parseFloat(rec.longitude);
        if (!isUSLatLong(lat, lon)) return;
        const cityName = String(rec.city || "").trim();
        const stateCode = String(rec.state || rec.state_name || "").toUpperCase().trim();
        if (!cityName) return;
        const key = `${cityName.toLowerCase()}|${stateCode}`;
        if (!cityAggregates.has(key)) {
          cityAggregates.set(key, {
            city: cityName,
            state: stateCode,
            lats: [],
            lons: [],
            count: 0
          });
        }
        const item = cityAggregates.get(key);
        item.lats.push(lat);
        item.lons.push(lon);
        item.count += 1;
      });

      cityAggregates.forEach((item) => {
        const avgLat = item.lats.reduce((a, b) => a + b, 0) / item.lats.length;
        const avgLon = item.lons.reduce((a, b) => a + b, 0) / item.lons.length;
        bounds.push([avgLat, avgLon]);
        focusBounds.push([avgLat, avgLon]);

        // Whitespace-strength score (2026-09-10 ask), city grain: same
        // reasoning/fallback as the state bubbles above, via
        // reporting_heatmap()'s city_scores.
        const cityScored = heatmapColorForCity(item.city, item.state);
        const cityFill = cityScored ? cityScored.color : "#f3e8ff";
        const cityStroke = cityScored ? cityScored.color : "#7c3aed";

        const cityMarker = L.circleMarker([avgLat, avgLon], {
          radius: Math.max(7, Math.min(22, Math.sqrt(item.count) * 2.2)),
          fillColor: cityFill,
          color: cityStroke,
          weight: 2,
          opacity: 0.92,
          fillOpacity: 0.88
        });

        // Hover tooltip showing city, state, exact listing count, and (once
        // available) the rolled-up whitespace-strength score.
        cityMarker.bindTooltip(cityBubbleTooltipHtml(item.city, item.state, item.count, cityScored?.row), {
          sticky: true,
          opacity: 0.96,
          offset: [0, -8]
        });

        // Click on city bubble zooms into city at street/pin level; keep the
        // state scope so the full-listing fetch stays active while drilling
        // deeper rather than resetting to national.
        cityMarker.on("click", () => {
          if (item.state) currentMapScopeState = item.state;
          if (reportingMap) reportingMap.setView([avgLat, avgLon], 11);
        });

        cityCirclesLayerGroup.addLayer(cityMarker);
        cityCircleRegistry.set(`${item.city.toLowerCase()}|${item.state}`, { marker: cityMarker, city: item.city, state: item.state, count: item.count });
      });

      // 2b. ZIP CIRCLES (BUG-102): Aggregated at ZIP level, shown at zoom
      // ZIP_TIER_ZOOM_THRESHOLD-LISTING_TIER_ZOOM_THRESHOLD, between the city
      // circles and the individual listing pins - same tooltip pattern as
      // the city circles above (hover shows the ZIP, city/state and exact
      // listing count), keyed by zip_code instead of city+state.
      const zipAggregates = new Map();
      mapRecords.forEach((rec) => {
        const lat = parseFloat(rec.latitude);
        const lon = parseFloat(rec.longitude);
        if (!isUSLatLong(lat, lon)) return;
        const zipCode = String(rec.zip_code || "").trim();
        if (!zipCode) return;
        const cityName = String(rec.city || "").trim();
        const stateCode = String(rec.state || rec.state_name || "").toUpperCase().trim();
        if (!zipAggregates.has(zipCode)) {
          zipAggregates.set(zipCode, {
            zip: zipCode,
            city: cityName,
            state: stateCode,
            lats: [],
            lons: [],
            count: 0
          });
        }
        const item = zipAggregates.get(zipCode);
        item.lats.push(lat);
        item.lons.push(lon);
        item.count += 1;
      });

      zipAggregates.forEach((item) => {
        const avgLat = item.lats.reduce((a, b) => a + b, 0) / item.lats.length;
        const avgLon = item.lons.reduce((a, b) => a + b, 0) / item.lons.length;

        const zipMarker = L.circleMarker([avgLat, avgLon], {
          radius: Math.max(6, Math.min(18, Math.sqrt(item.count) * 2)),
          fillColor: "#cffafe",
          color: "#0891b2",
          weight: 2,
          opacity: 0.92,
          fillOpacity: 0.88
        });

        // Hover tooltip showing ZIP, city/state and exact listing count -
        // the same interaction pattern the city circles use above.
        const cityStateLabel = [item.city, item.state].filter(Boolean).join(", ");
        zipMarker.bindTooltip(`
          <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4; padding: 2px 4px;">
            <strong style="color: #0f172a; font-size: 14px;">ZIP ${escapeHtml(item.zip)}</strong>${cityStateLabel ? `<br/><span style="color: #475569;">${escapeHtml(cityStateLabel)}</span>` : ""}<br/>
            <span style="color: #0891b2; font-weight: 700; font-size: 13px;">${formatNumber(item.count)} Listing${item.count === 1 ? "" : "s"}</span>
          </div>
        `, {
          sticky: true,
          opacity: 0.96,
          offset: [0, -8]
        });

        // Click on a ZIP bubble zooms into it at pin level, same pattern as
        // the city bubble click above.
        zipMarker.on("click", () => {
          if (item.state) currentMapScopeState = item.state;
          if (reportingMap) reportingMap.setView([avgLat, avgLon], LISTING_TIER_ZOOM_THRESHOLD + 1);
        });

        zipCirclesLayerGroup.addLayer(zipMarker);
      });

      // 3. INDIVIDUAL STORE & GAP PIN MARKERS: Shown at zoom >= LISTING_TIER_ZOOM_THRESHOLD or when filtered to specific city/zip
      mapRecords.forEach((rec) => {
        const lat = parseFloat(rec.latitude);
        const lon = parseFloat(rec.longitude);
        if (!isUSLatLong(lat, lon)) return; // Discard non-US coordinates
        bounds.push([lat, lon]);
        focusBounds.push([lat, lon]);
        // Position is the source of truth for "is this really a US point,"
        // `country` a secondary tiebreaker only (user-directed) - this
        // dataset has real state/country/coordinate mismatches (a row can
        // carry state="OR" and country="Canada" and a coordinate in New
        // York simultaneously, see the Oregon investigation in codex.md),
        // so trusting `country` alone colored a large fraction of visibly
        // US-positioned points black. `rec.state` is not a raw label - it
        // is the OUTPUT of the geo-enrichment pipeline's coordinate-to-ZIP
        // matching against real US reference data, so a populated state
        // code IS a position-derived signal, stronger than the loose
        // lat/lon bounding box isUSLatLong() uses. Only fall back to the
        // `country` field when no state resolved at all (position gave no
        // answer, so the label is what's left to go on).
        const hasResolvedUsState = Boolean(String(rec.state || "").trim());
        const countryNormalized = String(rec.country || "").trim().toLowerCase();
        const countryLooksNonUs = countryNormalized && !["us", "usa", "united states", "united states of america"].includes(countryNormalized);
        const isNonUs = !hasResolvedUsState && countryLooksNonUs;
        const isPrimary = primaryBrandKey && String(rec.brand || "").toLowerCase() === primaryBrandKey;
        const color = isNonUs ? "#000000" : (primaryBrandKey ? (isPrimary ? "#16a34a" : "#dc2626") : "#3b82f6");
        const stateLabel = rec.state_name || rec.state || "";

        const marker = L.marker([lat, lon], {
          icon: L.divIcon({
            className: "",
            html: `<span class="brand-map-marker" style="display:block; background:${color};"></span>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8],
            popupAnchor: [0, -8]
          }),
          zIndexOffset: 500
        });
        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
            <strong style="color: ${color}; font-size: 14px;">${escapeHtml(rec.name || rec.brand)}</strong><br/>
            <span>${escapeHtml(rec.address || "")}</span><br/>
            <span>${escapeHtml(rec.city || "")}, ${escapeHtml(stateLabel)} ${escapeHtml(rec.zip_code || "")}</span><br/>
            <span style="color: #64748b; font-size: 11px;">🌐 Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}</span><br/>
            ${rec.phone_number ? `<span style="color: #64748b;">📞 ${escapeHtml(rec.phone_number)}</span>` : ""}
          </div>
        `);
        storeMarkersLayerGroup.addLayer(marker);
      });

      gapRecords.forEach((gap) => {
        const lat = parseFloat(gap.latitude);
        const lon = parseFloat(gap.longitude);
        if (!isUSLatLong(lat, lon)) return; // Discard non-US coordinates
        bounds.push([lat, lon]);
        const stateLabel = gap.state_name || gap.state || "";

        const marker = L.circleMarker([lat, lon], {
          radius: 5,
          fillColor: "#f59e0b",
          color: "#ffffff",
          weight: 1.5,
          opacity: 0.9,
          fillOpacity: 0.85
        });
        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
            <strong style="color: #f59e0b; font-size: 14px;">📍 Whitespace Candidate ZIP ${escapeHtml(gap.zip_code)}</strong><br/>
            <span>${escapeHtml(gap.city || "")}, ${escapeHtml(stateLabel)} (${escapeHtml(gap.county || "")})</span><br/>
            <span style="color: #64748b; font-size: 11px;">🌐 Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}</span>
            <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
            <span><strong>Competitors Operating:</strong> ${escapeHtml(formatBrandList(gap.brands_present))} (${gap.competitor_locations} store${gap.competitor_locations > 1 ? "s" : ""})</span><br/>
            <span><strong>Population:</strong> ${formatNumber(gap.population)}</span><br/>
            <span><strong>Median Income:</strong> ${gap.median_household_income ? "$" + formatNumber(gap.median_household_income) : "N/A"}</span><br/>
            <span><strong>Median Age:</strong> ${gap.median_age || "N/A"} yrs</span>
          </div>
        `);
        gapMarkersLayerGroup.addLayer(marker);
      });

      // Say so when the map is only showing a slice (see
      // MAP_RECORD_DISPLAY_CAP). A partial map that looks complete is how
      // "only one area has listings" gets read off a national view.
      const mapNote = el("reportingMapNote");
      if (mapNote) {
        if (opts.fullScope) {
          mapNote.textContent = `Showing the full listing set for ${escapeHtml(opts.scopeLabel || "this area")} (${formatNumber((mapRecords || []).length)} listings), not the national sample.`;
        } else {
          mapNote.textContent = (mapRecords || []).length >= MAP_RECORD_DISPLAY_CAP
            ? `Showing the first ${formatNumber(MAP_RECORD_DISPLAY_CAP)} listings this report returned, not every listing - each marker is one listing, and they are not spread evenly across states. Filter by brand, state or city to map an area in full, or zoom into a state on the map to load its full listing set. The state bubbles above them are counted over all listings.`
            : `Each marker is one listing - the same "Total Listings" count above, not the ZIP-level "Covered Markets" count (several listings can share one ZIP).`;
        }
      }

      syncMapLayersByZoom();

      // A geographic filter means "take me there"; no filter means the whole
      // country, which is also what Reset All lands on once it has cleared
      // the geo controls and reloaded.
      if (shouldFocusFilteredArea && (focusBounds.length || bounds.length)) {
        // Falling back to bounds means the filtered area returned no mappable
        // listing at all (it can: the server caps map_records - see
        // MAP_RECORD_DISPLAY_CAP - so a real state can come back with none of
        // its rows). That leaves a state centroid, a single point, and
        // fitBounds on one point goes straight to maxZoom - hence the lower
        // ceiling there. Zooming to street level on a guessed centroid is
        // worse than showing the state.
        const focused = focusBounds.length > 0;
        reportingMap.fitBounds(focused ? focusBounds : bounds, { padding: [30, 30], maxZoom: focused ? 12 : 7 });
      } else {
        reportingMap.fitBounds(DEFAULT_US_BOUNDS, { padding: [18, 18], maxZoom: DEFAULT_US_MAP_VIEW.zoom });
      }
      setTimeout(() => reportingMap.invalidateSize(), 200);
    }
let brandDropdownsInitialized = false;
function syncReportingFilters(result) {
      const rawBrands = result.filter_options?.brands || [];
      const uniqueBrands = registerBrandMappings(rawBrands);
      if (uniqueBrands.join("|") !== reportingBrands.join("|") || !brandDropdownsInitialized) {
        reportingBrands = uniqueBrands;
        const mainSel = el("reportMainBrandSelect");
        if (mainSel && uniqueBrands.length) {
          const currentCanonical = resolveCanonicalBrand(mainSel.value);
          const currentMain = uniqueBrands.includes(currentCanonical) ? currentCanonical : "";
          mainSel.innerHTML = '<option value="">All Brands</option>' + uniqueBrands.map((b) => `<option value="${escapeHtml(b)}"${b === currentMain ? " selected" : ""}>${escapeHtml(b)}</option>`).join("");
          mainSel.value = currentMain;
        } else if (mainSel) {
          mainSel.innerHTML = '<option value="">All Brands</option>';
        }
        updateCompetitorOptions();
        // Same rule as the geo cascade: the brand list was just rewritten
        // (up to 1,002 of them), so the search has to be pointed at the new
        // options rather than the ones it cached last load.
        refreshReportFilterSearch();
        brandDropdownsInitialized = true;
      }
      loadGeoOptions();
    }
function updateCompetitorOptions() {
      const selectedMain = el("reportMainBrandSelect")?.value || "";
      // Exclude primary brand so same brand data is NEVER shown in competitor choices
      const competitorChoices = selectedMain ? reportingBrands.filter((b) => b !== selectedMain) : [];
      const currentlyChecked = new Set(checkedValues("competitorBrand"));

      // Picking a primary brand used to default to comparing against every
      // other brand automatically - per explicit user request, competitor
      // selection now starts empty and the user opts in to whichever
      // brands they actually want to compare against.
      const defaultCompetitors = competitorChoices.filter((b) => currentlyChecked.has(b));

      // Distinguish "you haven't picked a primary brand yet" from "the data
      // genuinely has no other brands" - the old fixed "No brands available."
      // read like a data problem even when it just meant pick one first.
      const emptyMessage = selectedMain ? "No other brands available." : "Select a primary brand first.";
      renderBrandChecksWithSelectAll("competitorBrandChecks", "competitorBrand", competitorChoices, defaultCompetitors, emptyMessage);
      const checkboxes = document.querySelectorAll("input[name='competitorBrand']");
      checkboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", updateCompetitorDropdownText);
      });
      updateCompetitorDropdownText();
    }
function updateCompetitorDropdownText() {
      const checked = checkedValues("competitorBrand");
      const btnText = el("competitorDropdownBtnText");
      const dropdownButton = el("competitorDropdownBtn");
      if (!btnText) return;
      const mainBrand = el("reportMainBrandSelect")?.value || "";

      if (!mainBrand) {
        btnText.textContent = "Select Primary Brand First";
        btnText.title = "Select a primary brand first";
        if (dropdownButton) { dropdownButton.removeAttribute("title"); dropdownButton.dataset.tooltip = "Select a primary brand first"; dropdownButton.setAttribute("aria-label", "Select a primary brand first"); }
      } else if (checked.length === 0) {
        btnText.textContent = "Select Competitor Brands (0 selected)";
        btnText.title = "No competitors selected";
        if (dropdownButton) { dropdownButton.removeAttribute("title"); dropdownButton.dataset.tooltip = "No competitors selected"; dropdownButton.setAttribute("aria-label", "No competitors selected"); }
      } else {
        const selectedLabel = checked.join(" ~ ");
        btnText.textContent = selectedLabel;
        btnText.title = selectedLabel;
        if (dropdownButton) { dropdownButton.removeAttribute("title"); dropdownButton.dataset.tooltip = selectedLabel; dropdownButton.setAttribute("aria-label", selectedLabel); }
      }
    const exportButton = el("downloadSampleCsvBtn");
    if (exportButton) exportButton.classList.toggle("hidden", !mainBrand);
}
function setupBrandDropdownListeners() {
      const mainSel = el("reportMainBrandSelect");
      if (mainSel) {
        mainSel.addEventListener("change", () => {
          updateCompetitorOptions();
        });
      }
      const dropdownBtn = el("competitorDropdownBtn");
      const dropdownMenu = el("competitorDropdownMenu");
      if (dropdownBtn && dropdownMenu) {
        // Closing this menu is what releases the competitor ticks auto-apply
        // held back while it was open (see setupReportAutoApply), so both
        // ways of closing it have to say so - hence the open/closed state is
        // read out rather than just toggled.
        dropdownBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const opening = dropdownMenu.style.display !== "block";
          dropdownMenu.style.display = opening ? "block" : "none";
          if (!opening) reportAutoApply?.resume();
        });
        document.addEventListener("click", (e) => {
          if (!e.target.closest("#competitorDropdownContainer")) {
            const wasOpen = dropdownMenu.style.display === "block";
            dropdownMenu.style.display = "none";
            if (wasOpen) reportAutoApply?.resume();
          }
        });
      }
      setupBrandComparisonViewSwitcher();
    }

// Mounts the shared auto-apply switch on the Location Intelligence rail and
// wires the filters that need nothing more than "changed, reload". The
// geographic ones are deliberately absent: they live in integrations.html
// because changing a state also has to repopulate county/city/ZIP, which
// must happen whether auto-apply is on or off - only their reload is handed
// back here via reportAutoApply.schedule().
function setupReportAutoApply() {
  reportAutoApply = attachAutoApplyToggle("reportAutoApplyHost", {
    id: "reportAutoApplyToggle",
    title: "Run the report automatically whenever a filter changes. Turn it off to set several filters first, then use Apply All Filters.",
    watchIds: ["reportMainBrandSelect", "reportMinPopFilter", "reportMinIncomeFilter", "reportMaxAgeFilter"],
    // Competitor brands are ticked inside an open dropdown, and a reload
    // rebuilds that very list (syncReportingFilters -> updateCompetitorOptions
    // re-renders #competitorBrandChecks), throwing away the brand search the
    // user typed and moving the rows under their cursor mid-selection. Hold
    // the reload until the dropdown closes - which is the same call the
    // manual Apply button already makes before it runs.
    shouldDefer: () => el("competitorDropdownMenu")?.style.display === "block",
    onApply: () => {
      reportLoaded = false;
      loadReporting({ interactive: true });
    }
  });
  const competitorChecks = el("competitorBrandChecks");
  if (competitorChecks) {
    // Delegated to the container rather than bound to the checkboxes:
    // updateCompetitorOptions() replaces its contents on every report load,
    // so per-checkbox listeners would be discarded with them. The container
    // element itself survives.
    competitorChecks.addEventListener("change", (event) => {
      // The brand search box sits in the same container and fires change on
      // blur; it only hides rows, it is not a filter on the report.
      const changedName = event.target?.name || "";
      if (changedName === "competitorBrand" || changedName === "competitorBrand_selectAll") reportAutoApply?.schedule();
    });
    competitorChecks.addEventListener("click", (event) => {
      // All / None move the checkboxes in code, which fires no change event.
      if (event.target?.closest?.("[data-action='select-all'],[data-action='deselect-all']")) reportAutoApply?.schedule();
    });
  }
}

let activeBrandComparisonView = "benchmark";

function getBrandFallbackSvg(name) {
  const clean = String(name || "").trim();
  const initials = clean.split(/[\s_\-]+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase() || "B";
  let hash = 0;
  for (let i = 0; i < clean.length; i++) {
    hash = clean.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ["#2563eb", "#7c3aed", "#db2777", "#ea580c", "#0d9488", "#4f46e5", "#0891b2", "#16a34a", "#dc2626"];
  const color = colors[Math.abs(hash) % colors.length];
  return `<svg viewBox="0 0 32 32" width="22" height="22" style="display:inline-block;vertical-align:middle;"><rect width="32" height="32" rx="6" fill="${color}"/><text x="16" y="21" font-family="system-ui,sans-serif" font-weight="750" font-size="13" fill="#ffffff" text-anchor="middle">${escapeHtml(initials)}</text></svg>`;
}

function getBrandLogoSvg(brandName) {
  const name = String(brandName || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  if (name.includes("pizzahut")) {
    return `<svg viewBox="0 0 32 32" width="22" height="22" style="display:inline-block;vertical-align:middle;"><path d="M16 4C10 4 4.5 7.2 2 9.5l2 3c1.5-1.5 6-3.8 12-3.8s10.5 2.3 12 3.8l2-3C27.5 7.2 22 4 16 4z" fill="#ee1c25"/><path d="M5 14l1.5 10c.2 1.5 1.5 2.5 3 2.5h13c1.5 0 2.8-1 3-2.5L27 14H5z" fill="#ee1c25"/><path d="M8 18h16v2.5H8z" fill="#ffc600"/></svg>`;
  }
  if (name.includes("domino")) {
    return `<svg viewBox="0 0 32 32" width="22" height="22" style="display:inline-block;vertical-align:middle;"><g transform="rotate(45 16 16)"><rect x="7" y="6" width="18" height="9" rx="2" fill="#e31837"/><rect x="7" y="17" width="18" height="9" rx="2" fill="#006491"/><circle cx="16" cy="10.5" r="2" fill="#ffffff"/><circle cx="11.5" cy="21.5" r="2" fill="#ffffff"/><circle cx="20.5" cy="21.5" r="2" fill="#ffffff"/></g></svg>`;
  }
  if (name.includes("huntbrother") || name.includes("huntbros")) {
    return `<svg viewBox="0 0 34 20" width="26" height="16" style="display:inline-block;vertical-align:middle;border-radius:2px;"><rect width="34" height="20" rx="3" fill="#1b6b37"/><rect x="2" y="2" width="30" height="16" rx="2" fill="#ffffff"/><rect x="3" y="3" width="28" height="14" rx="1.5" fill="#c41224"/><text x="17" y="9.5" font-family="-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-weight="900" font-size="5" fill="#ffffff" text-anchor="middle" letter-spacing="0.2px">HUNT</text><text x="17" y="14.5" font-family="-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-weight="900" font-size="3.8" fill="#ffffff" text-anchor="middle" letter-spacing="0.2px">BROTHERS</text></svg>`;
  }
  if (name.includes("papajohn")) {
    return `<svg viewBox="0 0 32 22" width="24" height="16" style="display:inline-block;vertical-align:middle;border-radius:2px;"><rect width="32" height="22" rx="3" fill="#006b3f"/><rect x="2" y="2" width="28" height="18" rx="2" fill="#ffffff"/><text x="16" y="10" font-family="-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-weight="900" font-size="5.5" fill="#c41224" text-anchor="middle">PAPA</text><text x="16" y="17" font-family="-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-weight="900" font-size="5" fill="#006b3f" text-anchor="middle">JOHNS</text></svg>`;
  }
  if (name.includes("marco")) {
    return `<svg viewBox="0 0 32 32" width="22" height="22" style="display:inline-block;vertical-align:middle;"><circle cx="16" cy="16" r="15" fill="#d9241b"/><circle cx="16" cy="16" r="12" fill="#ffbe00"/><path d="M10 21V11l6 6 6-6v10h-3v-5.5l-3 3-3-3V21z" fill="#d9241b"/></svg>`;
  }
  if (name.includes("papamurphy")) {
    return `<svg viewBox="0 0 32 22" width="24" height="16" style="display:inline-block;vertical-align:middle;border-radius:2px;"><rect width="32" height="22" rx="3" fill="#b91c1c"/><rect x="2" y="2" width="28" height="18" rx="2" fill="#15803d"/><text x="16" y="10" font-family="Georgia,serif" font-weight="bold" font-size="4.5" fill="#ffffff" text-anchor="middle">Papa</text><text x="16" y="17" font-family="Georgia,serif" font-weight="bold" font-size="5" fill="#ffffff" text-anchor="middle">Murphy's</text></svg>`;
  }
  if (name.includes("littlecaesar")) {
    return `<svg viewBox="0 0 32 32" width="22" height="22" style="display:inline-block;vertical-align:middle;"><circle cx="16" cy="16" r="15" fill="#f97316"/><path d="M11 11c0-2.2 2-3.5 5-3.5s5 1.3 5 3.5l-1 5H12l-1-5z" fill="#ffffff"/><path d="M9 18h14l-2.5 8h-9L9 18z" fill="#ffffff"/></svg>`;
  }
  return getBrandFallbackSvg(brandName);
}

function formatMetricDiff(diff, unit, primaryBrandName) {
  if (!diff && diff !== 0) return "";
  if (diff === 0) return `Same as ${escapeHtml(primaryBrandName)}`;
  const sign = diff > 0 ? "+" : "-";
  const absDiff = formatNumber(Math.abs(diff));
  return `${sign}${absDiff} <em>${unit}</em> than ${escapeHtml(primaryBrandName)}`;
}

function setupBrandComparisonViewSwitcher() {
  const switcher = el("competitorViewSwitcher");
  if (!switcher || switcher.dataset.initialized === "true") return;
  switcher.dataset.initialized = "true";

  switcher.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-comp-view]");
    if (!btn) return;
    setBrandComparisonView(btn.dataset.compView);
  });
}

function setBrandComparisonView(viewName) {
  activeBrandComparisonView = viewName;
  const switcher = el("competitorViewSwitcher");
  if (switcher) {
    switcher.querySelectorAll("[data-comp-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.compView === viewName);
    });
  }
  if (el("reportCompetitorBenchmarkView")) {
    el("reportCompetitorBenchmarkView").classList.toggle("hidden", viewName !== "benchmark");
  }
  if (el("reportBrandComparisonCardsView")) {
    el("reportBrandComparisonCardsView").classList.toggle("hidden", viewName !== "cards");
  }
  if (el("reportBrandComparisonTableView")) {
    el("reportBrandComparisonTableView").classList.toggle("hidden", viewName !== "table");
  }
}

function renderCompetitorBenchmarkView(primaryRow, competitorRows, totals = {}, hasPrimarySelected = false) {
  const container = el("reportCompetitorBenchmarkContent");
  if (!container) return;

  if (!hasPrimarySelected || !primaryRow) {
    // When no primary brand selected, render a single row showing active store, state, and city metrics
    container.innerHTML = `
      <div class="comp-bench-table-wrap">
        <table class="comp-bench-table">
          <thead>
            <tr>
              <th class="brand-col">Brand</th>
              <th class="loc-col">Number of locations</th>
              <th class="state-col">Number of States</th>
              <th class="city-col">Number of cities</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <div class="comp-bench-brand-cell">
                  <div class="comp-brand-row comp-brand-primary">
                    <span class="comp-logo-icon" title="All Active Brands">${getBrandLogoSvg("All Active Brands")}</span>
                    <span class="comp-primary-name" style="font-weight: 700; color: var(--ink);">All Active Brands</span>
                  </div>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber((totals.total_listings ?? totals.total_stores) || totals.active_market_locations || 0)}</span>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber(totals.active_brand_states || totals.total_states || 0)}</span>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber(totals.active_brand_cities || totals.total_cities || 0)}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="comp-sales-footer" style="color: var(--muted); font-size: 12px; margin-top: 10px;">
        Select a primary brand from the filter sidebar on the left to benchmark head-to-head against competitors.
      </p>
    `;
    return;
  }

  const primaryName = primaryRow.brand;
  const primaryLogo = getBrandLogoSvg(primaryName);

  if (!competitorRows || !competitorRows.length) {
    // Primary brand selected, but no competitors chosen
    container.innerHTML = `
      <div class="comp-bench-table-wrap">
        <table class="comp-bench-table">
          <thead>
            <tr>
              <th class="brand-col">Brand</th>
              <th class="loc-col">Number of locations</th>
              <th class="state-col">Number of States</th>
              <th class="city-col">Number of cities</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <div class="comp-bench-brand-cell">
                  <div class="comp-brand-row comp-brand-primary">
                    <span class="comp-logo-icon" title="${escapeHtml(primaryName)}">${primaryLogo}</span>
                    <span class="comp-primary-name" style="font-weight: 700; color: var(--ink);">${escapeHtml(primaryName)}</span>
                  </div>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber(primaryRow.locations)}</span>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber(primaryRow.states)}</span>
                </div>
              </td>
              <td>
                <div class="comp-metric-cell">
                  <span class="comp-metric-num">${formatNumber(primaryRow.cities)}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="comp-sales-footer" style="color: var(--muted); font-size: 12px; margin-top: 10px;">
        Select competitor brands from the filter sidebar on the left to see comparisons against ${escapeHtml(primaryName)}.
      </p>
    `;
    return;
  }

  const rowsHtml = competitorRows.map((comp) => {
    const compName = comp.brand;
    const compLogo = getBrandLogoSvg(compName);
    const locDiff = comp.locations - primaryRow.locations;
    const stateDiff = comp.states - primaryRow.states;
    const cityDiff = comp.cities - primaryRow.cities;

    return `
      <tr>
        <td>
          <div class="comp-bench-brand-cell">
            <div class="comp-brand-row comp-brand-primary">
              <span class="comp-logo-icon" title="${escapeHtml(primaryName)}">${primaryLogo}</span>
              <span class="comp-primary-name" title="${escapeHtml(primaryName)}">${escapeHtml(primaryName)}</span>
            </div>
            <div class="comp-brand-row comp-brand-vs">
              <span class="comp-vs-badge">VS</span>
              <span class="comp-logo-icon" title="${escapeHtml(compName)}">${compLogo}</span>
              <a href="#" class="comp-link-name" data-competitor-brand="${escapeHtml(compName)}" title="${escapeHtml(compName)} - click to focus">${escapeHtml(compName)}</a>
            </div>
          </div>
        </td>
        <td>
          <div class="comp-metric-cell">
            <span class="comp-metric-num">${formatNumber(comp.locations)}</span>
            <span class="comp-metric-diff">(${formatMetricDiff(locDiff, "locations", primaryName)})</span>
          </div>
        </td>
        <td>
          <div class="comp-metric-cell">
            <span class="comp-metric-num">${formatNumber(comp.states)}</span>
            <span class="comp-metric-diff">(${stateDiff === 0 ? `Same as ${escapeHtml(primaryName)}` : formatMetricDiff(stateDiff, "states", primaryName)})</span>
          </div>
        </td>
        <td>
          <div class="comp-metric-cell">
            <span class="comp-metric-num">${formatNumber(comp.cities)}</span>
            <span class="comp-metric-diff">(${formatMetricDiff(cityDiff, "cities", primaryName)})</span>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  container.innerHTML = `
    <div class="comp-bench-table-wrap">
      <table class="comp-bench-table">
        <thead>
          <tr>
            <th class="brand-col"></th>
            <th class="loc-col">Number of locations</th>
            <th class="state-col">Number of States</th>
            <th class="city-col">Number of cities</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
    <p class="comp-sales-footer">
      If you would like to get a detailed report comparing ${escapeHtml(primaryName)} with any other company, please <a href="mailto:sales@birdeye.com?subject=Detailed%20Report%20Comparison%20for%20${encodeURIComponent(primaryName)}">contact our sales team</a>
    </p>
  `;

  container.querySelectorAll(".comp-link-name").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      const targetBrand = link.dataset.competitorBrand;
      if (!targetBrand) return;
      const mainSel = el("reportMainBrandSelect");
      if (mainSel && [...mainSel.options].some((opt) => opt.value === targetBrand)) {
        mainSel.value = targetBrand;
        updateCompetitorOptions();
        loadReporting();
      }
    });
  });
}
// ---------------------------------------------------------------------------
// Geographic filters - ONE implementation, used by BOTH reporting tabs
// ---------------------------------------------------------------------------
// Location Intelligence and Data Quality show the same four cascading
// geographic controls (State -> County -> City -> ZIP), so the loader, the
// cascade and the ZIP typeahead live here once and are parameterised by
// element id. The two tabs previously carried separate filter code and
// drifted apart - tab 2 was left with a lone State select while tab 1
// cascaded all four - which is what the user kept reporting ("geo filters on
// tab 2 aren't same as tab 1"). A second copy is the failure mode, not the
// fix: any behaviour added below is on both tabs the moment it is written.
//
// A rail descriptor names controls, nothing more:
//   state/county/city  the selects this rail reads the current selection FROM
//                      and rebuilds from /api/geo/options
//   zip / zipList      the ZIP input and the <datalist> its server-side
//                      suggestions are written into
//   ownsStateOptions   false when the tab supplies its own State list (Data
//                      Quality lists only states that actually have issues,
//                      from /api/reporting/quality) - the cascade still READS
//                      that select, it just must not overwrite what the tab
//                      put in it
//   onOptionsRebuilt   re-points that rail's search component at the options
//                      just written, since each rail attaches the shared
//                      search component to its own list of control ids
const REPORT_GEO_RAIL = {
  state: "reportStateFilter",
  county: "reportCountyFilter",
  city: "reportCityFilter",
  zip: "reportZipFilter",
  zipList: "zipSuggestions",
  ownsStateOptions: true,
  onOptionsRebuilt: () => refreshReportFilterSearch(),
};

async function loadGeoOptions(rail = REPORT_GEO_RAIL) {
      const state = el(rail.state)?.value || "";
      const county = el(rail.county)?.value || "";
      try {
        const response = await fetch(`/api/geo/options?state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}`);
        const data = await response.json();
        if (!response.ok) return;

        const stateSel = rail.ownsStateOptions === false ? null : el(rail.state);
        if (stateSel && stateSel.options.length <= 1 && data.states?.length) {
          const current = stateSel.value;
          stateSel.innerHTML = '<option value="">All States</option>' + data.states.map((st) => {
            const code = typeof st === "string" ? st : st.code;
            const name = typeof st === "string" ? st : (st.name || st.code);
            return `<option value="${escapeHtml(code)}">${escapeHtml(name)}</option>`;
          }).join("");
          stateSel.value = current;
        }

        const countySel = el(rail.county);
        if (countySel) {
          const currentCounty = countySel.value;
          const countyList = data.counties || [];
          countySel.innerHTML = '<option value="">All Counties</option>' + countyList.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
          countySel.value = countyList.includes(currentCounty) ? currentCounty : "";
        }

        const citySel = el(rail.city);
        if (citySel) {
          const currentCity = citySel.value;
          const cityList = data.cities || [];
          citySel.innerHTML = '<option value="">All Cities</option>' + cityList.map((ct) => `<option value="${escapeHtml(ct)}">${escapeHtml(ct)}</option>`).join("");
          citySel.value = cityList.includes(currentCity) ? currentCity : "";
        }
        // State/county/city were just rewritten from the server response, so
        // the search component has to re-read them here or it keeps offering
        // the previous state's counties. Each rail re-attaches its own
        // controls - hence the hook rather than a hard-coded call.
        (rail.onOptionsRebuilt || refreshReportFilterSearch)();
      } catch (err) {}
    }

// Every long <select> on the Location rail, searched by the SAME component
// as the brand pickers (attachSearchableSelect, common.js). This replaced a
// second, parallel search implementation that lived here - it had no
// suggestion panel, no open-on-focus, no re-homing, and a "Type 2+ letters
// to search counties" placeholder explaining a minimum length that a
// client-side filter over already-fetched options has no reason to have.
// The Data Quality rail calls the same component on its own selects
// (reporting-tabs.js), so both tabs search the same way.
const REPORT_SEARCHABLE_FILTERS = ["reportMainBrandSelect", "reportStateFilter", "reportCountyFilter", "reportCityFilter"];

// MUST be called immediately after anything rebuilds one of these selects.
// attachSearchableSelect caches the option list, and re-reads it from the
// select on every call - so a rebuild that is not followed by a re-attach
// leaves the search filtering a list that no longer matches the control
// (BB9/BB10: a newly created brand was invisible to the search because the
// cache predated it). threshold 15 keeps the chrome off short lists - a
// three-county dropdown does not need a search box - and minChars 1 matches
// the brand pickers in mapper.js.
function refreshReportFilterSearch() {
  if (typeof attachSearchableSelect !== "function") return;
  REPORT_SEARCHABLE_FILTERS.forEach((selectId) => attachSearchableSelect(selectId, { threshold: 15, minChars: 1 }));
}

// "Reset All" has to clear the rail's search boxes too: a search box still
// holding text over a select showing only its matches is a filter the user
// just asked to be rid of. Takes any node in the rail so each tab clears its
// own - shared with the Data Quality rail's Reset All (reporting-tabs.js).
function clearReportFilterSearch(nodeInRail) {
  const rail = nodeInRail?.closest?.(".report-filter-rail");
  if (!rail) return;
  rail.querySelectorAll('input[type="search"]').forEach((input) => {
    input.value = "";
    // Re-expands the select this input had narrowed: attachSearchableSelect
    // assigns oninput as a property, and it rebuilds the control from the
    // cached full list whenever the query is empty.
    if (typeof input.oninput === "function") input.oninput();
  });
}
// The one control on either rail that is NOT a searchable select: 30k+ ZIPs
// are never all in the page, so this queries /api/zips/search as the user
// types and writes the matches into that rail's own <datalist>. Same function
// for both tabs, driven by the rail descriptor - the Data Quality tab gets
// this behaviour by passing its ids, not by getting a second copy of it.
function setupZipTypeahead(rail = REPORT_GEO_RAIL) {
      const zipInput = el(rail.zip);
      const datalist = el(rail.zipList);
      if (!zipInput || !datalist) return;

      // Debounce timer and request id are per rail (closure state) rather
      // than module-level, now that two rails run this same function: shared
      // state would let a keystroke on one rail cancel the other rail's
      // in-flight request and silently drop its suggestions.
      let typeaheadTimer = null;
      let latestRequestId = 0;

      zipInput.addEventListener("input", () => {
        clearTimeout(typeaheadTimer);
        const query = zipInput.value.trim();
        const requestId = ++latestRequestId;
        if (!query) {
          datalist.innerHTML = "";
          return;
        }
        typeaheadTimer = setTimeout(async () => {
          // Scoped by whatever this rail's cascade has already narrowed to,
          // so ZIP is the last step of the same State -> County -> City chain
          // rather than a free-floating search over the whole country.
          const state = el(rail.state)?.value || "";
          const county = el(rail.county)?.value || "";
          const city = el(rail.city)?.value || "";
          try {
            const resp = await fetch(`/api/zips/search?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}&city=${encodeURIComponent(city)}`);
            const data = await resp.json();
            if (requestId !== latestRequestId) return;
            if (resp.ok && data.zips) {
              datalist.innerHTML = data.zips.map((z) => `<option value="${escapeHtml(z.zip_code)}">${escapeHtml(z.zip_code)} - ${escapeHtml(z.city_name)}, ${escapeHtml(z.state_name || stateCodeToName[z.state_code] || "")} (Pop: ${formatNumber(z.population)})</option>`).join("");
            }
          } catch (e) {}
        }, 250);
      });
    }
    function reportingQueryString() {
      const params = new URLSearchParams();
      const mainBrand = el("reportMainBrandSelect")?.value || "";
      const competitorBrands = checkedValues("competitorBrand").filter((b) => b !== mainBrand);
      if (mainBrand) {
        const rawMain = getRawVariantsForBrand(mainBrand);
        params.set("main_brands", rawMain.join(","));
      }
      if (competitorBrands.length) {
        const rawComps = competitorBrands.flatMap((b) => getRawVariantsForBrand(b));
        params.set("competitor_brands", Array.from(new Set(rawComps)).join(","));
      }
      [
        ["state", "reportStateFilter"],
        ["county", "reportCountyFilter"],
        ["city", "reportCityFilter"],
        ["zip", "reportZipFilter"],
        ["min_population", "reportMinPopFilter"],
        ["min_income", "reportMinIncomeFilter"],
        ["max_median_age", "reportMaxAgeFilter"]
      ].forEach(([key, id]) => {
        const inputEl = el(id);
        if (inputEl && inputEl.value.trim()) params.set(key, inputEl.value.trim());
      });
      return params.toString();
    }

let currentMarketGaps = [];
let currentGapsPage = 1;
const GAPS_PER_PAGE = 10;

function renderMarketGapsWithPagination(gaps = [], page = 1) {
  currentMarketGaps = gaps || [];
  const totalRows = currentMarketGaps.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / GAPS_PER_PAGE));
  currentGapsPage = Math.min(Math.max(1, page), totalPages);

  const startIdx = (currentGapsPage - 1) * GAPS_PER_PAGE;
  const endIdx = Math.min(startIdx + GAPS_PER_PAGE, totalRows);
  const currentSlice = currentMarketGaps.slice(startIdx, endIdx);

  renderSimpleTable("reportGapsTable", [
    { key: "state_name", label: "State" },
    { key: "county", label: "County" },
    { key: "city", label: "City" },
    { key: "zip_code", label: "ZIP Code" },
    { key: "competitor_locations", label: "Competitor Listings", format: formatNumber },
    { key: "brands_present", label: "Competitor Brands", format: formatBrandList },
    { key: "population", label: "Census Population", format: (v) => (v ? formatNumber(v) : "N/A") },
    { key: "median_household_income", label: "Median Income", format: (v) => (v ? "$" + formatNumber(v) : "N/A") },
    { key: "median_age", label: "Median Age", format: (v) => (v ? v + " yrs" : "N/A") }
  ], currentSlice);

  const paginationContainer = el("reportGapsPagination");
  if (!paginationContainer) return;

  if (totalRows === 0) {
    paginationContainer.innerHTML = '<div style="color: var(--muted); font-size: 12px; text-align: center; padding: 6px;">No whitespace gaps found for the current filter criteria.</div>';
    return;
  }

  if (totalRows <= GAPS_PER_PAGE) {
    paginationContainer.innerHTML = `<div style="color: var(--muted); font-size: 12px; text-align: right; padding: 4px;">Showing all ${formatNumber(totalRows)} market gaps</div>`;
    return;
  }

  paginationContainer.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 4px; font-size: 12px; color: var(--muted); border-top: 1px solid var(--line); margin-top: 8px;">
      <div>
        Showing <strong>${startIdx + 1}</strong> &ndash; <strong>${endIdx}</strong> of <strong>${formatNumber(totalRows)}</strong> market gaps
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <button type="button" id="gapsPrevBtn" class="secondary" style="padding: 4px 10px; font-size: 11px; cursor: pointer; border-radius: 4px;" ${currentGapsPage <= 1 ? "disabled" : ""}>&larr; Prev</button>
        <span style="font-weight: 600; color: var(--ink);">Page ${currentGapsPage} of ${totalPages}</span>
        <button type="button" id="gapsNextBtn" class="secondary" style="padding: 4px 10px; font-size: 11px; cursor: pointer; border-radius: 4px;" ${currentGapsPage >= totalPages ? "disabled" : ""}>Next &rarr;</button>
      </div>
    </div>
  `;

  const prevBtn = el("gapsPrevBtn");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => renderMarketGapsWithPagination(currentMarketGaps, currentGapsPage - 1));
  }
  const nextBtn = el("gapsNextBtn");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => renderMarketGapsWithPagination(currentMarketGaps, currentGapsPage + 1));
  }
}

let currentSampleRecords = [];

function setupSampleRecordsDownload() {
  const btn = el("downloadSampleCsvBtn");
  if (!btn || btn.dataset.initialized === "true") return;
  btn.dataset.initialized = "true";

  btn.addEventListener("click", async () => {
    const icon = el("downloadSampleCsvIcon");
    const text = el("downloadSampleCsvText");

    // Guard: already in loading state
    if (btn.classList.contains("loading")) return;

    // Show red loading state
    btn.classList.add("loading");
    btn.disabled = true;
    if (icon) icon.textContent = "⏳";
    if (text) text.textContent = "Preparing Excel";

    try {
      const queryString = reportingQueryString();
      const url = `/api/reporting/export-excel${queryString ? `?${queryString}` : ""}`;
      const response = await fetch(url);
      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || `Export failed (${response.status})`);
      }

      // Derive filename from Content-Disposition header or fallback
      let filename = "whitespace_locations.xlsx";
      const cd = response.headers.get("Content-Disposition");
      if (cd) {
        const match = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';\r\n]+)["']?/i);
        if (match) filename = decodeURIComponent(match[1].trim());
      }

      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);

      // Flip to green "ready" state
      btn.classList.remove("loading");
      btn.classList.add("ready");
      if (icon) icon.textContent = "✅";
      if (text) text.textContent = "Excel Download is Ready";

      // Reset button after 4 s
      setTimeout(() => {
        btn.classList.remove("ready");
        btn.disabled = false;
        if (icon) icon.textContent = "📥";
        if (text) text.textContent = "Download Excel";
      }, 4000);

    } catch (err) {
      btn.classList.remove("loading");
      btn.disabled = false;
      if (icon) icon.textContent = "📥";
      if (text) text.textContent = "Download Excel";
      showAppNotice(productSafeError(err.message, "Excel export failed."), "Export failed", "error");
    }
  });
}

async function loadReporting({ interactive = false } = {}) {
      const status = el("reportStatus");
      const refreshBtn = el("refreshReportBtn");
      const applyBtn = el("applyReportFiltersBtn");
      startEnrichmentStatusPolling();
      const previousRefreshBtn = interactive ? setButtonBusy(refreshBtn, "Refreshing Reports") : "";
      const previousApplyBtn = interactive && applyBtn ? setButtonBusy(applyBtn, "Applying Filters") : "";
      if (interactive) {
        status.className = "report-status loading";
        status.innerHTML = '<span class="spinner"></span> Refreshing report';
      } else {
        status.classList.add("hidden");
      }
      // Only blank the screen when there is nothing on it yet. This ran
      // unconditionally, BEFORE the fetch, on every loadReporting() - so the
      // 5-minute auto-refresh reset every count to 0 (including "50 states",
      // which is a global constant and can never legitimately be 0) and left
      // it that way until the response landed. Reported as "auto refresh
      // removed all data which was good".
      if (!reportHasRenderedOnce) renderEmptyReportingStructure();
      try {
        const queryString = reportingQueryString();
        const response = await fetch(`/api/reporting${queryString ? `?${queryString}` : ""}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load reporting data.");
        syncReportingFilters(result);
        const totals = result.totals || {};
        const hasBusinessData = reportHasBusinessData(totals);
        // Revealing #reportContent before knowing whether there IS data laid
        // out the whole empty skeleton - every section reserving its height
        // with nothing in it - so the "Preparing reporting data" line sat
        // above a screen of blank space. Keep it hidden until there is
        // something to put in it.
        const preparing = Boolean(result.refreshing) && !hasBusinessData;
        el("reportContent").classList.toggle("hidden", preparing);
        if (result.warning && !result.refreshing) {
          status.className = "report-status";
          status.textContent = result.warning;
        } else if (preparing) {
          if (reportingWarmupPolls >= REPORTING_WARMUP_POLL_LIMIT) {
            // Budget spent and still nothing. Saying so once beats a spinner
            // that implies work is progressing when it has stopped.
            status.className = "report-status";
            status.textContent = "Reporting data is taking longer than usual to prepare. Use Refresh Report to try again.";
          } else {
            status.className = "report-status loading";
            // No trailing ellipsis - the spinner already says it is working.
            status.innerHTML = '<span class="spinner"></span> Preparing reporting data';
            scheduleReportingWarmupPoll(3000);
          }
        } else if (interactive && result.refreshing) {
          // The Refresh Report button itself already shows "Refreshing
          // Reports" with a spinner while this is in flight - no need for a
          // second, redundant status line saying the same thing.
          status.classList.add("hidden");
          scheduleReportingWarmupPoll(10000);
        } else {
          status.classList.add("hidden");
          // Settled with real data: the next warm-up cycle starts from a
          // clean budget rather than inheriting this one's spent attempts.
          if (hasBusinessData) reportingWarmupPolls = 0;
          if (reportingWarmupTimer && hasBusinessData) {
            clearTimeout(reportingWarmupTimer);
            reportingWarmupTimer = null;
          }
        }

        // Correct real metrics mapping
        el("reportLocations").textContent = formatNumber(totals.active_market_locations || 0);
        el("reportBrands").textContent = formatNumber(totals.total_brands || 0);
        // The US reporting view includes states and territories, but the KPI
        // must never exceed the 50-state US ceiling.
        el("reportStates").textContent = formatNumber(Math.min(50, Number(totals.total_states || 0)));
        el("reportCities").textContent = formatNumber(totals.active_brand_cities != null ? totals.active_brand_cities : (totals.total_cities || 0));
        if (el("reportZips")) el("reportZips").textContent = formatNumber(totals.total_zips || 0);
        if (el("reportStores")) el("reportStores").textContent = formatNumber((totals.total_listings ?? totals.total_stores) || 0);
        if (el("reportBrandStates")) el("reportBrandStates").textContent = formatNumber(totals.active_brand_states || 0);
        if (el("reportWhitespaceGaps")) el("reportWhitespaceGaps").textContent = formatNumber(totals.gap_zips != null ? totals.gap_zips : (result.primary_kpis?.gap_zips ?? (totals.total_zips - totals.active_market_locations)));

        renderReportingMap(result.map_records || [], result.gaps || [], result.top_states || [], result.filters || {});

        const totalLocs = totals.total_locations || 1;
        // "if filter applicable": only show a Subject vs Competitor listing
        // split once the user has actually picked both a subject brand and
        // at least one competitor - otherwise every row's split is
        // meaningless zeros for both columns.
        const hasBrandVsCompetitorFilter = Boolean((result.filters?.main_brands || []).length && (result.filters?.competitor_brands || []).length);

        const rawPrimary = selectedPrimaryBrand(result.filters || "");
        const primaryBrandName = resolveCanonicalBrand(rawPrimary);

        // Dynamic Top States title
        const topStatesHeading = el("reportTopStatesHeading");
        if (topStatesHeading) {
          topStatesHeading.textContent = primaryBrandName ? `${primaryBrandName}'s Top States` : "Top States";
        }

        const top3States = (result.top_states || []).slice(0, 3);
        if (el("reportTopStateCards")) {
          const stateCards = top3States.length ? top3States : [
            { state_name: "State", state: "", locations: 0, state_population: 0 },
            { state_name: "State", state: "", locations: 0, state_population: 0 },
            { state_name: "State", state: "", locations: 0, state_population: 0 },
          ];
          el("reportTopStateCards").innerHTML = stateCards
            .map((st) => {
                const pct = ((st.locations / totalLocs) * 100).toFixed(1);
                const popPerStore = st.state_population && st.locations ? Math.round(st.state_population / st.locations) : null;
                const popStr = st.state_population ? (st.state_population >= 1e6 ? (st.state_population / 1e6).toFixed(2) + "M" : (st.state_population / 1e3).toFixed(0) + "K") : "0";
                const ratioStr = popPerStore ? (popPerStore >= 1e3 ? (popPerStore / 1e3).toFixed(1) + "K" : popPerStore) : "0";
                const stateLabel = st.state_name || st.state || "";
                return `<div style="border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 14px; text-align: center;">
                  <h3 style="margin: 0 0 4px; font-size: 18px; color: var(--ink);">${escapeHtml(stateLabel)}</h3>
                  <div style="font-size: 26px; font-weight: 700; color: var(--accent);">${formatNumber(st.locations)} <span style="font-size: 13px; color: var(--muted); font-weight: 500;">(${pct}%)</span></div>
                  <p style="margin: 8px 0 0; font-size: 12px; color: var(--muted); line-height: 1.4;">
                    Pop. per listing: <strong>${ratioStr}</strong>. Population: ${popStr}
                  </p>
                </div>`;
              }).join("");
        }

        renderSimpleTable("reportTopStates", [
          { key: "state_name", label: "State / Territory" },
          { key: "locations", label: "Listings", format: formatNumber },
          {
            key: "pct",
            label: "Listing Share",
            html: true,
            format: (v, row) => {
              const pct = ((row.locations / totalLocs) * 100).toFixed(1);
              return `<div style="display: flex; align-items: center; gap: 8px;">
                <div style="flex: 1; background: #e2e8f0; border-radius: 4px; height: 8px; overflow: hidden; min-width: 50px;">
                  <div style="background: var(--accent); height: 100%; width: ${pct}%;"></div>
                </div>
                <span style="font-weight: 600; font-size: 12px; width: 42px; text-align: right;">${pct}%</span>
              </div>`;
            }
          },
          {
            key: "state_population",
            label: "State Population",
            format: formatNumber
          },
          {
            key: "pop_per_store",
            label: "Population Per Listing",
            format: (v, row) => {
              if (!row.state_population || !row.locations) return "N/A";
              const ratio = Math.round(row.state_population / row.locations);
              return ratio >= 1e3 ? (ratio / 1e3).toFixed(1) + "K" : ratio;
            }
          },
          { key: "median_household_income", label: "Median Income", format: (v) => v ? `$${formatNumber(Math.round(v))}` : "N/A" },
          { key: "cities", label: "Cities Covered", format: formatNumber },
          ...(hasBrandVsCompetitorFilter ? [
            { key: "main_brand_locations", label: "Subject Brand Listings", format: formatNumber },
            { key: "competitor_brand_locations", label: "Competitor Listings", format: formatNumber }
          ] : [])
        ], result.top_states || []);

        renderSimpleTable("reportTopCities", [
          { key: "city", label: "City" },
          { key: "state_name", label: "State / Territory" },
          { key: "locations", label: "Listings", format: formatNumber },
          { key: "city_population", label: "Population", format: (v) => v ? formatNumber(v) : "N/A" },
          {
            key: "pop_per_listing",
            label: "Population Per Listing",
            format: (v, row) => {
              if (!row.city_population || !row.locations) return "N/A";
              const ratio = Math.round(row.city_population / row.locations);
              return ratio >= 1e3 ? (ratio / 1e3).toFixed(1) + "K" : ratio;
            }
          },
          { key: "median_household_income", label: "Median Income", format: (v) => v ? `$${formatNumber(Math.round(v))}` : "N/A" },
          ...(hasBrandVsCompetitorFilter ? [
            { key: "main_brand_locations", label: "Subject Brand Listings", format: formatNumber },
            { key: "competitor_brand_locations", label: "Competitor Listings", format: formatNumber }
          ] : [])
        ], result.top_cities || []);

        const aggregatedBrandMap = new Map();
        (result.brands || []).forEach((b) => {
          const canonical = resolveCanonicalBrand(b.brand);
          if (!aggregatedBrandMap.has(canonical)) {
            aggregatedBrandMap.set(canonical, {
              brand: canonical,
              locations: 0,
              states: 0,
              counties: 0,
              cities: 0,
              zips: 0,
              is_subject: b.is_subject || false
            });
          }
          const item = aggregatedBrandMap.get(canonical);
          item.locations += Number(b.locations || 0);
          item.states = Math.max(item.states, Number(b.states || 0));
          item.counties = Math.max(item.counties, Number(b.counties || 0));
          item.cities = Math.max(item.cities, Number(b.cities || 0));
          item.zips = Math.max(item.zips, Number(b.zips || 0));
          if (b.is_subject) item.is_subject = true;
        });

        const brandRows = Array.from(aggregatedBrandMap.values()).sort((a, b) => {
          const aIsPrimary = primaryBrandName && a.brand === primaryBrandName;
          const bIsPrimary = primaryBrandName && b.brand === primaryBrandName;
          if (aIsPrimary !== bIsPrimary) return aIsPrimary ? -1 : 1;
          return Number(b.locations || 0) - Number(a.locations || 0);
        });

        const hasPrimarySelected = Boolean(primaryBrandName);
        const primaryRow = hasPrimarySelected ? (brandRows.find((b) => b.brand === primaryBrandName) || null) : null;
        const competitorBrands = primaryRow ? brandRows.filter((b) => b.brand !== primaryRow.brand) : [];

        if (el("reportBrandComparisonTitle")) {
          el("reportBrandComparisonTitle").textContent = hasPrimarySelected && primaryRow && competitorBrands.length
            ? `${primaryRow.brand} vs competitors`
            : (hasPrimarySelected && primaryRow ? `${primaryRow.brand} Overview` : "Brand Comparison");
        }

        // Render the Competitor Benchmark view (with single-row summary when no primary brand is selected)
        renderCompetitorBenchmarkView(primaryRow, competitorBrands, totals, hasPrimarySelected);
        setupBrandComparisonViewSwitcher();
        setBrandComparisonView(activeBrandComparisonView);

        if (el("reportBrandComparisonCards")) {
          if (primaryRow && brandRows.length > 1) {
            const cards = [];
            cards.push(`
              <div style="border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 14px; border-left: 4px solid var(--accent);">
                <div style="font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 600; text-transform: uppercase;">Primary Brand</div>
                <div style="font-size: 20px; font-weight: 700; color: var(--ink); margin-bottom: 8px;">${escapeHtml(primaryRow.brand)}</div>
                <div style="font-size: 12px; color: var(--muted);">
                  <div>${formatNumber(primaryRow.locations)} locations</div>
                  <div>${formatNumber(primaryRow.states)} states</div>
                </div>
              </div>
            `);
            competitorBrands.slice(0, 2).forEach((brand) => {
              const locDiff = brand.locations - primaryRow.locations;
              const stateDiff = brand.states - primaryRow.states;
              const locColor = locDiff > 0 ? "var(--ok)" : locDiff < 0 ? "var(--error)" : "var(--muted)";
              const locSign = locDiff > 0 ? "+" : "";
              const stateColor = stateDiff > 0 ? "var(--ok)" : stateDiff < 0 ? "var(--error)" : "var(--muted)";
              const stateSign = stateDiff > 0 ? "+" : "";
              cards.push(`
                <div style="border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 14px;">
                  <div style="font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 600; text-transform: uppercase;">Competitor</div>
                  <div style="font-size: 20px; font-weight: 700; color: var(--ink); margin-bottom: 8px;">${escapeHtml(brand.brand)}</div>
                  <div style="font-size: 12px; color: var(--muted);">
                    <div>${formatNumber(brand.locations)} locations <span style="color: ${locColor}; font-weight: 600;">(${locSign}${formatNumber(locDiff)})</span></div>
                    <div>${formatNumber(brand.states)} states <span style="color: ${stateColor}; font-weight: 600;">(${stateSign}${formatNumber(stateDiff)})</span></div>
                  </div>
                </div>
              `);
            });
            if (competitorBrands.length > 2) {
              cards.push(`
                <div style="border: 1px solid var(--line); background: #f9fafb; border-radius: 8px; padding: 14px; display: flex; align-items: center; justify-content: center;">
                  <div style="text-align: center; color: var(--muted); font-size: 12px;">
                    <div style="font-weight: 600; margin-bottom: 4px;">+${competitorBrands.length - 2} more</div>
                    <div style="font-size: 11px;">competitors</div>
                  </div>
                </div>
              `);
            }
            el("reportBrandComparisonCards").innerHTML = cards.join("");
          } else if (primaryRow && brandRows.length === 1) {
            el("reportBrandComparisonCards").innerHTML = `<div style="color: var(--muted); font-size: 13px; padding: 16px; text-align: center; background: #f9fafb; border: 1px solid var(--line); border-radius: 8px;">Only one brand in current dataset. Select multiple brands to compare.</div>`;
          } else {
            el("reportBrandComparisonCards").innerHTML = `<div style="color: var(--muted); font-size: 13px; padding: 16px; text-align: center; background: #f9fafb; border: 1px solid var(--line); border-radius: 8px;">No primary brand selected. Pick a primary brand from the left filter sidebar to compare against competitors.</div>`;
          }
        }

        // Every row here is a COMPETITOR measured against the primary brand,
        // so the sign and the sentiment are opposite: a competitor with MORE
        // locations than you is bad news, not good. Colouring diff > 0 green
        // read "+278 competitor locations" as an achievement. One helper for
        // every column so the two can never drift apart again.
        const competitorDiffCell = (value, diff, unit) => {
          if (diff === 0) {
            return `${formatNumber(value)} <span style="color: var(--muted); font-size: 11px; font-weight: 600;" title="Level with ${escapeHtml(primaryRow.brand)}">(Same vs ${escapeHtml(primaryRow.brand)})</span>`;
          }
          const ahead = diff > 0;
          const color = ahead ? "var(--error)" : "var(--ok)";
          const explain = ahead
            ? `${escapeHtml(primaryRow.brand)} is behind by ${formatNumber(Math.abs(diff))} ${unit}`
            : `${escapeHtml(primaryRow.brand)} is ahead by ${formatNumber(Math.abs(diff))} ${unit}`;
          return `${formatNumber(value)} <span style="color: ${color}; font-size: 11px; font-weight: 600;" title="${explain}">(${ahead ? "+" : "-"}${formatNumber(Math.abs(diff))} vs ${escapeHtml(primaryRow.brand)})</span>`;
        };
        const competitorColumn = (key, label, unit) => ({
          key, label, html: true,
          format: (v, row) => (!primaryRow || row.brand === primaryRow.brand)
            ? formatNumber(v)
            : competitorDiffCell(v, row[key] - primaryRow[key], unit),
        });
        renderSimpleTable("reportBrandsTable", [
          { key: "brand", label: "Brand" },
          competitorColumn("locations", "Number of Locations", "locations"),
          competitorColumn("states", "Number of States", "states"),
          competitorColumn("counties", "Counties Covered", "counties"),
          competitorColumn("cities", "Cities Covered", "cities"),
          competitorColumn("zips", "ZIP Codes Covered", "ZIP codes")
        ], brandRows);

        // Render market gaps with client-side pagination
        renderMarketGapsWithPagination(result.gaps || [], 1);

        // States & Territories Without Tracked Locations (full names, not short codes)
        const emptyStates = (result.states_without_locations || []).map((code) => {
          const cleanCode = String(code || "").toUpperCase().trim();
          return stateCodeToName[cleanCode] || code;
        }).filter(Boolean);
        emptyStates.sort((a, b) => a.localeCompare(b));

        el("reportEmptyStates").innerHTML = emptyStates.length
          ? emptyStates.map((state) => `<span>${escapeHtml(state)}</span>`).join("")
          : '<div class="report-status">Every tracked state and territory has at least one active location.</div>';

        // Sample records with Download CSV functionality
        currentSampleRecords = result.sample_records || [];
        setupSampleRecordsDownload();
        renderSimpleTable("reportSampleRecords", [
          { key: "name", label: "Name" },
          { key: "address", label: "Street" },
          { key: "city", label: "City" },
          { key: "state_name", label: "State" },
          { key: "county", label: "County" },
          { key: "zip_code", label: "Zip Code" },
          { key: "phone_number", label: "Phone" },
          { key: "latitude", label: "Latitude" },
          { key: "longitude", label: "Longitude" },
          { key: "country", label: "Country" },
          { key: "last_observed_at", label: "Last Updated" }
        ], currentSampleRecords);

        if (interactive && !result.refreshing && hasBusinessData) status.classList.add("hidden");
        el("reportContent").classList.remove("hidden");
        reportLoaded = true;
        reportHasRenderedOnce = true;
      } catch (error) {
        renderEmptyReportingStructure();
        status.className = "report-status";
        status.textContent = productSafeError(error.message, "No reporting records found for the current filters.");
        scheduleReportingWarmupPoll(3000);
        reportLoaded = false;
      } finally {
        if (interactive) {
          clearButtonBusy(refreshBtn, previousRefreshBtn);
          if (applyBtn) clearButtonBusy(applyBtn, previousApplyBtn);
        }
      }
      startReportingAutoRefreshCountdown();
}

function renderReportingCountdown() {
      const countdownEl = el("reportAutoRefreshCountdown");
      if (!countdownEl) return;
      const minutes = Math.floor(reportingCountdownSeconds / 60);
      const seconds = reportingCountdownSeconds % 60;
      countdownEl.textContent = `Next auto refresh in ${minutes}:${String(seconds).padStart(2, "0")}`;
    }

function startReportingAutoRefreshCountdown() {
      renderReportingCountdown();
      if (reportingCountdownTimer) return;
      reportingCountdownTimer = window.setInterval(() => {
        if (document.getElementById("reportingView")?.classList.contains("hidden")) return;
        reportingCountdownSeconds -= 1;
        if (reportingCountdownSeconds <= 0) {
          reportingCountdownSeconds = 300;
          loadReporting({ interactive: false });
        }
        renderReportingCountdown();
      }, 1000);
    }

async function refreshReportingNow() {
      const status = el("reportStatus");
      const refreshBtn = el("refreshReportBtn");
      // An explicit click is the user asking again, so it always gets a full
      // poll budget - otherwise a session that exhausted it once could never
      // recover without a page reload.
      resetReportingWarmupPolls();
      const previousRefreshBtn = setButtonBusy(refreshBtn, "Starting Refresh");
      reportingCountdownSeconds = 300;
      renderReportingCountdown();
      // No status line here: the Refresh button itself is already showing
      // "Starting Refresh" with a spinner, and the countdown sits right
      // under it. A second line saying the same thing was pure duplication -
      // and its reserved height was the empty band under the button.
      if (status) status.classList.add("hidden");
      try {
        const response = await fetch("/api/reporting/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ low_priority: true })
        });
        let result = {};
        try { result = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(result.error || "Could not start report refresh.");
        // Same reasoning: the button carries the in-flight state. Only an
        // "already running" case is worth a word, and even that goes on the
        // button rather than opening a second status band.
        if (status) status.classList.add("hidden");
        reportLoaded = false;
        await loadReporting({ interactive: true });
        if (typeof window.reportingRefreshQuality === "function") window.reportingRefreshQuality();
      } catch (error) {
        if (status) {
          status.className = "report-status";
          status.textContent = productSafeError(error.message, "Could not refresh the report right now.");
        }
      } finally {
        clearButtonBusy(refreshBtn, previousRefreshBtn);
      }
}

// The enrichment control does not stop enrichment any more - it eases it
// off. The queue keeps draining at roughly 2 rows every 30 seconds instead of
// 10 every 5, which is slow enough to stay out of the user's way while still
// making progress. That makes the button a two-state toggle over one route:
// POST /api/enrichment/stop eases, the same route with {resume:true} returns
// to full speed. Its label therefore has to describe what a click will DO,
// and it is rendered from the server's throttled flag rather than flipped
// locally - otherwise reloading the page mid-ease would show "Ease Off" over
// an already-eased queue.
const ENRICHMENT_EASE_LABEL = "Ease Off Enriching";
const ENRICHMENT_RESUME_LABEL = "Resume Full Speed";
// Deliberately no spinner, no processed count and no "current record" line:
// at this pace a progress indicator crawls, and a crawling progress bar reads
// as a hung app rather than a considerate one. One calm sentence, so the
// quiet is explained rather than mistaken for nothing happening.
const ENRICHMENT_EASED_NOTE = "Enrichment eased off. It keeps working quietly in the background.";

function renderEnrichmentToggle(button, eased) {
  if (!button) return;
  button.dataset.enrichmentMode = eased ? "eased" : "full";
  button.textContent = eased ? ENRICHMENT_RESUME_LABEL : ENRICHMENT_EASE_LABEL;
  button.title = eased
    ? "Enrichment is running at a trickle in the background. Put it back to full speed."
    : "Keep enriching, but slowly enough to stay out of your way. Nothing is discarded and nothing stops.";
}

// Fast only while there is something to watch. Eased work moves a couple of
// rows in half a minute and displays nothing at all, and an idle app displays
// nothing either - polling those every 3s is hundreds of requests an hour to
// learn nothing, on a 512MB deployment. The slow tick still has a job: it is
// what keeps the toggle honest about the server's current pace.
const ENRICHMENT_POLL_MS = 3000;
const ENRICHMENT_QUIET_POLL_MS = 30000;
let enrichmentPollIntervalMs = 0;

function stopEnrichmentStatusPolling() {
      if (enrichmentStatusTimer) {
        window.clearInterval(enrichmentStatusTimer);
        enrichmentStatusTimer = null;
      }
      enrichmentPollIntervalMs = 0;
    }

// A running poller is deliberately left alone by startEnrichmentStatusPolling
// below, so anything that CHANGES the thing being polled has to ask for a
// fresh look: this fires an immediate poll and re-picks the cadence.
function restartEnrichmentStatusPolling() {
      stopEnrichmentStatusPolling();
      startEnrichmentStatusPolling();
    }

function startEnrichmentStatusPolling() {
      if (enrichmentStatusTimer) return;
      let sawWork = false;
      const poll = async () => {
        try {
          const response = await fetch("/api/enrichment/status", { cache: "no-store" });
          if (!response.ok) return;
          const state = await response.json();
          const target = el("reportingDataRefreshStatus");
          const stopButton = el("stopEnrichmentBtn");
          // "eased" is a state of its own, not a flavour of running, and it
          // outranks running: the server reports state="eased" while work is
          // in flight under the throttle, and keeps throttled=true even once
          // the queue goes quiet (the pace is a setting, not a run). Either
          // way the user asked not to be shown the processing.
          const eased = state.throttled === true || state.state === "eased";
          const running = !eased && (state.refreshing || state.state === "running");
          if (running || eased) sawWork = true;
          // Always re-rendered, never toggled on click alone: this is what
          // makes the button correct after a reload, and after another tab
          // (or the shutdown path) changes the pace.
          renderEnrichmentToggle(stopButton, eased);
          if (!target) return;
          if (eased) {
            // The toggle stays visible - it is the only way back to full
            // speed - but everything that reads as "processing" goes.
            target.className = "action-feedback";
            target.textContent = ENRICHMENT_EASED_NOTE;
            stopButton?.classList.remove("hidden");
          } else if (running) {
            target.className = "action-feedback";
            // Explicit user ask (2026-09-10): the processed-record count is
            // internal progress, not something to surface here at all - not
            // "Processed 0 records", not "Processed 34 records" either.
            // Just the busy state.
            target.innerHTML = busyMarkup("Enriching in progress");
            stopButton?.classList.remove("hidden");
          } else if (state.state === "stopped") {
            target.className = "action-feedback warn";
            target.textContent = "Enrichment stopped. Unresolved records remain available for review.";
            stopButton?.classList.add("hidden");
          } else if (state.state === "failed") {
            target.className = "action-feedback error";
            target.textContent = "Enrichment could not complete. It will retry automatically.";
            stopButton?.classList.add("hidden");
          } else {
            stopButton?.classList.add("hidden");
          }
          // Stop polling once a run we were watching has reached a terminal
          // state - otherwise this timer runs every 3s for the rest of the
          // session (leak risk on a 512MB deployment). An eased run is NOT
          // terminal: the queue is still draining and, more importantly, the
          // toggle has to keep reflecting the server's pace or it would sit
          // offering the wrong action. So it keeps polling - slowly.
          if (sawWork && !running && !eased) {
            stopEnrichmentStatusPolling();
            return;
          }
          // Re-arm at the cadence the current state deserves.
          const wanted = running ? ENRICHMENT_POLL_MS : ENRICHMENT_QUIET_POLL_MS;
          if (wanted !== enrichmentPollIntervalMs) {
            if (enrichmentStatusTimer) window.clearInterval(enrichmentStatusTimer);
            enrichmentPollIntervalMs = wanted;
            enrichmentStatusTimer = window.setInterval(poll, wanted);
          }
        } catch (_) {}
      };
      poll();
      enrichmentPollIntervalMs = ENRICHMENT_POLL_MS;
      enrichmentStatusTimer = window.setInterval(poll, ENRICHMENT_POLL_MS);
    }

async function refreshReportingData() {
      const target = el("reportingDataRefreshStatus");
      const button = el("reportingDataRefreshBtn");
      const stopButton = el("stopEnrichmentBtn");
      const previousButton = setButtonBusy(button, "Enriching");
      stopButton?.classList.remove("hidden");
      target.className = "action-feedback";
      // Starting a run while the pace is eased must not flash the very
      // spinner the easing exists to remove; the poll below settles both
      // cases within a tick either way.
      if (stopButton?.dataset.enrichmentMode === "eased") target.textContent = ENRICHMENT_EASED_NOTE;
      else target.innerHTML = busyMarkup("Enriching in progress");
      try {
        const response = await fetch("/api/reporting/refresh", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not refresh data.");
        target.className = "action-feedback ok";
        target.textContent = `Enrichment started for ${result.rows || 0} records.`;
        // The poller may be sitting on its quiet 30s tick (nothing was
        // running a moment ago), and a run the user just started should not
        // wait that long to be picked up and shown.
        restartEnrichmentStatusPolling();
      } catch (error) {
        target.className = "action-feedback error";
        target.textContent = productSafeError(error.message, "Could not refresh data.");
      } finally {
        clearButtonBusy(button, previousButton);
        stopButton?.classList.add("hidden");
      }
    }

// Both directions of the toggle. Which one a click means is read off the
// button, whose label the status poll keeps truthful - not off a module flag
// that a reload would lose. The route is still called /api/enrichment/stop:
// it keeps its name for existing clients, but with {} it eases and with
// {resume:true} it returns to full speed. Neither touches the hard-stop flag,
// so nothing is abandoned and the queue is never left half-processed.
async function toggleEnrichmentEasing() {
      const button = el("stopEnrichmentBtn");
      const target = el("reportingDataRefreshStatus");
      const resume = button?.dataset.enrichmentMode === "eased";
      if (button) button.disabled = true;
      try {
        const response = await fetch("/api/enrichment/stop", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(resume ? { resume: true } : {})
        });
        let result = {};
        try { result = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(result.error || "Could not change the enrichment pace.");
        // The server's own answer decides the new state, not the click that
        // asked for it - the two can disagree (another tab, a run that ended
        // meanwhile), and the server is the one that knows.
        const eased = result.throttled === true || result.state === "eased";
        renderEnrichmentToggle(button, eased);
        if (target) {
          target.className = "action-feedback";
          target.textContent = eased ? ENRICHMENT_EASED_NOTE : "Enrichment is back at full speed.";
        }
        // The pace just changed under the poller, so it needs a fresh look:
        // this confirms the control against the server immediately and moves
        // the tick to the cadence the new pace deserves.
        restartEnrichmentStatusPolling();
      } catch (error) {
        if (target) {
          target.className = "action-feedback error";
          target.textContent = productSafeError(error.message, "Could not change the enrichment pace.");
        }
      } finally {
        if (button) button.disabled = false;
      }
    }
