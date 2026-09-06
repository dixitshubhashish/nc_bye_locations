/**
 * @file reporting.core.js
 * @summary Core logic for the Reporting tab.
 *
 * @description
 * Owns everything the reporting screen does: building the filter controls
 * (primary/competitor brands, cascading state/county/city/ZIP, demographics),
 * fetching the report from the backend, rendering the KPI tiles and data
 * tables, and drawing the location map (Leaflet when available, with a static
 * grid fallback).
 *
 * Backend endpoints consumed:
 *   - `GET /api/reporting`        - the full report payload (KPIs, brands,
 *                                   gaps, top states/cities, map + sample rows)
 *   - `GET /api/geo/options`      - state/county/city dropdown options
 *   - `GET /api/zips/search`      - ZIP typeahead suggestions
 *   - `POST /api/reporting/refresh` - rebuild the reporting data
 *
 * Dependencies (globals from `js/common.js`): `el`, `escapeHtml`,
 * `formatNumber`, `renderSimpleTable`, `productSafeError`. Vendor globals:
 * `L` (Leaflet) and `topojson`, both optional (the code degrades gracefully).
 *
 * Load order: this file must load AFTER `common.js`. It publishes several
 * globals (e.g. `loadReporting`, `reportLoaded`, `reportingQueryString`,
 * `window.reportingMap`) that `js/common.js` (switchView), `reporting.wiring.js`,
 * and `reporting.tabs.js` rely on.
 *
 * NOTE: This is relocated code (previously `ui/js/reporting.js`); its behavior
 * is unchanged - only documentation and its folder location were updated.
 */

/** @type {boolean} True once a report has been fetched; short-circuits reloads. */
let reportLoaded = false;
/** @type {string[]} Brand names available in the current report (for dropdowns). */
let reportingBrands = [];
/** @type {?string} Primary brand for which competitor defaults were last applied. */
let competitorDefaultsAppliedForMainBrand = null;

/**
 * Reveal the report body and render every KPI tile, card, and table in an
 * empty/zeroed state (including a default US map). Used as the initial skeleton
 * before data arrives and as the fallback when a load fails.
 * @returns {void}
 */
