// Reporting tab: filters, KPI/table rendering, and the Leaflet location map.

let reportLoaded = false;
let reportingBrands = [];
let enrichmentStatusTimer = null;
let reportingCountdownTimer = null;
let reportingCountdownSeconds = 300;
let reportingWarmupTimer = null;

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
            Loading competitor benchmark view...
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
        { key: "competitor_locations", label: "Competitor Stores", format: formatNumber },
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
      return Number(totals.total_stores || 0) > 0
        || Number(totals.total_brands || 0) > 0
        || Number(totals.active_market_locations || 0) > 0;
    }

function scheduleReportingWarmupPoll(delayMs = 5000) {
      if (reportingWarmupTimer) return;
      reportingWarmupTimer = window.setTimeout(() => {
        reportingWarmupTimer = null;
        if (document.getElementById("reportingView")?.classList.contains("hidden")) return;
        loadReporting({ interactive: false });
      }, delayMs);
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
let pinMarkersLayerGroup = null;
let gapMarkersLayerGroup = null;
let staticMapZoom = 1;
// Keep the complete contiguous US in view, with enough scale to read the
// state-level layer without opening on an overly distant national view.
const DEFAULT_US_MAP_VIEW = { center: [39.8283, -98.5795], zoom: 5 };
const DEFAULT_US_BOUNDS = [[24.3963, -125.0], [49.3844, -66.9346]];
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
function syncMapLayersByZoom() {
  if (!reportingMap) return;
  const currentZoom = reportingMap.getZoom();
  const activeCityFilter = String(el("reportCityFilter")?.value || "").trim();
  const activeZipFilter = String(el("reportZipFilter")?.value || "").trim();
  const isPinLevel = Boolean(activeCityFilter || activeZipFilter) || currentZoom >= 9.5;
  const isCityLevel = currentZoom >= 6.0 && currentZoom < 9.5;

  if (isPinLevel) {
    if (pinMarkersLayerGroup && !reportingMap.hasLayer(pinMarkersLayerGroup)) reportingMap.addLayer(pinMarkersLayerGroup);
    if (cityCirclesLayerGroup && reportingMap.hasLayer(cityCirclesLayerGroup)) reportingMap.removeLayer(cityCirclesLayerGroup);
    if (stateCirclesLayerGroup && reportingMap.hasLayer(stateCirclesLayerGroup)) reportingMap.removeLayer(stateCirclesLayerGroup);
  } else if (isCityLevel) {
    if (pinMarkersLayerGroup && reportingMap.hasLayer(pinMarkersLayerGroup)) reportingMap.removeLayer(pinMarkersLayerGroup);
    if (cityCirclesLayerGroup && !reportingMap.hasLayer(cityCirclesLayerGroup)) reportingMap.addLayer(cityCirclesLayerGroup);
    if (stateCirclesLayerGroup && reportingMap.hasLayer(stateCirclesLayerGroup)) reportingMap.removeLayer(stateCirclesLayerGroup);
  } else {
    // National level: show state circles
    if (pinMarkersLayerGroup && reportingMap.hasLayer(pinMarkersLayerGroup)) reportingMap.removeLayer(pinMarkersLayerGroup);
    if (cityCirclesLayerGroup && reportingMap.hasLayer(cityCirclesLayerGroup)) reportingMap.removeLayer(cityCirclesLayerGroup);
    if (stateCirclesLayerGroup && !reportingMap.hasLayer(stateCirclesLayerGroup)) reportingMap.addLayer(stateCirclesLayerGroup);
  }
  // Gap ZIPs are an analysis layer, so keep them visible at every zoom level.
  if (gapMarkersLayerGroup && !reportingMap.hasLayer(gapMarkersLayerGroup)) {
    reportingMap.addLayer(gapMarkersLayerGroup);
  }
}

let mapZoomListenerAttached = false;

function renderReportingMap(mapRecords = [], gapRecords = [], stateRecords = [], filters = {}) {
      if (!el("reportingMap")) return;
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
        pinMarkersLayerGroup = L.layerGroup().addTo(reportingMap);
        gapMarkersLayerGroup = L.layerGroup().addTo(reportingMap);
      }
      if (!mapZoomListenerAttached && reportingMap) {
        reportingMap.on("zoomend", syncMapLayersByZoom);
        mapZoomListenerAttached = true;
      }
      if (mapMarkerLayerGroup) mapMarkerLayerGroup.clearLayers();
      if (stateBoundaryLayerGroup) stateBoundaryLayerGroup.clearLayers();
      if (stateCirclesLayerGroup) stateCirclesLayerGroup.clearLayers();
      if (cityCirclesLayerGroup) cityCirclesLayerGroup.clearLayers();
      if (pinMarkersLayerGroup) pinMarkersLayerGroup.clearLayers();
      if (gapMarkersLayerGroup) gapMarkersLayerGroup.clearLayers();

      const primaryBrand = selectedPrimaryBrand(filters);
      const primaryBrandKey = primaryBrand.toLowerCase();
      const bounds = [];
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
          stateBoundaryLayerGroup.clearLayers();
          L.geoJSON(geojson, {
            style: (feature) => {
              const code = stateNameToCode[feature?.properties?.name] || "";
              const isSelected = activeStateFilter && code === activeStateFilter;
              const hasData = (boundaryStateCounts.get(code) || 0) > 0;
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
        const markerHtml = hasRecords
          ? `<div style="width:${size}px; height:${size}px; line-height:${size - 4}px; border-radius:50%; background:#e7f0ff; border:2px solid #2563eb; color:#1e40af; font-size:11px; font-weight:800; text-align:center; box-sizing:border-box; cursor:pointer; box-shadow:0 1px 4px rgba(0,0,0,0.15);">${escapeHtml(stateCode)}</div>`
          : `<div style="width:${size}px; height:${size}px; line-height:${size - 2}px; border-radius:50%; background:rgba(255,255,255,0.85); border:1px solid #cbd5e1; color:#475569; font-size:10px; font-weight:700; text-align:center; box-sizing:border-box; cursor:pointer; box-shadow:0 1px 2px rgba(0,0,0,0.08);">${escapeHtml(stateCode)}</div>`;

        const marker = L.marker([lat, lon], {
          icon: L.divIcon({
            className: "",
            html: markerHtml,
            iconSize: [size, size],
            iconAnchor: [radius, radius]
          })
        });

        // Interactive hover tooltip showing full state name and exact listing count
        marker.bindTooltip(`
          <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4; padding: 2px 4px;">
            <strong style="color: #0f172a; font-size: 14px;">${escapeHtml(stateName)}</strong><br/>
            <span style="color: ${hasRecords ? '#2563eb' : '#64748b'}; font-weight: 700; font-size: 13px;">${formatNumber(storeCount)} Listing${storeCount === 1 ? "" : "s"}</span>
          </div>
        `, {
          permanent: false,
          sticky: true,
          opacity: 0.96,
          offset: [0, -10]
        });

        // Click on state bubble zooms into state at city level
        marker.on("click", () => {
          if (reportingMap) reportingMap.setView([lat, lon], 7);
        });

        stateCirclesLayerGroup.addLayer(marker);
      });

      // 2. CITY CIRCLES: Aggregated at city level, shown at zoom 6-8 before marker pins appear
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

        const cityMarker = L.circleMarker([avgLat, avgLon], {
          radius: Math.max(7, Math.min(22, Math.sqrt(item.count) * 2.2)),
          fillColor: "#f3e8ff",
          color: "#7c3aed",
          weight: 2,
          opacity: 0.92,
          fillOpacity: 0.88
        });

        // Hover tooltip showing city, state and exact listing count
        cityMarker.bindTooltip(`
          <div style="font-family: system-ui, -apple-system, sans-serif; font-size: 13px; line-height: 1.4; padding: 2px 4px;">
            <strong style="color: #0f172a; font-size: 14px;">${escapeHtml(item.city)}, ${escapeHtml(item.state)}</strong><br/>
            <span style="color: #7c3aed; font-weight: 700; font-size: 13px;">${formatNumber(item.count)} Listing${item.count === 1 ? "" : "s"}</span>
          </div>
        `, {
          sticky: true,
          opacity: 0.96,
          offset: [0, -8]
        });

        // Click on city bubble zooms into city at street/pin level
        cityMarker.on("click", () => {
          if (reportingMap) reportingMap.setView([avgLat, avgLon], 11);
        });

        cityCirclesLayerGroup.addLayer(cityMarker);
      });

      // 3. INDIVIDUAL STORE & GAP PIN MARKERS: Shown at zoom >= 9.5 or when filtered to specific city/zip
      mapRecords.forEach((rec) => {
        const lat = parseFloat(rec.latitude);
        const lon = parseFloat(rec.longitude);
        if (!isUSLatLong(lat, lon)) return; // Discard non-US coordinates
        bounds.push([lat, lon]);
        const isPrimary = primaryBrandKey && String(rec.brand || "").toLowerCase() === primaryBrandKey;
        const color = primaryBrandKey ? (isPrimary ? "#16a34a" : "#dc2626") : "#3b82f6";
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
        gapMarkersLayerGroup.addLayer(marker);
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
        pinMarkersLayerGroup.addLayer(marker);
      });

      syncMapLayersByZoom();

      if (bounds.length && shouldFocusFilteredArea) {
        reportingMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
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
        dropdownBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          dropdownMenu.style.display = dropdownMenu.style.display === "block" ? "none" : "block";
        });
        document.addEventListener("click", (e) => {
          if (!e.target.closest("#competitorDropdownContainer")) {
            dropdownMenu.style.display = "none";
          }
        });
      }
      setupBrandComparisonViewSwitcher();
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
                  <span class="comp-metric-num">${formatNumber(totals.total_stores || totals.active_market_locations || 0)}</span>
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
              <span class="comp-primary-name">${escapeHtml(primaryName)}</span>
            </div>
            <div class="comp-brand-row comp-brand-vs">
              <span class="comp-vs-badge">VS</span>
              <span class="comp-logo-icon" title="${escapeHtml(compName)}">${compLogo}</span>
              <a href="#" class="comp-link-name" data-competitor-brand="${escapeHtml(compName)}" title="Focus on ${escapeHtml(compName)}">${escapeHtml(compName)}</a>
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
async function loadGeoOptions() {
      const state = el("reportStateFilter")?.value || "";
      const county = el("reportCountyFilter")?.value || "";
      try {
        const response = await fetch(`/api/geo/options?state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}`);
        const data = await response.json();
        if (!response.ok) return;

        const stateSel = el("reportStateFilter");
        if (stateSel && stateSel.options.length <= 1 && data.states?.length) {
          const current = stateSel.value;
          stateSel.innerHTML = '<option value="">All States</option>' + data.states.map((st) => {
            const code = typeof st === "string" ? st : st.code;
            const name = typeof st === "string" ? st : (st.name || st.code);
            return `<option value="${escapeHtml(code)}">${escapeHtml(name)}</option>`;
          }).join("");
          stateSel.value = current;
        }

        const countySel = el("reportCountyFilter");
        if (countySel) {
          const currentCounty = countySel.value;
          const countyList = data.counties || [];
          countySel.innerHTML = '<option value="">All Counties</option>' + countyList.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
          countySel.value = countyList.includes(currentCounty) ? currentCounty : "";
        }

        const citySel = el("reportCityFilter");
        if (citySel) {
          const currentCity = citySel.value;
          const cityList = data.cities || [];
          citySel.innerHTML = '<option value="">All Cities</option>' + cityList.map((ct) => `<option value="${escapeHtml(ct)}">${escapeHtml(ct)}</option>`).join("");
          citySel.value = cityList.includes(currentCity) ? currentCity : "";
        }
        // Cache the full option set first, then re-narrow it - otherwise a
        // repopulate would silently discard whatever the user had typed.
        GEO_SEARCHABLE_FILTERS.forEach(([selectId]) => {
          cacheGeoOptions(selectId);
          applyGeoOptionSearch(selectId);
        });
      } catch (err) {}
    }

const GEO_SEARCHABLE_FILTERS = [
  ["reportStateFilter", "states"],
  ["reportCountyFilter", "counties"],
  ["reportCityFilter", "cities"],
];
const geoOptionCache = {};

function setupGeoFilterSearch() {
      GEO_SEARCHABLE_FILTERS.forEach(([selectId, label]) => {
        const select = el(selectId);
        if (!select || document.getElementById(`${selectId}Search`)) return;
        const search = document.createElement("input");
        search.id = `${selectId}Search`;
        search.type = "search";
        search.className = "report-filter-control report-filter-search";
        search.placeholder = `Type 2+ letters to search ${label}`;
        search.setAttribute("aria-label", `Search ${label}`);
        search.autocomplete = "off";
        select.parentNode.insertBefore(search, select);
        search.addEventListener("input", () => applyGeoOptionSearch(selectId));
        cacheGeoOptions(selectId);
      });
    }

function cacheGeoOptions(selectId) {
      const select = el(selectId);
      if (!select || select.options.length <= 1) return;
      geoOptionCache[selectId] = Array.from(select.options).map((option) => ({ value: option.value, text: option.textContent }));
    }

function applyGeoOptionSearch(selectId) {
      const select = el(selectId);
      const search = document.getElementById(`${selectId}Search`);
      const allOptions = geoOptionCache[selectId];
      if (!select || !search || !allOptions || !allOptions.length) return;
      const query = search.value.trim().toLowerCase();
      const selected = select.value;
      // Under 2 characters there is nothing worth narrowing by, so show the
      // full list. The blank "All X" option and whatever is currently
      // selected always survive the filter, so a search can never strip the
      // active selection out of the control.
      const matches = query.length < 2
        ? allOptions
        : allOptions.filter((option) => !option.value || option.value === selected || option.text.toLowerCase().includes(query));
      select.innerHTML = matches.map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.text)}</option>`).join("");
      select.value = selected;
    }
let zipTypeaheadTimer = null;
let zipTypeaheadRequestId = 0;
function setupZipTypeahead() {
      const zipInput = el("reportZipFilter");
      const datalist = el("zipSuggestions");
      if (!zipInput || !datalist) return;

      zipInput.addEventListener("input", () => {
        clearTimeout(zipTypeaheadTimer);
        const query = zipInput.value.trim();
        const requestId = ++zipTypeaheadRequestId;
        if (!query) {
          datalist.innerHTML = "";
          return;
        }
        zipTypeaheadTimer = setTimeout(async () => {
          const state = el("reportStateFilter")?.value || "";
          const county = el("reportCountyFilter")?.value || "";
          const city = el("reportCityFilter")?.value || "";
          try {
            const resp = await fetch(`/api/zips/search?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}&city=${encodeURIComponent(city)}`);
            const data = await resp.json();
            if (requestId !== zipTypeaheadRequestId) return;
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
    { key: "competitor_locations", label: "Competitor Stores", format: formatNumber },
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
    if (text) text.textContent = "Preparing Excel…";

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
      alert(`Excel export failed: ${err.message}`);
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
        status.innerHTML = '<span class="spinner"></span> Refreshing report...';
      } else {
        status.classList.add("hidden");
      }
      renderEmptyReportingStructure();
      try {
        const queryString = reportingQueryString();
        const response = await fetch(`/api/reporting${queryString ? `?${queryString}` : ""}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load reporting data.");
        syncReportingFilters(result);
        el("reportContent").classList.remove("hidden");
        const totals = result.totals || {};
        const hasBusinessData = reportHasBusinessData(totals);
        if (result.warning && !result.refreshing) {
          status.className = "report-status";
          status.textContent = result.warning;
        } else if (result.refreshing && !hasBusinessData) {
          status.className = "report-status loading";
          status.innerHTML = '<span class="spinner"></span> Preparing reporting data...';
          scheduleReportingWarmupPoll(3000);
        } else if (interactive && result.refreshing) {
          // The Refresh Report button itself already shows "Refreshing
          // Reports" with a spinner while this is in flight - no need for a
          // second, redundant status line saying the same thing.
          status.classList.add("hidden");
          scheduleReportingWarmupPoll(10000);
        } else {
          status.classList.add("hidden");
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
        if (el("reportStores")) el("reportStores").textContent = formatNumber(totals.total_stores || 0);
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

        renderSimpleTable("reportBrandsTable", [
          { key: "brand", label: "Brand" },
          {
            key: "locations",
            label: "Number of Locations",
            html: true,
            format: (v, row) => {
              if (!primaryRow || row.brand === primaryRow.brand) return formatNumber(v);
              const diff = row.locations - primaryRow.locations;
              const color = diff > 0 ? "var(--ok)" : "var(--error)";
              const sign = diff > 0 ? "+" : "";
              return `${formatNumber(v)} <span style="color: ${color}; font-size: 11px; font-weight: 600;">(${sign}${formatNumber(diff)} vs ${escapeHtml(primaryRow.brand)})</span>`;
            }
          },
          {
            key: "states",
            label: "Number of States",
            html: true,
            format: (v, row) => {
              if (!primaryRow || row.brand === primaryRow.brand) return formatNumber(v);
              const diff = row.states - primaryRow.states;
              const color = diff > 0 ? "var(--ok)" : (diff < 0 ? "var(--error)" : "var(--muted)");
              const sign = diff > 0 ? "+" : "";
              return `${formatNumber(v)} <span style="color: ${color}; font-size: 11px; font-weight: 600;">(${diff === 0 ? "Same" : `${sign}${diff}`} vs ${escapeHtml(primaryRow.brand)})</span>`;
            }
          },
          { key: "counties", label: "Counties Covered", format: formatNumber },
          { key: "cities", label: "Cities Covered", format: formatNumber },
          { key: "zips", label: "ZIP Codes Covered", format: formatNumber }
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
      const previousRefreshBtn = setButtonBusy(refreshBtn, "Starting Refresh");
      reportingCountdownSeconds = 300;
      renderReportingCountdown();
      if (status) {
        status.className = "report-status loading";
        status.innerHTML = '<span class="spinner"></span> Starting report refresh...';
      }
      try {
        const response = await fetch("/api/reporting/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ low_priority: true })
        });
        let result = {};
        try { result = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(result.error || "Could not start report refresh.");
        if (status) {
          status.className = "report-status loading";
          status.innerHTML = result.started === false
            ? '<span class="spinner"></span> Report refresh is already running...'
            : '<span class="spinner"></span> Report refresh started. Updating numbers...';
        }
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

function stopEnrichmentStatusPolling() {
      if (enrichmentStatusTimer) {
        window.clearInterval(enrichmentStatusTimer);
        enrichmentStatusTimer = null;
      }
    }

function startEnrichmentStatusPolling() {
      if (enrichmentStatusTimer) return;
      let sawRunning = false;
      const poll = async () => {
        try {
          const response = await fetch("/api/enrichment/status", { cache: "no-store" });
          if (!response.ok) return;
          const state = await response.json();
          const target = el("reportingDataRefreshStatus");
          const stopButton = el("stopEnrichmentBtn");
          const running = state.refreshing || state.state === "running";
          if (running) sawRunning = true;
          if (!target) return;
          if (running) {
            target.className = "action-feedback";
            target.innerHTML = `${busyMarkup("Enriching in progress")} <small>Processed ${Number(state.processed || 0)} records${state.current_id ? `; current ${escapeHtml(state.current_id)}` : ""}.</small>`;
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
          // session (leak risk on a 512MB deployment).
          if (sawRunning && !running) stopEnrichmentStatusPolling();
        } catch (_) {}
      };
      poll();
      enrichmentStatusTimer = window.setInterval(poll, 3000);
    }

async function refreshReportingData() {
      const target = el("reportingDataRefreshStatus");
      const button = el("reportingDataRefreshBtn");
      const stopButton = el("stopEnrichmentBtn");
      const previousButton = setButtonBusy(button, "Enriching");
      stopButton?.classList.remove("hidden");
      target.className = "action-feedback";
      target.innerHTML = busyMarkup("Enriching in progress");
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
      } catch (error) {
        target.className = "action-feedback error";
        target.textContent = productSafeError(error.message, "Could not refresh data.");
      } finally {
        clearButtonBusy(button, previousButton);
        stopButton?.classList.add("hidden");
      }
    }

async function stopEnrichment() {
      await fetch("/api/enrichment/stop", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
      const target = el("reportingDataRefreshStatus");
      if (target) { target.className = "action-feedback warn"; target.textContent = "Stop requested. The current database operation will finish safely."; }
    }