function renderEmptyReportingStructure() {
      el("reportContent").classList.remove("hidden");
      ["reportLocations", "reportBrands", "reportStates", "reportCities", "reportZips", "reportStores", "reportBrandStates", "reportWhitespaceGaps"].forEach((id) => {
        if (el(id)) el(id).textContent = "0";
      });
      renderReportingMap([], [], defaultStateRecords);
      if (el("reportTopStateCards")) {
        el("reportTopStateCards").innerHTML = [1, 2, 3].map(() => `
          <div style="border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 14px; text-align: center;">
            <h3 style="margin: 0 0 4px; font-size: 18px; color: var(--ink);">State</h3>
            <div style="font-size: 26px; font-weight: 700; color: var(--accent);">0 <span style="font-size: 13px; color: var(--muted); font-weight: 500;">(0.0%)</span></div>
            <p style="margin: 8px 0 0; font-size: 12px; color: var(--muted); line-height: 1.4;">People per location: <strong>0</strong>. Population: 0</p>
          </div>
        `).join("");
      }
      renderSimpleTable("reportTopStates", [
        { key: "state_name", label: "State / Territory" },
        { key: "locations", label: "ZIP Locations", format: formatNumber },
        { key: "pct", label: "Location Share" },
        { key: "state_population", label: "State Population", format: formatNumber },
        { key: "pop_per_store", label: "Population Per Location", format: formatNumber },
        { key: "cities", label: "Cities Covered", format: formatNumber }
      ], []);
      renderSimpleTable("reportTopCities", [
        { key: "city", label: "City" },
        { key: "state_name", label: "State / Territory" },
        { key: "locations", label: "ZIP Locations", format: formatNumber }
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
        { key: "brands_present", label: "Competitor Brands" },
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
/**
 * Return the values of all checked checkboxes/radios sharing a `name`.
 * @param {string} name - The control group's `name` attribute.
 * @returns {string[]} The checked values, in document order.
 */
function checkedValues(name) {
      return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
    }
/**
 * Render a list of brand checkboxes into a container and reload the report
 * whenever the selection changes.
 * @param {string} containerId - Id of the element to render the checkboxes into.
 * @param {string} name - Shared `name` for the rendered checkboxes.
 * @param {string[]} brands - Brand options to render.
 * @param {string[]} [checkedBrands] - Brands that should start checked.
 * @param {string} [emptyMessage="No brands available."] - Shown when `brands`
 *   is empty.
 * @returns {void}
 */
function renderBrandChecks(containerId, name, brands, checkedBrands, emptyMessage = "No brands available.") {
      const selected = new Set(checkedBrands || []);
      el(containerId).innerHTML = brands.length
        ? brands.map((brand) => `<label><input type="checkbox" name="${name}" value="${escapeHtml(brand)}" ${selected.has(brand) ? "checked" : ""}>${escapeHtml(brand)}</label>`).join("")
        : `<div class="report-status">${escapeHtml(emptyMessage)}</div>`;
      el(containerId).querySelectorAll("input").forEach((input) => input.addEventListener("change", () => {
        reportLoaded = false;
        loadReporting();
      }));
    }
let reportingMap = null;
let mapMarkerLayerGroup = null;
let stateBoundaryLayerGroup = null;
let staticMapZoom = 1;
const DEFAULT_US_MAP_VIEW = { center: [39.8283, -98.5795], zoom: 4 };
const DEFAULT_US_BOUNDS = [[24.3963, -125.0], [49.3844, -66.9346]];
const stateNameToCode = {
      Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA", Colorado: "CO", Connecticut: "CT", Delaware: "DE",
      Florida: "FL", Georgia: "GA", Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA", Kansas: "KS",
      Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD", Massachusetts: "MA", Michigan: "MI", Minnesota: "MN", Mississippi: "MS",
      Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
      "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH", Oklahoma: "OK", Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI",
      "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX", Utah: "UT", Vermont: "VT", Virginia: "VA",
      Washington: "WA", "West Virginia": "WV", Wisconsin: "WI", Wyoming: "WY", "District of Columbia": "DC"
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
      WI: [44.2685, -89.6165], WY: [42.756, -107.3025], DC: [38.9072, -77.0369]
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
/**
 * Resolve the active primary brand, preferring the dropdown value and falling
 * back to the first brand in a server-provided filters object.
 * @param {{main_brands?: string[]}} [fallbackFilters={}] - Filters echoed by the
 *   backend, used when the dropdown is empty.
 * @returns {string} The primary brand name, or "" if none is selected.
 */
function selectedPrimaryBrand(fallbackFilters = {}) {
      const fromSelect = el("reportMainBrandSelect")?.value || "";
      const fromFilters = Array.isArray(fallbackFilters.main_brands) ? (fallbackFilters.main_brands[0] || "") : "";
      return fromSelect || fromFilters;
    }
/**
 * Lazily fetch and memoize the US state boundaries as GeoJSON, converting the
 * bundled TopoJSON via `topojson-client`.
 * @returns {Promise<Object|null>} The states FeatureCollection, or `null` if the
 *   file or the `topojson` global is unavailable (map degrades gracefully).
 */
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
/**
 * Test whether a coordinate falls within continental US / territory bounds
 * (mirrors the backend's coordinate validation so off-US points are dropped).
 * @param {number} lat - Latitude.
 * @param {number} lon - Longitude.
 * @returns {boolean} True if the point is within US bounds.
 */
function isUSLatLong(lat, lon) {
      if (isNaN(lat) || isNaN(lon)) return false;
      if (lat < 13.0 || lat > 72.0) return false;
      const isWestUS = (lon >= -180.0 && lon <= -64.0);
      const isEastUSTerritory = (lon >= 144.0 && lon <= 146.0);
      return isWestUS || isEastUSTerritory;
    }
/**
 * Fallback map used when Leaflet is unavailable: render a static grid of US
 * states with per-state location counts and simple zoom controls.
 * @param {Array<{state: string, locations: number}>} [stateRecords=[]] - Per-state
 *   counts; defaults to the zeroed state list when empty.
 * @returns {void}
 */
function renderStaticUSMap(stateRecords = []) {
      const target = el("reportingMap");
      if (!target) return;
      const stateCounts = new Map((stateRecords.length ? stateRecords : defaultStateRecords).map((row) => [String(row.state || "").toUpperCase(), Number(row.locations || 0)]));
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
              return `<div class="static-state-cell" title="${escapeHtml(stateCodeToName[code] || code)}">${escapeHtml(stateCodeToName[code] || code)}<br>${formatNumber(stateCounts.get(code) || 0)}</div>`;
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
/**
 * Render the location map: state boundary choropleth plus markers for primary
 * brand, competitor, and whitespace-gap locations. Initializes Leaflet on first
 * call and falls back to {@link renderStaticUSMap} when Leaflet is absent. When
 * geo filters are active the view fits the plotted points; otherwise it fits the
 * whole US.
 * @param {Array<Object>} [mapRecords=[]] - Location rows with latitude/longitude/brand.
 * @param {Array<Object>} [gapRecords=[]] - Whitespace-candidate ZIP rows.
 * @param {Array<{state: string, locations: number, state_name?: string}>} [stateRecords=[]]
 *   - Per-state counts for boundary shading and default markers.
 * @param {{main_brands?: string[]}} [filters={}] - Active filters (used to
 *   determine the primary brand for marker coloring).
 * @returns {void}
 */
function renderReportingMap(mapRecords = [], gapRecords = [], stateRecords = [], filters = {}) {
      if (!el("reportingMap")) return;
      const displayStates = stateRecords.length ? stateRecords : defaultStateRecords;
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
      }
      mapMarkerLayerGroup.clearLayers();
      stateBoundaryLayerGroup.clearLayers();

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
              const hasData = boundaryStateCounts.has(code);
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
              layer.bindTooltip(code || feature.properties.name, { sticky: true, className: "state-code-label" });
              layer.bindPopup(`
                <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
                  <strong>${escapeHtml(feature.properties.name || code)}</strong><br/>
                  <span>${formatNumber(boundaryStateCounts.get(code) || 0)} ZIP locations</span>
                </div>
              `);
            }
          }).addTo(stateBoundaryLayerGroup);
        })
        .catch(() => {});

      if (!mapRecords.length && !gapRecords.length) {
        const states = (displayStates || []).filter((row) => stateCentroids[String(row.state || "").toUpperCase()]);
        states.forEach((row) => {
          const stateCode = String(row.state || "").toUpperCase();
          const [lat, lon] = stateCentroids[stateCode];
          bounds.push([lat, lon]);
          const marker = L.circleMarker([lat, lon], {
            radius: Math.max(8, Math.min(22, Math.sqrt(Number(row.locations || 0)) * 1.2)),
            fillColor: "#e7f0ff",
            color: "#2563eb",
            weight: 1.5,
            opacity: 0.9,
            fillOpacity: 0.85
          });
          marker.bindTooltip(stateCode || "??", {
            permanent: true,
            direction: "center",
            className: "state-code-label"
          });
          marker.bindPopup(`
            <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
              <strong>${escapeHtml(row.state_name || stateCodeToName[stateCode] || "Unknown State")}</strong><br/>
              <span>${formatNumber(row.locations)} ZIP location${Number(row.locations || 0) === 1 ? "" : "s"}</span>
            </div>
          `);
          mapMarkerLayerGroup.addLayer(marker);
        });
      }

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
        mapMarkerLayerGroup.addLayer(marker);
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
            <span><strong>Competitors Operating:</strong> ${escapeHtml(gap.brands_present || "")} (${gap.competitor_locations} store${gap.competitor_locations > 1 ? "s" : ""})</span><br/>
            <span><strong>Population:</strong> ${formatNumber(gap.population)}</span><br/>
            <span><strong>Median Income:</strong> ${gap.median_household_income ? "$" + formatNumber(gap.median_household_income) : "N/A"}</span><br/>
            <span><strong>Median Age:</strong> ${gap.median_age || "N/A"} yrs</span>
          </div>
        `);
        mapMarkerLayerGroup.addLayer(marker);
      });

      if (bounds.length && shouldFocusFilteredArea) {
        reportingMap.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
      } else {
        reportingMap.fitBounds(DEFAULT_US_BOUNDS, { padding: [18, 18], maxZoom: DEFAULT_US_MAP_VIEW.zoom });
      }
      setTimeout(() => reportingMap.invalidateSize(), 200);
    }
let brandDropdownsInitialized = false;
/**
 * Reconcile the brand dropdowns with the brand list in a fresh report payload,
 * repopulating the primary-brand `<select>` (preserving the current choice when
 * still valid), refreshing competitor options, and reloading geo options.
 * @param {{filter_options?: {brands?: string[]}}} result - The `/api/reporting`
 *   payload.
 * @returns {void}
 */
function syncReportingFilters(result) {
      const brands = result.filter_options?.brands || [];
      if (brands.join("|") !== reportingBrands.join("|") || !brandDropdownsInitialized) {
        reportingBrands = brands;
        const mainSel = el("reportMainBrandSelect");
        if (mainSel && brands.length) {
          const currentMain = brands.includes(mainSel.value) ? mainSel.value : "";
          mainSel.innerHTML = '<option value="">All Brands</option>' + brands.map((b) => `<option value="${escapeHtml(b)}"${b === currentMain ? " selected" : ""}>${escapeHtml(b)}</option>`).join("");
          mainSel.value = currentMain;
        } else if (mainSel) {
          mainSel.innerHTML = '<option value="">All Brands</option>';
        }
        updateCompetitorOptions();
        brandDropdownsInitialized = true;
      }
      loadGeoOptions();
    }
/**
 * Rebuild the competitor-brand checkbox list based on the chosen primary brand.
 * Excludes the primary brand, and when the primary brand was just changed,
 * defaults to selecting every other brand (the user can then narrow it down).
 * @returns {void}
 */
function updateCompetitorOptions() {
      const selectedMain = el("reportMainBrandSelect")?.value || "";
      // Exclude primary brand so same brand data is NEVER shown in competitor choices
      const competitorChoices = selectedMain ? reportingBrands.filter((b) => b !== selectedMain) : [];
      const currentlyChecked = new Set(checkedValues("competitorBrand"));

      // Picking a primary brand should default to comparing against every other
      // brand, same as the primary brand selector defaulting to "All Brands" -
      // the user can still narrow it down manually afterward.
      const isFreshMainBrandSelection = selectedMain && selectedMain !== competitorDefaultsAppliedForMainBrand;
      const defaultCompetitors = isFreshMainBrandSelection
        ? competitorChoices
        : competitorChoices.filter((b) => currentlyChecked.has(b));
      competitorDefaultsAppliedForMainBrand = selectedMain || null;

      // Distinguish "you haven't picked a primary brand yet" from "the data
      // genuinely has no other brands" - the old fixed "No brands available."
      // read like a data problem even when it just meant pick one first.
      const emptyMessage = selectedMain ? "No other brands available." : "Select a primary brand first.";
      renderBrandChecks("competitorBrandChecks", "competitorBrand", competitorChoices, defaultCompetitors, emptyMessage);
      updateCompetitorDropdownText();
    }
/**
 * Update the competitor dropdown's button label to reflect the current
 * selection ("Select Primary Brand", "N Competitors Selected", "All
 * Competitors Selected", etc.).
 * @returns {void}
 */
function updateCompetitorDropdownText() {
      const checked = checkedValues("competitorBrand");
      const btnText = el("competitorDropdownBtnText");
      if (!btnText) return;
      if (!el("reportMainBrandSelect")?.value) {
        btnText.textContent = "Select Primary Brand";
      } else if (checked.length === 0) {
        btnText.textContent = "Select Competitor Brands (0 selected)";
      } else if (checked.length === (reportingBrands.length ? reportingBrands.length - 1 : 0)) {
        btnText.textContent = "All Competitors Selected";
      } else {
        btnText.textContent = `${checked.length} Competitor${checked.length > 1 ? "s" : ""} Selected`;
      }
    }
/**
 * Attach one-time listeners for the brand controls: reload the report when the
 * primary brand changes, and open/close the competitor multi-select dropdown
 * (closing it on outside clicks).
 * @returns {void}
 */
function setupBrandDropdownListeners() {
      const mainSel = el("reportMainBrandSelect");
      if (mainSel) {
        mainSel.addEventListener("change", () => {
          updateCompetitorOptions();
          reportLoaded = false;
          loadReporting();
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
    }
/**
 * Fetch and repopulate the cascading geography dropdowns (states, counties,
 * cities) from `/api/geo/options`, scoped by the current state/county
 * selection. Preserves valid current selections and fails silently on error.
 * @returns {Promise<void>}
 */
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
      } catch (err) {}
    }
let zipTypeaheadTimer = null;
/**
 * Wire debounced ZIP typeahead: as the user types (>=2 chars), query
 * `/api/zips/search` (scoped by state/county/city) and fill the `<datalist>`
 * with suggestions. Debounced to 250ms; fails silently on error.
 * @returns {void}
 */
function setupZipTypeahead() {
      const zipInput = el("reportZipFilter");
      const datalist = el("zipSuggestions");
      if (!zipInput || !datalist) return;

      zipInput.addEventListener("input", () => {
        clearTimeout(zipTypeaheadTimer);
        const query = zipInput.value.trim();
        if (query.length < 2) return;
        zipTypeaheadTimer = setTimeout(async () => {
          const state = el("reportStateFilter")?.value || "";
          const county = el("reportCountyFilter")?.value || "";
          const city = el("reportCityFilter")?.value || "";
          try {
            const resp = await fetch(`/api/zips/search?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}&city=${encodeURIComponent(city)}`);
            const data = await resp.json();
            if (resp.ok && data.zips) {
              datalist.innerHTML = data.zips.map((z) => `<option value="${escapeHtml(z.zip_code)}">${escapeHtml(z.zip_code)} - ${escapeHtml(z.city_name)}, ${escapeHtml(z.state_name || stateCodeToName[z.state_code] || "")} (Pop: ${formatNumber(z.population)})</option>`).join("");
            }
          } catch (e) {}
        }, 250);
      });
    }
/**
 * Build the query string for `/api/reporting` from the current control values
 * (primary/competitor brands, geography, and demographic thresholds).
 * Competitor brands are de-duplicated against the primary brand.
 * Also exposed as `window.reportingQueryString` for `reporting.tabs.js`.
 * @returns {string} URL-encoded query string (without a leading "?").
 */
function reportingQueryString() {
      const params = new URLSearchParams();
      const mainBrand = el("reportMainBrandSelect")?.value || "";
      const competitorBrands = checkedValues("competitorBrand").filter((b) => b !== mainBrand);
      if (mainBrand) params.set("main_brands", mainBrand);
      if (competitorBrands.length) params.set("competitor_brands", competitorBrands.join(","));
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

/**
 * Main entry point: fetch `/api/reporting` with the current filters and render
 * the entire report - status line, KPI tiles, map, top-state cards, state/city
 * distributions, brand head-to-head, market gaps, empty states, and the sample
 * records table. On error, restores the empty skeleton and shows the message.
 * Sets `reportLoaded = true` on success. Exposed globally (called by
 * `switchView` and the reporting wiring).
 * @returns {Promise<void>}
 */
async function loadReporting() {
      const status = el("reportStatus");
      status.className = "report-status loading";
      status.innerHTML = '<span class="spinner"></span> Loading...';
      renderEmptyReportingStructure();
      try {
        const queryString = reportingQueryString();
        const response = await fetch(`/api/reporting${queryString ? `?${queryString}` : ""}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load reporting data.");
        syncReportingFilters(result);
        el("reportContent").classList.remove("hidden");
        const totals = result.totals || {};
        if (result.refreshing || result.warning) {
          status.className = "report-status";
          status.textContent = result.warning || "Updating.";
        } else {
          status.classList.add("hidden");
        }
        el("reportLocations").textContent = formatNumber(totals.active_market_locations);
        el("reportBrands").textContent = formatNumber(totals.total_brands);
        el("reportStates").textContent = formatNumber(totals.total_states);
        el("reportCities").textContent = formatNumber(totals.total_cities);
        if (el("reportZips")) el("reportZips").textContent = formatNumber(totals.total_zips);
        if (el("reportStores")) el("reportStores").textContent = formatNumber(totals.total_stores);
        if (el("reportBrandStates")) el("reportBrandStates").textContent = formatNumber(totals.active_brand_states);
        if (el("reportWhitespaceGaps")) el("reportWhitespaceGaps").textContent = formatNumber(result.primary_kpis?.gap_zips ?? (result.gaps || []).length);

        renderReportingMap(result.map_records || [], result.gaps || [], result.top_states || [], result.filters || {});

        const totalLocs = totals.total_locations || 1;

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
                    People per location: <strong>${ratioStr}</strong>. Population: ${popStr}
                  </p>
                </div>`;
              }).join("");
        }

        renderSimpleTable("reportTopStates", [
          { key: "state_name", label: "State / Territory" },
          { key: "locations", label: "ZIP Locations", format: formatNumber },
          {
            key: "pct",
            label: "Location Share",
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
            format: (v) => (v ? (v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : (v / 1e3).toFixed(0) + "K") : "N/A")
          },
          {
            key: "pop_per_store",
            label: "Population Per Location",
            format: (v, row) => {
              if (!row.state_population || !row.locations) return "N/A";
              const ratio = Math.round(row.state_population / row.locations);
              return ratio >= 1e3 ? (ratio / 1e3).toFixed(1) + "K" : ratio;
            }
          },
          { key: "cities", label: "Cities Covered", format: formatNumber }
        ], result.top_states || []);

        renderSimpleTable("reportTopCities", [
          { key: "city", label: "City" },
          { key: "state_name", label: "State / Territory" },
          { key: "locations", label: "ZIP Locations", format: formatNumber }
        ], result.top_cities || []);

        const primaryBrandName = selectedPrimaryBrand(result.filters || "");
        const brandRows = (result.brands || []).slice().sort((a, b) => {
          const aIsPrimary = primaryBrandName && a.brand === primaryBrandName;
          const bIsPrimary = primaryBrandName && b.brand === primaryBrandName;
          if (aIsPrimary !== bIsPrimary) return aIsPrimary ? -1 : 1;
          return Number(b.locations || 0) - Number(a.locations || 0);
        });
        const effectivePrimaryName = primaryBrandName || (brandRows[0] ? brandRows[0].brand : "");
        const primaryRow = brandRows.find((b) => b.brand === effectivePrimaryName) || brandRows[0];

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

        renderSimpleTable("reportGapsTable", [
          { key: "state_name", label: "State" },
          { key: "county", label: "County" },
          { key: "city", label: "City" },
          { key: "zip_code", label: "ZIP Code" },
          { key: "competitor_locations", label: "Competitor Stores", format: formatNumber },
          { key: "brands_present", label: "Competitor Brands" },
          { key: "population", label: "Census Population", format: (v) => (v ? formatNumber(v) : "N/A") },
          { key: "median_household_income", label: "Median Income", format: (v) => (v ? "$" + formatNumber(v) : "N/A") },
          { key: "median_age", label: "Median Age", format: (v) => (v ? v + " yrs" : "N/A") }
        ], result.gaps || []);

        const emptyStates = result.states_without_locations || [];
        el("reportEmptyStates").innerHTML = emptyStates.length
          ? emptyStates.map((state) => `<span>${escapeHtml(stateCodeToName[state] || state)}</span>`).join("")
          : '<div class="report-status">Every tracked state has at least one location.</div>';
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
        ], result.sample_records || []);
        status.classList.add("hidden");
        el("reportContent").classList.remove("hidden");
        reportLoaded = true;
      } catch (error) {
        renderEmptyReportingStructure();
        status.className = "report-status";
        status.textContent = productSafeError(error.message, "Could not load reporting data.");
      }
    }

/**
 * Trigger a server-side rebuild of the reporting data via
 * `POST /api/reporting/refresh` and report the row count (or an error) into the
 * refresh status element. Bound to the "Refresh Data" button in the mapper aside.
 * @returns {Promise<void>}
 */
async function refreshReportingData() {
      const target = el("reportingDataRefreshStatus");
      target.className = "action-feedback";
      target.textContent = "Refreshing...";
      try {
        const response = await fetch("/api/reporting/refresh", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not refresh data.");
        target.className = "action-feedback ok";
        target.textContent = `Data refreshed: ${result.rows} records.`;
      } catch (error) {
        target.className = "action-feedback error";
        target.textContent = productSafeError(error.message, "Could not refresh data.");
      }
    }
