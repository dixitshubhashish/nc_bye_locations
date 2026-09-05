// Mappings tab: source onboarding, brand/connector setup, mapping builder,
// draft save/restore, and save-to-warehouse logic.

let mappingTargets = [
      { key: "name", table: "listings", field: "name", label: "Restaurant Name", required: true, hints: ["name", "restaurantname", "storename", "displayname"] },
      { key: "address", table: "listings", field: "address", label: "Street Address", required: true, hints: ["address", "addressdescription", "line1", "street"] },
      { key: "city", table: "listings", field: "city_name", label: "City", required: true, hints: ["city", "town"] },
      { key: "state", table: "listings", field: "state_code", label: "State", required: true, hints: ["state", "region", "province", "state_code"] },
      { key: "postal_code", table: "listings", field: "zip_code", label: "ZIP Code", required: true, hints: ["zip", "zipcode", "zip_code", "postalcode", "postal_code"] },
      { key: "location_id", table: "listings", field: "location_key", label: "Location ID / Store ID", required: false, hints: ["locationid", "storeid", "store_id", "id", "number"] },
      { key: "town", table: "listings", field: "town", label: "Town", required: false, hints: ["town", "locality"] },
      { key: "province", table: "listings", field: "province", label: "Province", required: false, hints: ["province", "region"] },
      { key: "country", table: "listings", field: "country", label: "Country", required: false, hints: ["country", "countrycode"] },
      { key: "latitude", table: "listings", field: "latitude", label: "Latitude", required: false, hints: ["lat", "latitude"] },
      { key: "longitude", table: "listings", field: "longitude", label: "Longitude", required: false, hints: ["lng", "lon", "longitude"] },
      { key: "franchise_name", table: "listings", field: "franchise_name", label: "Franchise Name", required: false, hints: ["franchise", "franchisename"] },
      { key: "concept_type", table: "listings", field: "concept_type", label: "Concept Type", required: false, hints: ["concept", "concepttype"] },
      { key: "cuisine_type", table: "listings", field: "cuisine_type", label: "Cuisine Type", required: false, hints: ["cuisine", "cuisinetype"] },
      { key: "neighborhood", table: "listings", field: "neighborhood", label: "Neighborhood", required: false, hints: ["neighborhood"] },
      { key: "district", table: "listings", field: "district", label: "District", required: false, hints: ["district"] },
      { key: "phone_number", table: "listings", field: "phone_number", label: "Phone Number", required: false, hints: ["phone", "phonenumber", "telephone"] },
      { key: "website_url", table: "listings", field: "website_url", label: "Website URL", required: false, hints: ["website", "websiteurl", "url"] },
      { key: "google_maps_link", table: "listings", field: "google_maps_link", label: "Google Maps Link", required: false, hints: ["googlemaps", "mapsurl", "mapslink"] },
      { key: "social_media_handles", table: "listings", field: "social_media_handles", label: "Social Media Handles", required: false, hints: ["social", "socialmedia", "handles"] },
      { key: "operating_hours", table: "listings", field: "operating_hours", label: "Operating Hours", required: false, hints: ["hours", "operatinghours", "openhours"] },
      { key: "seating_capacity", table: "listings", field: "seating_capacity", label: "Seating Capacity", required: false, hints: ["seating", "capacity", "seatingcapacity"] },
      { key: "service_types", table: "listings", field: "service_types", label: "Service Types", required: false, hints: ["service", "servicetype", "services"] },
      { key: "opening_date", table: "listings", field: "opening_date", label: "Opening Date", required: false, hints: ["openingdate", "opendate"] },
      { key: "status", table: "listings", field: "status", label: "Status", required: false, hints: ["status", "storestatus"] },
      { key: "annual_revenue", table: "listings", field: "annual_revenue", label: "Annual Revenue", required: false, hints: ["revenue", "annualrevenue"] },
      { key: "average_ticket_size", table: "listings", field: "average_ticket_size", label: "Average Ticket Size", required: false, hints: ["ticket", "averageticket", "averageticketsize"] },
      { key: "daily_footfall", table: "listings", field: "daily_footfall", label: "Daily Footfall", required: false, hints: ["dailyfootfall", "dailytraffic"] },
      { key: "monthly_footfall", table: "listings", field: "monthly_footfall", label: "Monthly Footfall", required: false, hints: ["monthlyfootfall", "monthlytraffic"] },
      { key: "rental_cost", table: "listings", field: "rental_cost", label: "Rental Cost", required: false, hints: ["rent", "rentalcost"] },
      { key: "lease_cost", table: "listings", field: "lease_cost", label: "Lease Cost", required: false, hints: ["lease", "leasecost"] },
      { key: "population_density", table: "listings", field: "population_density", label: "Population Density", required: false, hints: ["density", "populationdensity"] },
      { key: "average_household_income", table: "listings", field: "average_household_income", label: "Average Household Income", required: false, hints: ["income", "householdincome", "averagehouseholdincome"] },
      { key: "competitor_count", table: "listings", field: "competitor_count", label: "Competitor Count", required: false, hints: ["competitors", "competitorcount"] },
      { key: "foot_traffic_score", table: "listings", field: "foot_traffic_score", label: "Foot Traffic Score", required: false, hints: ["foottraffic", "foottrafficscore"] },
      { key: "parking_availability", table: "listings", field: "parking_availability", label: "Parking Availability", required: false, hints: ["parking", "parkingavailability"] },
      { key: "observed_at", table: "listings", field: "first_observed_at", label: "Observed At", required: false, hints: ["observed_at", "updatedat", "updated_at", "last_seen"] }
    ];
const primaryMappingKeys = new Set(mappingTargets.slice(0, 20).map((target) => target.key));
const fieldDisplayOrder = [
      "name", "address", "city", "state", "postal_code", "location_id", "town", "province", "country",
      "latitude", "longitude", "franchise_name", "concept_type", "cuisine_type", "neighborhood", "district",
      "phone_number", "website_url", "google_maps_link", "social_media_handles", "operating_hours", "seating_capacity",
      "service_types", "opening_date", "status", "observed_at", "annual_revenue", "average_ticket_size", "daily_footfall",
      "monthly_footfall", "rental_cost", "lease_cost", "population_density", "average_household_income", "competitor_count",
      "foot_traffic_score", "parking_availability"
    ];
const fieldOrderIndex = new Map(fieldDisplayOrder.map((key, index) => [key, index]));
let optionalMappingKeys = new Set();
let hiddenMappingKeys = new Set();
let sourceRows = [];
let sourceFields = [];
let resolvedRecordPath = "";
let mappingSelections = {};
let jsonRecordPaths = [];
let autoMappedKeys = new Set();
let learnedSuggestions = {};
let sourceParsed = false;
let selectedBrand = null;
let csvFunctionMode = "new";
let jsonFunctionMode = "new";
let apiFunctionMode = "new";
let customAliases = {};
let lastSaveEventId = "";
let activeTemplateId = "";
let connectorEditor = null;
let pyodideRuntimePromise = null;

const draftStorageKey = "competitive_whitespace_mapping_draft";
const draftPreviewRowLimit = 10;
const saveBatchTargetBytes = 4 * 1024 * 1024;
const saveBatchMinRows = 250;

function normalizeName(value) {
      return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    }

function sourceTypeNameToFormat(name) {
      const normalized = normalizeName(name);
      if (normalized.includes("csv")) return "csv";
      if (normalized.includes("json")) return "json";
      if (normalized.includes("xls") || normalized.includes("excel")) return "excel";
      if (normalized.includes("xml")) return "xml";
      if (normalized.includes("api")) return "api_get_json";
      if (normalized.includes("openstreetmap") || normalized.includes("osm") || normalized.includes("python")) return "python_editor";
      return "";
    }
function sourceTypeIdToFormat(sourceTypeId) {
      const source = sourceTypes.find((item) => item.source_type_id === sourceTypeId);
      return sourceTypeNameToFormat(source?.name || "");
    }
function currentSourceTypeId() {
      const format = el("sourceType").value;
      const existing = sourceTypes.find((item) => item.name === format || sourceTypeNameToFormat(item.name) === format);
      return existing?.source_type_id || "";
    }
function setNewBusinessSourceType(format) {
      const match = Array.from(el("newBrandSourceType").options).find((option) => option.dataset.format === format || option.value === format);
      if (match) el("newBrandSourceType").value = match.value;
    }
function populateSourceTypeSelects() {
      const options = sourceTypes.length
        ? sourceTypes.map((source) => `<option value="${escapeHtml(source.source_type_id)}" data-format="${escapeHtml(sourceTypeNameToFormat(source.name))}">${escapeHtml(source.name)}</option>`).join("")
        : [
            ["csv", "CSV"],
            ["json", "JSON"],
            ["excel", "XLS"],
            ["api_get_json", "API"],
            ["python_editor", "OpenStreetMap"]
          ].map(([value, label]) => `<option value="${escapeHtml(value)}" data-format="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
      el("newBrandSourceType").innerHTML = `<option value="">Select source format</option>${options}`;
    }
function resetTemplateSelection() {
      activeTemplateId = "";
      el("templateSearch").value = "";
      el("templateResults").className = "status";
      el("templateResults").textContent = "Search saved templates to edit an existing mapping.";
    }
function applyBusinessSourceType(business) {
      const sourceTypeId = business?.source_type_id || "";
      const format = sourceTypeIdToFormat(sourceTypeId) || sourceTypeNameToFormat(business?.source_type_name || "");
      el("sourceType").disabled = Boolean(format);
      if (format) {
        el("sourceType").value = format;
        resetSourceInputsForNewMode(format);
        updateSourceVisibility();
      }
      el("templateBusinessFilter").value = business?.business_id || "";
      el("templateSourceFilter").value = sourceTypeId;
    }
async function refreshTemplatesForBusiness() {
      resetTemplateSelection();
      await loadTemplateLibrary();
    }

function setCustomFieldFeedback(message, type = "") {
      el("customFieldFeedback").className = `action-feedback ${type}`;
      el("customFieldFeedback").textContent = message;
    }
function setConnectorFeedback(message, type = "") {
      el("pythonConnectorFeedback").className = `action-feedback ${type}`;
      el("pythonConnectorFeedback").textContent = message;
    }
function getConnectorCode() {
      return connectorEditor ? connectorEditor.getValue() : el("pythonConnectorCode").value;
    }
function setConnectorCode(code) {
      if (connectorEditor) connectorEditor.setValue(code);
      else el("pythonConnectorCode").value = code;
    }
function dominosPythonCode() {
      const limit = window.APP_CONSTANTS.dominosZipFetchLimit || 1;
      const storesPerZip = window.APP_CONSTANTS.dominosStoresPerZipLimit || 1;
      const maxWorkers = window.APP_CONSTANTS.dominosMaxWorkers || 8;
      const provider = encodeURIComponent(window.APP_CONSTANTS.dominosProvider || "auto");
      const orderType = encodeURIComponent(window.APP_CONSTANTS.dominosOrderType || "Delivery");
      return `from pyodide.http import pyfetch
import json

response = await pyfetch("/api/dominos-source?limit=${limit}&stores_per_zip=${storesPerZip}&one_per_zip=true&max_workers=${maxWorkers}&provider=${provider}&type=${orderType}")
if response.status != 200:
    raise RuntimeError(await response.string())

result = json.loads(await response.string())`;
    }
function syncBrandSelection(brandConfig) {
      if (!brandConfig || !brandConfig.name) return;
      const brandName = brandConfig.name.trim();
      let brands = [];
      try {
        brands = JSON.parse(el("brandSelect").dataset.brands || "[]");
      } catch (e) {}

      const existing = brands.find((b) => b.name && b.name.toLowerCase() === brandName.toLowerCase());

      if (existing) {
        selectedBrand = existing;
        el("brandSelect").value = existing.business_id;
        el("newBrandFields").classList.add("hidden");
        applyBusinessSourceType(existing);
      } else {
        selectedBrand = null;
        el("brandSelect").value = "__create_new__";
        el("newBrandFields").classList.remove("hidden");
        setNewBusinessSourceType(el("sourceType").value);
        el("newBrandName").value = brandConfig.name || "";
        el("newBrandSlug").value = brandConfig.slug || "";
        el("newBrandDescription").value = brandConfig.description || "";
        el("newBrandLogo").value = "";
        el("newBrandWebsite").value = brandConfig.websiteUrl || "";
        el("newBrandStatus").value = brandConfig.status || "active";
        el("newBrandMetaTitle").value = brandConfig.metaTitle || "";
        el("newBrandMetaDescription").value = brandConfig.metaDescription || "";
        el("newBrandOrigin").value = brandConfig.countryOfOrigin || "";
      }
    }
function fillDominosBrand() {
      syncBrandSelection(window.APP_CONSTANTS.dominosBrand || {});
    }
function setDominosMappings() {
      mappingSelections = {
        location_id: "StoreID",
        name: "StoreName",
        address: "AddressDescription",
        city: "City",
        state: "Region",
        postal_code: "PostalCode",
        latitude: "Latitude",
        longitude: "Longitude",
        observed_at: "ObservedAt"
      };
      optionalMappingKeys = new Set(["location_id", "latitude", "longitude", "observed_at"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function setDominosLocked(locked) {
      setPresetLocked(false, []);
    }
function applyDominosPythonFunction() {
      el("sourceType").value = "python_editor";
      el("sourceName").value = "dominos_store_locator";
      el("recordPath").value = "Stores";
      el("pythonPackages").value = "";
      setConnectorCode(dominosPythonCode());
      fillDominosBrand();
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      renderMappings();
      updateOutput();
      updateSourceVisibility();
      setDominosLocked(false);
      setStatus("Domino's ready. Click Parse.", "ok");
    }
function updatePythonFunctionSelection(value) {
      if (value === "dominos") applyDominosPythonFunction();
      else setDominosLocked(false);
    }
function setLockedValue(id, value) {
      if (el(id)) el(id).value = value || "";
    }
function setPresetLocked(locked, controlIds) {
      // Keep all controls and mapping elements 100% enabled & fully editable
      (controlIds || []).forEach((id) => { if (el(id)) el(id).disabled = false; });
      ["newBrandName", "newBrandSlug", "newBrandDescription", "newBrandLogo", "newBrandWebsite", "newBrandStatus", "newBrandMetaTitle", "newBrandMetaDescription", "newBrandOrigin"].forEach((id) => { if (el(id)) el(id).disabled = false; });
      document.querySelectorAll("select[data-field]").forEach((select) => { select.disabled = false; });
      document.querySelectorAll("button[data-remove-field]").forEach((button) => { button.disabled = false; });
      if (el("addOptionalFieldBtn")) el("addOptionalFieldBtn").disabled = false;
      document.querySelector("aside .panel")?.classList.remove("locked-demo");
      el("mappingGrid")?.classList.remove("locked-demo");
    }
const sourceUrlPlaceholders = {
      csv: "https://example.com/locations.csv",
      json: "https://example.com/locations.json",
      excel: "https://example.com/locations.xls",
      xml: "https://example.com/locations.xml"
    };
function setSourceUrlLocked(locked) {
      el("sourceUrl").toggleAttribute("readonly", Boolean(locked));
      el("sourceUrl").classList.toggle("demo-url", Boolean(locked));
    }
function resetSourceInputsForNewMode(sourceType = el("sourceType").value) {
      setPresetLocked(false, []);
      setSourceUrlLocked(false);
      el("sourceUrl").value = "";
      el("sourceUrl").placeholder = sourceUrlPlaceholders[sourceType] || "https://example.com/locations.json";
      el("apiUrl").value = "";
      el("apiUrl").placeholder = sourceType === "api_get_json" ? "https://example.com/stores.json" : "https://example.com/locations.json";
      el("sourceName").value = "";
      el("recordPath").value = "";
      el("jsonRecordPath").innerHTML = '<option value="">Automatically select the best record layer</option>';
      el("sheetName").innerHTML = '<option value="">Upload Excel to load sheets</option>';
      el("sheetName").disabled = true;
      const editLink = el("sourceUrlEditLink");
      if (editLink) editLink.remove();
      sourceRows = [];
      sourceFields = [];
      jsonRecordPaths = [];
      resolvedRecordPath = "";
      sourceParsed = false;
      mappingSelections = {};
      autoMappedKeys = new Set();
      optionalMappingKeys = new Set();
      hiddenMappingKeys = new Set();
      renderMappings();
      updateOutput();
    }
function fillBrandFromConfig(brand) {
      syncBrandSelection(brand);
    }
function setPizzaHutMappings() {
      mappingSelections = {
        location_id: "id",
        name: "address",
        address: "address",
        city: "city",
        state: "state",
        postal_code: "zip",
        phone_number: "phone",
        latitude: "latitude",
        longitude: "longitude"
      };
      optionalMappingKeys = new Set(["location_id", "phone_number", "latitude", "longitude"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function setPizzaHutLocked(locked) {
      setPresetLocked(false, []);
    }
function applyPizzaHutCsvDemo() {
      csvFunctionMode = "pizza_hut";
      el("sourceType").value = "csv";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.pizzaHutCsvDemoUrl || "";
      setSourceUrlLocked(true);
      el("sourceName").value = "pizza_hut_locations_csv";
      el("recordPath").value = "";
      fillBrandFromConfig(window.APP_CONSTANTS.pizzaHutBrand || {});
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      updateSourceVisibility();
      renderMappings();
      setPizzaHutLocked(false);
      updateOutput();
      setStatus("Pizza Hut ready. Click Parse.", "ok");
    }
function setGlobalHotelsMappings() {
      mappingSelections = {
        location_id: "HotelId",
        name: "HotelName",
        address: "StreetAddress",
        city: "City",
        state: "StateProvince",
        postal_code: "PostalCode",
        latitude: "Latitude",
        longitude: "Longitude",
        country: "Country",
        status: "IsDeleted"
      };
      optionalMappingKeys = new Set(["location_id", "latitude", "longitude", "country", "status"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function applyGlobalHotelsCsvDemo() {
      csvFunctionMode = "global_hotels";
      el("sourceType").value = "csv";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.globalHotelsCorruptDemoUrl || "";
      setSourceUrlLocked(true);
      el("sourceName").value = "global_hotels_mixed_csv";
      el("recordPath").value = "";
      fillBrandFromConfig(window.APP_CONSTANTS.globalHotelsBrand || {});
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      updateSourceVisibility();
      renderMappings();
      setPresetLocked(false, []);
      updateOutput();
      setStatus("Global Hotels ready. Click Parse.", "warn");
    }
function resetCsvDemoLock() {
      csvFunctionMode = "new";
      resetSourceInputsForNewMode("csv");
    }
function updateCsvFunctionSelection(value) {
      if (value === "pizza_hut") applyPizzaHutCsvDemo();
      else if (value === "global_hotels") applyGlobalHotelsCsvDemo();
      else resetCsvDemoLock();
    }
function fillLaCityDemoBrand() {
      const brand = window.APP_CONSTANTS.laCityJsonDemoBrand || {};
      fillBrandFromConfig(brand);
    }
function setLaCityDemoLocked(locked) {
      setPresetLocked(false, []);
    }
function setLaCityDemoMappings() {
      mappingSelections = {
        location_id: "facility_id",
        name: "facility_name",
        address: "facility_address",
        city: "facility_city",
        state: "facility_state",
        postal_code: "facility_zip",
        status: "program_status",
        observed_at: "activity_date"
      };
      optionalMappingKeys = new Set(["location_id", "status", "observed_at"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function applyLaCityJsonDemo() {
      jsonFunctionMode = "la_city";
      el("sourceType").value = "json";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.laCityJsonDemoUrl || "";
      setSourceUrlLocked(true);
      el("sourceName").value = "la_city_restaurant_inspections_json";
      el("recordPath").value = "";
      fillLaCityDemoBrand();
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      updateSourceVisibility();
      renderMappings();
      setLaCityDemoLocked(false);
      updateOutput();
      setStatus("LA City ready. Click Parse.", "ok");
    }
function resetJsonDemoLock() {
      jsonFunctionMode = "new";
      resetSourceInputsForNewMode("json");
    }
function updateJsonFunctionSelection(value) {
      if (value === "la_city") applyLaCityJsonDemo();
      else resetJsonDemoLock();
    }
function setLittleCaesarsMappings() {
      mappingSelections = {
        location_id: "store_number",
        name: "store_name",
        address: "street_address",
        city: "city",
        state: "state_code",
        postal_code: "zip_code",
        phone_number: "phone",
        latitude: "lat",
        longitude: "lng"
      };
      optionalMappingKeys = new Set(["location_id", "phone_number", "latitude", "longitude"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function applyLittleCaesarsApiDemo() {
      apiFunctionMode = "little_caesars";
      el("sourceType").value = "api_get_json";
      el("apiUrl").value = window.APP_CONSTANTS.littleCaesarsApiDemoUrl || "";
      el("sourceName").value = "little_caesars_locations_api";
      el("recordPath").value = "locations";
      fillBrandFromConfig(window.APP_CONSTANTS.littleCaesarsBrand || {});
      setLittleCaesarsMappings();
      updateSourceVisibility();
      renderMappings();
      setPresetLocked(false, []);
      updateOutput();
      setStatus("Little Caesars ready.", "ok");
    }
function resetApiDemoLock() {
      apiFunctionMode = "new";
      resetSourceInputsForNewMode("api_get_json");
    }
function updateApiFunctionSelection(value) {
      if (value === "little_caesars") applyLittleCaesarsApiDemo();
      else resetApiDemoLock();
    }
function isNewSourceMode() {
      const sourceType = el("sourceType").value;
      return (
        sourceType === "csv" && csvFunctionMode === "new"
        || sourceType === "json" && jsonFunctionMode === "new"
        || sourceType === "api_get_json" && apiFunctionMode === "new"
        || !["csv", "json", "api_get_json"].includes(sourceType)
      );
    }
function initializeConnectorEditor() {
      if (!window.require) {
        setConnectorFeedback("Editor unavailable.", "error");
        return;
      }
      window.require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" } });
      window.require(["vs/editor/editor.main"], () => {
        connectorEditor = monaco.editor.create(el("pythonConnectorEditor"), {
          value: el("pythonConnectorCode").value,
          language: "python",
          theme: "vs",
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 13,
          tabSize: 4,
          insertSpaces: true,
          scrollBeyondLastLine: false
        });
        connectorEditor.onDidChangeModelContent(() => saveDraft());
        restoreDraft();
      });
    }
function openConnectorEditor() {
      const dialog = el("pythonConnectorDialog");
      if (!connectorEditor || typeof dialog.showModal !== "function") return;
      el("pythonConnectorDialogHost").appendChild(el("pythonConnectorEditor"));
      dialog.showModal();
      connectorEditor.layout();
      connectorEditor.focus();
    }
function minimizeConnectorEditor() {
      const dialog = el("pythonConnectorDialog");
      if (!connectorEditor) return;
      document.querySelector(".python-connector-field").insertBefore(el("pythonConnectorEditor"), document.querySelector(".python-connector-field .mapping-note"));
      dialog.close();
      connectorEditor.layout();
    }
function textToBase64(value) {
      const bytes = new TextEncoder().encode(value);
      let binary = "";
      bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
      return btoa(binary);
    }
async function loadConnectorPackages(pyodide, code) {
      const requested = el("pythonPackages").value.split(",").map((name) => name.trim()).filter(Boolean);
      if (/^\s*(?:from\s+requests\s+import|import\s+requests\b)/m.test(code) && !requested.includes("requests")) requested.push("requests");
      if (requested.length) {
        setConnectorFeedback("Loading packages...", "");
        await pyodide.loadPackage(requested);
      }
    }
async function runPythonConnector() {
      const code = getConnectorCode().trim();
      if (!code) throw new Error("Enter code first.");
      showLoadingOverlay("Running...", () => {
        setConnectorFeedback("Run cancelled.", "warn");
      });
      try {
        setConnectorFeedback("Loading runtime...", "");
        pyodideRuntimePromise ||= window.loadPyodide ? window.loadPyodide() : Promise.reject(new Error("Browser Python runtime could not be loaded."));
        const pyodide = await pyodideRuntimePromise;
        await loadConnectorPackages(pyodide, code);
        setConnectorFeedback("Running...", "");
        const output = await pyodide.runPythonAsync(`${code}\n\nimport json\njson.dumps(result)`);
        let value;
        try {
          value = JSON.parse(output);
        } catch (error) {
          throw new Error("Python result must be JSON-compatible.");
        }
        if (!Array.isArray(value) && (!value || typeof value !== "object")) {
          throw new Error("Return an object or list.");
        }
        el("pythonConnectorOutput").value = JSON.stringify(value, null, 2).slice(0, 50000);
        setConnectorFeedback("Output ready.", "ok");
        hideLoadingOverlay();
        return JSON.stringify(value);
      } catch (err) {
        hideLoadingOverlay();
        throw err;
      }
    }
let activeAbortController = null;

function saveDraft() {
      if (!sourceParsed) return;
      const sessionId = sessionStorage.getItem(mappingSessionStorageKey);
      if (!sessionId) return;
      const draft = {
        sessionId,
        sourceType: el("sourceType").value,
        csvFunction: document.querySelector("input[name='csvFunction']:checked")?.value || "new",
        jsonFunction: document.querySelector("input[name='jsonFunction']:checked")?.value || "new",
        brandSelect: el("brandSelect").value,
        selectedBrand,
        sourceName: el("sourceName").value,
        sourceInputMode: el("sourceInputMode").value,
        sourceUrl: el("sourceUrl").value,
        recordPath: el("recordPath").value,
        jsonRecordPaths,
        sheetName: el("sheetName").value,
        apiUrl: el("apiUrl").value,
        authType: el("authType").value,
        pythonFunction: document.querySelector("input[name='pythonFunction']:checked")?.value || "new",
        pythonConnectorCode: getConnectorCode(),
        pythonPackages: el("pythonPackages").value,
        sourceRowCount: sourceRows.length,
        sourcePreviewRows: sourceRows.slice(0, draftPreviewRowLimit),
        sourceFields,
        resolvedRecordPath,
        mappingSelections,
        autoMappedKeys: [...autoMappedKeys],
        optionalMappingKeys: [...optionalMappingKeys],
        hiddenMappingKeys: [...hiddenMappingKeys],
        customAliases,
        activeTemplateId
      };
      try {
        sessionStorage.setItem(draftStorageKey, JSON.stringify(draft));
      } catch (error) {
        const compactDraft = {
          ...draft,
          sourcePreviewRows: [],
          pythonConnectorCode: "",
          customAliases: {}
        };
        try {
          sessionStorage.setItem(draftStorageKey, JSON.stringify(compactDraft));
        } catch (secondError) {
          sessionStorage.removeItem(draftStorageKey);
        }
      }
    }
function restoreDraft() {
      try {
        const activeSession = sessionStorage.getItem(loginSessionStorageKey) === "true";
        const sessionId = sessionStorage.getItem(mappingSessionStorageKey);
        if (!activeSession || !sessionId) {
          sessionStorage.removeItem(draftStorageKey);
          return;
        }
        const draft = JSON.parse(sessionStorage.getItem(draftStorageKey) || "null");
        if (!draft) return;
        if (draft.sessionId !== sessionId) {
          sessionStorage.removeItem(draftStorageKey);
          return;
        }
        sourceRows = draft.sourcePreviewRows || [];
        sourceFields = draft.sourceFields || [];
        sourceParsed = Boolean(sourceRows.length && (!draft.sourceRowCount || draft.sourceRowCount <= sourceRows.length));
        resolvedRecordPath = draft.resolvedRecordPath || "";
        jsonRecordPaths = draft.jsonRecordPaths || [];
        mappingSelections = draft.mappingSelections || {};
        autoMappedKeys = new Set(draft.autoMappedKeys || []);
        optionalMappingKeys = new Set(draft.optionalMappingKeys || []);
        hiddenMappingKeys = new Set(draft.hiddenMappingKeys || []);
        customAliases = draft.customAliases || {};
        activeTemplateId = draft.activeTemplateId || "";
        csvFunctionMode = draft.csvFunction || "new";
        jsonFunctionMode = draft.jsonFunction || "new";
        el("sourceType").value = draft.sourceType || "csv";
        const csvFunctionOption = document.querySelector(`input[name='csvFunction'][value="${CSS.escape(csvFunctionMode)}"]`);
        if (csvFunctionOption) csvFunctionOption.checked = true;
        const jsonFunctionOption = document.querySelector(`input[name='jsonFunction'][value="${CSS.escape(jsonFunctionMode)}"]`);
        if (jsonFunctionOption) jsonFunctionOption.checked = true;
        el("sourceName").value = draft.sourceName || "";
        el("sourceInputMode").value = draft.sourceInputMode || "file";
        el("sourceUrl").value = draft.sourceUrl || "";
        el("recordPath").value = draft.recordPath || "";
        el("sheetName").value = draft.sheetName || "";
        el("apiUrl").value = draft.apiUrl || "";
        el("authType").value = draft.authType || "none";
        const pythonFunction = draft.pythonFunction || "new";
        const pythonFunctionOption = document.querySelector(`input[name='pythonFunction'][value="${CSS.escape(pythonFunction)}"]`);
        if (pythonFunctionOption) pythonFunctionOption.checked = true;
        setConnectorCode(draft.pythonConnectorCode || getConnectorCode());
        el("pythonPackages").value = draft.pythonPackages || "";
        updateAuthVisibility();
        updateSourceVisibility();
        populateJsonRecordPaths(jsonRecordPaths);
        selectedBrand = draft.selectedBrand || null;
        renderMappings();
        setPizzaHutLocked(csvFunctionMode === "pizza_hut");
        setLaCityDemoLocked(jsonFunctionMode === "la_city");
        setDominosLocked((draft.pythonFunction || "new") === "dominos");
        renderTable("sourcePreview", sourceRows.slice(0, 10).map((row) => flattenObject(row)));
        const restoredCount = draft.sourceRowCount ? ` ${formatNumber(draft.sourceRowCount)} parsed records were in the prior session; re-parse before saving if you need the full dataset in memory.` : "";
        setStatus(`Draft restored.${restoredCount}`, "ok");
      } catch (error) {
        sessionStorage.removeItem(draftStorageKey);
      }
    }

async function loadFieldRegistry() {
      try {
        const response = await fetch("/api/field-registry");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load field definitions.");
        if (Array.isArray(result.fields) && result.fields.length) mappingTargets = result.fields;
        if (sourceParsed) renderMappings();
        if (result.warning) setStatus(result.warning, "warn");
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not load field definitions."), "error");
      }
    }

function inferSourceType(fileName) {
      const lower = fileName.toLowerCase();
      if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) return "excel";
      if (lower.endsWith(".json") || lower.endsWith(".geojson")) return "json";
      if (lower.endsWith(".xml")) return "xml";
      return "csv";
    }
const sourceFileAccept = {
      csv: ".csv,text/csv",
      excel: ".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel",
      json: ".json,.geojson,application/json,application/geo+json",
      xml: ".xml,application/xml,text/xml"
    };
function updateFileAccept() {
      el("fileInput").accept = sourceFileAccept[el("sourceType").value] || "";
    }
function validateSelectedFileType(file) {
      const selectedType = el("sourceType").value;
      if (!sourceFileAccept[selectedType]) return;
      const inferredType = inferSourceType(file.name);
      if (inferredType !== selectedType) {
        throw new Error(`Selected source format is ${selectedType.toUpperCase()}. Choose a matching ${selectedType === "json" ? "JSON or GeoJSON" : selectedType.toUpperCase()} file.`);
      }
    }
function populateJsonRecordPaths(paths) {
      jsonRecordPaths = Array.isArray(paths) ? paths : [];
      const picker = el("jsonRecordPath");
      picker.innerHTML = '<option value="">Automatically select the best record layer</option>' + jsonRecordPaths
        .filter((path) => path)
        .map((path) => `<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`)
        .join("");
      picker.value = el("recordPath").value || "";
    }
function isExcelFile(file) {
      if (!file) return false;
      const lower = file.name.toLowerCase();
      return lower.endsWith(".xlsx") || lower.endsWith(".xls");
    }
function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    }
function addPairRow(targetId, keyPlaceholder, valuePlaceholder, key = "", value = "") {
      const row = document.createElement("div");
      row.className = "source-row";
      row.innerHTML = `
        <div>
          <label>Key</label>
          <input data-pair-key placeholder="${escapeHtml(keyPlaceholder)}" value="${escapeHtml(key)}">
        </div>
        <div>
          <label>Value</label>
          <input data-pair-value placeholder="${escapeHtml(valuePlaceholder)}" value="${escapeHtml(value)}">
        </div>
        <button class="secondary" type="button" title="Remove">X</button>
      `;
      row.querySelector("button").addEventListener("click", () => row.remove());
      el(targetId).appendChild(row);
    }
function collectPairs(targetId) {
      return Array.from(el(targetId).querySelectorAll(".source-row"))
        .map((row) => ({
          key: row.querySelector("[data-pair-key]").value.trim(),
          value: row.querySelector("[data-pair-value]").value.trim()
        }))
        .filter((pair) => pair.key);
    }
function collectAuth() {
      const type = el("authType").value;
      if (type === "bearer") {
        return { type, token: el("bearerToken").value.trim() };
      }
      if (type === "basic") {
        return { type, username: el("basicUser").value, password: el("basicPassword").value };
      }
      if (type === "api_key_header") {
        return { type, key_name: el("apiKeyName").value.trim(), key_value: el("apiKeyValue").value.trim() };
      }
      return { type: "none" };
    }
function updateAuthVisibility() {
      const authType = el("authType").value;
      document.querySelectorAll(".auth-field").forEach((field) => field.classList.add("hidden"));
      if (authType === "bearer") document.querySelector(".auth-bearer").classList.remove("hidden");
      if (authType === "basic") document.querySelector(".auth-basic").classList.remove("hidden");
      if (authType === "api_key_header") document.querySelector(".auth-api-key").classList.remove("hidden");
    }
function updateSourceVisibility() {
      const sourceType = el("sourceType").value;
      const isApi = sourceType === "api_get_json";
      const isPythonConnector = sourceType === "python_editor";
      const isExcel = sourceType === "excel";
      const isJson = sourceType === "json";
      const isCsv = sourceType === "csv";
      const hasRecordPath = ["json", "xml", "api_get_json", "python_editor"].includes(sourceType);
      const isFileSource = !isApi && !isPythonConnector;

      document.querySelectorAll(".api-field").forEach((field) => field.classList.toggle("hidden", !isApi));
      document.querySelectorAll(".api-function-field").forEach((field) => field.classList.toggle("hidden", !isApi));
      document.querySelectorAll(".csv-function-field").forEach((field) => field.classList.toggle("hidden", !isCsv));
      document.querySelectorAll(".json-function-field").forEach((field) => field.classList.toggle("hidden", !isJson));
      document.querySelectorAll(".python-connector-field").forEach((field) => field.classList.toggle("hidden", !isPythonConnector));
      document.querySelectorAll(".excel-field").forEach((field) => field.classList.toggle("hidden", !isExcel));
      document.querySelectorAll(".file-field").forEach((field) => field.classList.toggle("hidden", isApi || isPythonConnector));
      document.querySelectorAll(".file-upload-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || el("sourceInputMode").value !== "file"));
      document.querySelectorAll(".source-url-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || el("sourceInputMode").value !== "url"));
      document.querySelectorAll(".record-field").forEach((field) => field.classList.toggle("hidden", !hasRecordPath));
      document.querySelectorAll(".json-record-path-field").forEach((field) => field.classList.toggle("hidden", sourceType !== "json"));

      document.querySelector("main").classList.toggle("connector-active", isPythonConnector);

      updateFileAccept();
      el("fileInput").disabled = isApi || isPythonConnector;
      el("apiUrl").disabled = !isApi;
      el("sheetName").disabled = !isExcel || !el("sheetName").options.length;
      updateAuthVisibility();
    }

function suggestField(target, usedFields = new Set()) {
      const learned = learnedSuggestions[target.key]?.source;
      if (learned && sourceFields.includes(learned) && !usedFields.has(learned)) return learned;
      const normalizedFields = sourceFields.map((field) => ({ field, clean: normalizeName(field) }));
      const hints = [...(target.hints || []), ...(customAliases[target.key] || [])];
      for (const hint of hints) {
        const exact = normalizedFields.find((entry) => entry.clean === normalizeName(hint));
        if (exact && !usedFields.has(exact.field)) return exact.field;
      }
      for (const hint of hints) {
        const cleanHint = normalizeName(hint);
        const partial = normalizedFields.find((entry) => !usedFields.has(entry.field) && (entry.clean.includes(cleanHint) || cleanHint.includes(entry.clean)));
        if (partial) return partial.field;
      }
      return "";
    }
function sampleValue(path) {
      for (const row of sourceRows.slice(0, 10)) {
        const value = getByPath(row, path);
        if (value !== undefined && value !== null && value !== "") return String(value);
      }
      return "";
    }
function renderMappings() {
      const grid = el("mappingGrid");
      grid.innerHTML = `
        <div class="mapping-head">Business Field</div>
        <div class="mapping-head">Source field path</div>
        <div class="mapping-head">Sample value</div>
        <div class="mapping-head"> </div>
      `;
      const visibleTargets = getVisibleTargets();
      const usedFields = new Set();
      // Only apply automatic field suggestions after source has been parsed
      if (sourceParsed) {
        const suggestionTargets = [...visibleTargets.filter((target) => target.required), ...visibleTargets.filter((target) => !target.required)];
        suggestionTargets.forEach((target) => {
          if (!Object.prototype.hasOwnProperty.call(mappingSelections, target.key)) {
            const selected = sourceFields.length ? suggestField(target, usedFields) : "";
            mappingSelections[target.key] = selected;
            if (selected) autoMappedKeys.add(target.key);
          }
          if (mappingSelections[target.key]) usedFields.add(mappingSelections[target.key]);
        });
      } else {
        // Still need to populate usedFields from existing mappings when not parsed
        visibleTargets.forEach((target) => {
          if (mappingSelections[target.key]) usedFields.add(mappingSelections[target.key]);
        });
      }
      visibleTargets.forEach((target) => {
        const hasSelection = Object.prototype.hasOwnProperty.call(mappingSelections, target.key);
        const selected = hasSelection ? mappingSelections[target.key] : "";
        if (selected) usedFields.add(selected);
        const availableOptionsList = [...sourceFields];
        if (selected && !availableOptionsList.includes(selected)) {
          availableOptionsList.push(selected);
        }
        const options = ['<option value="">Unmapped</option>']
          .concat(availableOptionsList.map((sourceField) => {
            const owner = Object.entries(mappingSelections).find(([, value]) => value === sourceField);
            const ownerLabel = owner ? mappingTargets.find((item) => item.key === owner[0])?.label : "";
            const title = ownerLabel ? ` title="Already mapped to ${escapeHtml(ownerLabel)}"` : "";
            return `<option value="${escapeHtml(sourceField)}"${title}>${escapeHtml(sourceField)}${ownerLabel ? " &#10003;" : ""}</option>`;
          }))
          .join("");
        grid.insertAdjacentHTML("beforeend", `
          <div>${target.label} ${target.required ? '<span class="required">*</span>' : ''}</div>
          <select data-field="${target.key}" class="${selected && autoMappedKeys.has(target.key) ? 'auto-mapped' : ''}">${options}</select>
          <div data-sample="${target.key}">${escapeHtml(selected ? sampleValue(selected) : "")}</div>
          <div>${target.required ? '' : `<button class="secondary mapping-remove" type="button" data-remove-field="${target.key}" title="Remove field" aria-label="Remove ${escapeHtml(target.label)}">&#128465;</button>`}</div>
        `);
        const select = grid.querySelector(`select[data-field="${target.key}"]`);
        select.value = selected;
      });
      grid.querySelectorAll("select").forEach((select) => {
        select.addEventListener("change", () => {
          const key = select.dataset.field;
          const nextValue = select.value;
          const previousOwner = Object.entries(mappingSelections).find(([otherKey, value]) => otherKey !== key && value === nextValue);
          if (nextValue && previousOwner) {
            const previousTarget = mappingTargets.find((target) => target.key === previousOwner[0]);
            const currentTarget = mappingTargets.find((target) => target.key === key);
            const move = window.confirm(`${nextValue} is already mapped to ${previousTarget.label}. Move it to ${currentTarget.label}?\n\nChoose Cancel to keep it mapped to ${previousTarget.label}.`);
            if (!move) {
              select.value = mappingSelections[key] || "";
              return;
            }
            mappingSelections[previousOwner[0]] = "";
            autoMappedKeys.delete(previousOwner[0]);
            const previousSelect = grid.querySelector(`select[data-field="${previousOwner[0]}"]`);
            if (previousSelect) {
              previousSelect.value = "";
              previousSelect.classList.remove("auto-mapped");
              grid.querySelector(`[data-sample="${previousOwner[0]}"]`).textContent = "";
            }
            setStatus(`Moved ${nextValue} from ${previousTarget.label} to ${currentTarget.label}.`, "warn");
          }
          mappingSelections[key] = nextValue;
          autoMappedKeys.delete(key);
          renderMappings();
        });
      });
      grid.querySelectorAll("button[data-remove-field]").forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.dataset.removeField;
          mappingSelections[key] = "";
          autoMappedKeys.delete(key);
          optionalMappingKeys.delete(key);
          if (primaryMappingKeys.has(key)) hiddenMappingKeys.add(key);
          renderMappings();
        });
      });
      updateOptionalFieldPicker();
      updateDropCustomFieldPicker();
      updateOutput();
    }
function updateOptionalFieldPicker() {
      const picker = el("optionalFieldSelect");
      const available = mappingTargets.filter((target) => !target.required && ((primaryMappingKeys.has(target.key) && hiddenMappingKeys.has(target.key)) || (!primaryMappingKeys.has(target.key) && !optionalMappingKeys.has(target.key))));
      picker.innerHTML = '<option value="">Choose a field</option>' + available
        .map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)}</option>`)
        .join("");
      el("addOptionalFieldBtn").disabled = available.length === 0;
    }
function updateDropCustomFieldPicker() {
      const picker = el("dropCustomFieldSelect");
      if (!picker) return;
      const businessId = selectedBrand?.business_id || "";
      const removable = mappingTargets.filter((target) => target.is_custom && target.business_id === businessId);
      picker.innerHTML = '<option value="">Choose a custom field</option>' + removable
        .map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)}</option>`)
        .join("");
      const button = el("dropCustomFieldBtn");
      if (button) button.disabled = removable.length === 0;
    }
async function dropCustomField() {
      const fieldKey = el("dropCustomFieldSelect").value;
      if (!fieldKey) {
        setDropCustomFieldFeedback("Choose a custom field to remove.", "warn");
        return;
      }
      try {
        const response = await fetch("/api/custom-field/delete", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            field_key: fieldKey,
            password: el("dropCustomFieldPassword").value,
            business_id: selectedBrand?.business_id || ""
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not remove custom field.");
        await loadFieldRegistry();
        updateOptionalFieldPicker();
        updateDropCustomFieldPicker();
        el("dropCustomFieldPassword").value = "";
        setDropCustomFieldFeedback(`Custom field ${result.label || fieldKey} removed.`, "ok");
      } catch (error) {
        setDropCustomFieldFeedback(productSafeError(error.message, "Could not remove custom field."), "error");
      }
    }
function setDropCustomFieldFeedback(message, type = "") {
      const target = el("dropCustomFieldFeedback");
      if (!target) return;
      target.className = `action-feedback ${type}`;
      target.textContent = message;
    }
function getVisibleTargets() {
      const seenKeys = new Set();
      const result = [];
      const standardTargets = mappingTargets
        .filter((target) => primaryMappingKeys.has(target.key) && !hiddenMappingKeys.has(target.key))
        .sort((left, right) => (fieldOrderIndex.get(left.key) ?? Number.MAX_SAFE_INTEGER) - (fieldOrderIndex.get(right.key) ?? Number.MAX_SAFE_INTEGER));
      for (const target of standardTargets) {
        if (target && !seenKeys.has(target.key)) {
          seenKeys.add(target.key);
          result.push(target);
        }
      }
      const optionalTargets = [...optionalMappingKeys]
        .map((key) => mappingTargets.find((target) => target.key === key))
        .filter(Boolean);
      for (const target of optionalTargets) {
        if (target && !seenKeys.has(target.key)) {
          seenKeys.add(target.key);
          result.push(target);
        }
      }
      return result;
    }
function getMapper() {
      const fields = {};
      document.querySelectorAll("select[data-field]").forEach((select) => {
        if (select.value) fields[select.dataset.field] = select.value;
      });
      const mapper = {
        brand: selectedBrand?.name || "",
        business_id: selectedBrand?.business_id || "",
        source_type_id: selectedBrand?.source_type_id || currentSourceTypeId(),
        source_name: el("sourceName").value.trim(),
        source_type: el("sourceType").value,
        fields,
        aliases: customAliases
      };
      if (el("sourceInputMode").value === "url" && el("sourceUrl").value.trim()) {
        mapper.source_url = el("sourceUrl").value.trim();
      }
      const recordPath = el("recordPath").value.trim() || resolvedRecordPath;
      if (recordPath && ["json", "xml", "excel", "api_get_json", "python_editor"].includes(el("sourceType").value)) {
        mapper.record_path = recordPath;
      }
      if (el("sourceType").value === "api_get_json") {
        mapper.api_request = {
          method: "GET",
          url: el("apiUrl").value.trim(),
          query_params: collectPairs("queryParams"),
          headers: collectPairs("customHeaders"),
          auth: collectAuth()
        };
      }
      if (el("sourceType").value === "python_editor") {
        mapper.python_editor = { code: getConnectorCode() };
      }
      return mapper;
    }
async function loadBrands(search = "") {
      try {
        const response = await fetch(`/api/brands?search=${encodeURIComponent(search)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load brands.");
        const brands = result.brands || [];
        el("brandSelect").innerHTML = '<option value="">Select an existing business</option><option class="create-new-option" value="__create_new__">+ Create New Business</option>' + brands.map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(brand.name)}</option>`).join("");
        el("brandSelect").dataset.brands = JSON.stringify(brands);
        if (selectedBrand) el("brandSelect").value = selectedBrand.business_id;
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not load businesses."), "error");
      }
    }
async function createNewBrand() {
      const name = el("newBrandName").value.trim();
      if (!name) { setStatus("Brand name is required.", "warn"); return; }
      const sourceTypeId = el("newBrandSourceType").value;
      const selectedSourceOption = el("newBrandSourceType").selectedOptions[0];
      const sourceType = selectedSourceOption?.dataset.format || sourceTypeNameToFormat(selectedSourceOption?.textContent || "") || el("sourceType").value;
      if (!sourceTypeId) { setStatus("Source format is required.", "warn"); return; }
      try {
        const response = await fetch("/api/brands", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
          name, source_type_id: sourceTypeId, source_type: sourceType, slug: el("newBrandSlug").value.trim(), description: el("newBrandDescription").value.trim(), logo_url: el("newBrandLogo").value.trim(), website_url: el("newBrandWebsite").value.trim(), status: el("newBrandStatus").value, meta_title: el("newBrandMetaTitle").value.trim(), meta_description: el("newBrandMetaDescription").value.trim(), country_of_origin: el("newBrandOrigin").value.trim()
        }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not create brand.");
        selectedBrand = result.brand;
        el("brandSelect").value = selectedBrand.business_id;
        await loadBrands(selectedBrand.name);
        el("brandSelect").value = selectedBrand.business_id;
        el("newBrandFields").classList.add("hidden");
        applyBusinessSourceType(selectedBrand);
        await refreshTemplatesForBusiness();
        setStatus(`Brand ${selectedBrand.name} is ready for mapping.`, "ok");
        updateOutput();
      } catch (error) { setStatus(productSafeError(error.message, "Could not create business."), "error"); }
    }
function normalizedRows() {
      const mapper = getMapper();
      return sourceRows.slice(0, 10).map((row, index) => {
        const out = { brand: mapper.brand };
        mappingTargets.forEach((target) => {
          const path = mapper.fields[target.key];
          out[`${target.table}.${target.field}`] = path ? getByPath(row, path) : "";
        });
        if (!out["restaurants.location_key"]) {
          out["restaurants.location_key"] = `${normalizeName(mapper.brand) || "brand"}:${out["restaurants.zip_code"] || "zip"}:${index + 1}`;
        }
        return out;
      });
    }
function validateMapper(mapper) {
      if (!sourceParsed || !sourceFields.length || !Object.keys(mappingSelections).length) return;
      const missing = mappingTargets.filter((target) => target.required && !mapper.fields[target.key]).map((target) => target.label);
      if (!mapper.brand) missing.unshift("brand");
      if (missing.length) {
        setStatus(`Missing required mapping: ${missing.join(", ")}`, "warn");
      } else if (mappingTargets.filter((target) => (primaryMappingKeys.has(target.key) && !hiddenMappingKeys.has(target.key)) || optionalMappingKeys.has(target.key)).every((target) => mapper.fields[target.key])) {
        setStatus(`Parsed ${sourceRows.length} records with ${sourceFields.length} source fields.`, "ok");
      } else {
        setStatus(`Parsed ${sourceRows.length} records with ${sourceFields.length} source fields.`, "ok");
      }
    }
function updateOutput() {
      const mapper = getMapper();
      const mappedSourceFields = new Set(Object.values(mapper.fields).filter(Boolean));
      const coverage = sourceFields.length ? Math.round(mappedSourceFields.size / sourceFields.length * 100) : 0;
      const percentage = el("mappingPercentage");
      percentage.textContent = `${coverage}%`;
      percentage.className = `mapping-percentage ${coverage < 50 ? "low" : coverage <= 75 ? "medium" : "high"}`;
      el("saveBtn").disabled = !sourceParsed || coverage < 50;
      el("saveActionWrap").dataset.tooltip = !sourceParsed || coverage < 50
        ? "Map at least 50% before saving."
        : "Ready to save.";
      el("mappingCoverageDetail").textContent = sourceFields.length ? `${mappedSourceFields.size} of ${sourceFields.length} columns mapped` : "Parse to measure coverage.";
      el("mapperOutput").value = JSON.stringify(mapper, null, 2);
      validateMapper(mapper);
      renderEntityMap();
      saveDraft();
    }
function renderEntityMap() {
      const target = el("entityPreview");
      const visibleTargets = getVisibleTargets();
      const mappedSourceFields = new Set(Object.values(mappingSelections).filter(Boolean));
      const entityNames = {
        listings: "Listings",
        workflow_templates: "Templates",
        source_types: "Source Types"
      };
      const groupedTargets = visibleTargets.reduce((groups, item) => {
        (groups[item.table] ||= []).push(item);
        return groups;
      }, {});
      const sourceItems = sourceFields.map((field) => `
        <div class="entity-field">
          <div class="entity-field-name">${escapeHtml(field)}</div>
          <div class="entity-field-source ${mappedSourceFields.has(field) ? "mapped" : "unmapped"}">${mappedSourceFields.has(field) ? "&#10003; Mapped" : "Unmapped"}</div>
        </div>
      `).join("");
      const entityItems = Object.entries(groupedTargets).map(([table, fields]) => `
        <div class="entity-box">
          <div class="entity-title">${escapeHtml(entityNames[table] || table)}</div>
          <div class="entity-subtitle">Fields received from the source</div>
          <div class="entity-fields">${fields.map((item) => {
            const source = mappingSelections[item.key];
            return `<div class="entity-field"><div class="entity-field-name">${escapeHtml(item.label)}</div><div class="entity-field-source ${source ? "mapped" : "unmapped"}">${source ? `&#8592; ${escapeHtml(source)}` : "Unmapped"}</div></div>`;
          }).join("")}</div>
        </div>
      `).join("");
      target.innerHTML = `
        <div class="entity-map">
          <div class="entity-column">
            <div class="entity-box">
              <div class="entity-title">Source Fields</div>
              <div class="entity-subtitle">Available fields from the parsed source</div>
              <div class="entity-fields">${sourceItems || '<div class="entity-field-source unmapped">Parse a source to view fields.</div>'}</div>
            </div>
          </div>
          <div class="entity-column">${entityItems || '<div class="status">Parse a source to view the data model.</div>'}</div>
        </div>
      `;
    }
function renderTable(targetId, rows) {
      const target = el(targetId);
      if (!rows.length) {
        target.innerHTML = "";
        return;
      }
      const sourceColumns = Object.keys(flattenObject(rows[0]));
      const mappedColumns = new Map(Object.entries(mappingSelections).filter(([, source]) => source));
      const columns = ["__brand", ...sourceColumns].sort((left, right) => {
        if (left === "__brand") return -1;
        if (right === "__brand") return 1;
        const leftTarget = [...mappedColumns.entries()].find(([, source]) => source === left)?.[0];
        const rightTarget = [...mappedColumns.entries()].find(([, source]) => source === right)?.[0];
        const leftOrder = leftTarget ? (fieldOrderIndex.get(leftTarget) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
        const rightOrder = rightTarget ? (fieldOrderIndex.get(rightTarget) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER;
        return leftOrder - rightOrder || sourceColumns.indexOf(left) - sourceColumns.indexOf(right);
      });
      const columnHeaders = columns.map((column) => {
        if (column === "__brand") return "Brand Name";
        const target = Object.entries(mappingSelections).find(([, source]) => source === column);
        const targetDefinition = target && mappingTargets.find((item) => item.key === target[0]);
        return targetDefinition
          ? `<span class="source-column-standard">${escapeHtml(targetDefinition.label)}</span><span class="source-column-name">[${escapeHtml(column)}]</span>`
          : escapeHtml(column);
      });
      const body = rows.map((row) => {
        const flat = flattenObject(row);
        return `<tr>${columns.map((col) => `<td>${escapeHtml(col === "__brand" ? (selectedBrand?.name || "") : flat[col] ?? "")}</td>`).join("")}</tr>`;
      }).join("");
      target.innerHTML = `
        <table>
          <thead><tr>${columnHeaders.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      `;
    }
function buildSaveBatches(rows, mapper, sourceFields) {
      const overhead = JSON.stringify({ mapper, rows: [], source_fields: sourceFields }).length + 512;
      const batches = [];
      let currentRows = [];
      let currentBytes = overhead;
      let rowOffset = 0;
      rows.forEach((row, index) => {
        const rowBytes = JSON.stringify(row).length + 2;
        const shouldFlush = currentRows.length >= saveBatchMinRows && currentBytes + rowBytes > saveBatchTargetBytes;
        if (shouldFlush) {
          batches.push({ rowOffset, rows: currentRows });
          rowOffset = index;
          currentRows = [];
          currentBytes = overhead;
        }
        currentRows.push(row);
        currentBytes += rowBytes;
      });
      if (currentRows.length) batches.push({ rowOffset, rows: currentRows });
      return batches.length ? batches : [{ rowOffset: 0, rows: [] }];
    }
async function parseSource() {
      setStatus("Reading your source...", "");
      try {
        const file = el("fileInput").files[0];
        let sourceType = el("sourceType").value;
        const payload = {
          source_type: sourceType,
          record_path: el("recordPath").value.trim()
        };
        if (sourceType === "api_get_json") {
          if (!el("apiUrl").value.trim()) throw new Error("Enter a GET API URL.");
          payload.api_url = el("apiUrl").value.trim();
          payload.query_params = collectPairs("queryParams");
          payload.headers = Object.fromEntries(collectPairs("customHeaders").map((pair) => [pair.key, pair.value]));
          payload.auth = collectAuth();
        } else if (sourceType === "python_editor") {
          payload.source_type = "json";
          payload.content_base64 = textToBase64(await runPythonConnector());
        } else if (el("sourceInputMode").value === "url") {
          const sourceUrl = el("sourceUrl").value.trim();
          if (!sourceUrl) throw new Error("Enter a public source URL.");
          const sourceResponse = await fetch("/api/source-url", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ url: sourceUrl })
          });
          const sourceResult = await sourceResponse.json();
          if (!sourceResponse.ok) throw new Error(sourceResult.error || "Could not fetch the public source URL.");
          if (sourceResult.warning) setStatus(sourceResult.warning, "warn");
          payload.file_name = sourceResult.file_name || "remote_source";
          payload.content_base64 = sourceResult.content_base64;
        } else {
          if (!file) throw new Error("Choose a source file.");
          validateSelectedFileType(file);
          payload.source_type = sourceType;
          payload.file_name = file.name;
          payload.content_base64 = await fileToBase64(file);
          if (sourceType === "excel" && el("sheetName").value) {
            payload.record_path = el("sheetName").value;
          }
        }
        const response = await fetch("/api/preview", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Preview failed.");
        sourceRows = result.rows || [];
        sourceFields = [...new Set((result.fields || []).filter((field) => field !== null && field !== undefined && String(field).trim()))];
        jsonRecordPaths = result.record_paths || [];
        sourceParsed = true;
        populateJsonRecordPaths(jsonRecordPaths);
        learnedSuggestions = {};
        try {
          const learningResponse = await fetch("/api/learning", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ source_type: sourceType, source_fields: sourceFields })
          });
          if (learningResponse.ok) learnedSuggestions = (await learningResponse.json()).suggestions || {};
        } catch (learningError) {
          learnedSuggestions = {};
        }
        resolvedRecordPath = result.record_path || "";
        mappingSelections = {};
        activeTemplateId = "";
        autoMappedKeys = new Set();
        if (csvFunctionMode === "pizza_hut") setPizzaHutMappings();
        else if (csvFunctionMode === "global_hotels") setGlobalHotelsMappings();
        else if (jsonFunctionMode === "la_city") setLaCityDemoMappings();
        else if (document.querySelector("input[name='pythonFunction']:checked")?.value === "dominos") setDominosMappings();
        sessionStorage.removeItem(draftStorageKey);
        if (resolvedRecordPath && !el("recordPath").value.trim()) el("recordPath").value = resolvedRecordPath;
        if (sourceType === "excel" && resolvedRecordPath) el("sheetName").value = resolvedRecordPath;
        renderMappings();
        if (csvFunctionMode === "pizza_hut") setPizzaHutLocked(true);
        if (jsonFunctionMode === "la_city") setLaCityDemoLocked(true);
        if (document.querySelector("input[name='pythonFunction']:checked")?.value === "dominos") setDominosLocked(true);
        renderTable("sourcePreview", sourceRows.slice(0, 10).map((row) => flattenObject(row)));
      } catch (error) {
        sourceRows = [];
        sourceFields = [];
        sourceParsed = false;
        setStatus(productSafeError(error.message, "Preview failed."), "error");
      }
    }
async function loadExcelSheets() {
      const file = el("fileInput").files[0];
      el("sheetName").innerHTML = '<option value="">Upload Excel to load sheets</option>';
      el("sheetName").disabled = true;
      if (!isExcelFile(file)) return;
      try {
        const payload = {
          file_name: file.name,
          content_base64: await fileToBase64(file)
        };
        const response = await fetch("/api/sheets", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load sheets.");
        const sheets = result.sheets || [];
        el("sheetName").innerHTML = sheets.map((sheet) => `<option value="${escapeHtml(sheet)}">${escapeHtml(sheet)}</option>`).join("");
        el("sheetName").disabled = sheets.length === 0;
        if (sheets.length) {
          el("recordPath").value = sheets[0];
          setStatus(`Loaded ${sheets.length} Excel sheet${sheets.length === 1 ? "" : "s"}.`, "ok");
        }
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not load sheets."), "error");
      }
    }
async function loadSampleDataset(reset = false) {
      const button = el("loadSampleDatasetBtn");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!reset && button?.dataset.sampleLoaded === "true") return;
      if (button) button.disabled = true;
      if (reloadLink) reloadLink.disabled = true;
      const status = el("reportStatus");
      status.classList.add("hidden");
      status.textContent = "";
      const estimatedSeconds = reset ? 80 : 50;
      const startedAt = Date.now();
      showLoadingOverlay(reset ? "Clearing and reloading sample dataset (0%)" : "Loading sample dataset (0%)", `About ${estimatedSeconds}s left.`);
      const progressTimer = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000);
        const percent = Math.min(94, Math.round(elapsed / estimatedSeconds * 100));
        const remaining = Math.max(1, estimatedSeconds - elapsed);
        updateLoadingOverlay(
          reset ? `Clearing and reloading sample dataset (${percent}%)` : `Loading sample dataset (${percent}%)`,
          `About ${remaining}s left.`
        );
      }, 1000);
      try {
        const response = await fetch("/api/sample/load", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ reset }),
          signal: activeAbortController?.signal
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load sample dataset.");
        updateLoadingOverlay(reset ? "Clearing and reloading sample dataset (100%)" : "Loading sample dataset (100%)", "Finishing report.");
        await loadBrands();
        await loadTemplateFilters();
        reportLoaded = false;
        await loadReporting();
        const sourceTypesSummary = Object.entries(result.source_types || {}).map(([name, count]) => `${name}: ${count}`).join(", ");
        const reportingRows = result.silver?.rows;
        const message = result.already_loaded
          ? `Sample dataset already loaded${reportingRows !== undefined ? `, ${formatNumber(reportingRows)} records ready` : ""}.`
          : `Sample dataset loaded: ${formatNumber(result.locations)} records, ${formatNumber(result.errors)} in review${reportingRows !== undefined ? `, ${formatNumber(reportingRows)} ready for reporting` : ""}${sourceTypesSummary ? ` (${sourceTypesSummary})` : ""}.`;
        status.className = "report-status";
        status.textContent = message;
        status.classList.remove("hidden");
        setStatus(message, "ok");
        updateSampleDatasetControls(result);
      } catch (error) {
        status.className = "report-status";
        const message = error.name === "AbortError" ? "Cancelled. No changes." : productSafeError(error.message, "Could not load sample dataset.");
        status.textContent = message;
        status.classList.remove("hidden");
        setStatus(message, error.name === "AbortError" ? "warn" : "error");
      } finally {
        window.clearInterval(progressTimer);
        hideLoadingOverlay();
        if (button && button.dataset.sampleLoaded !== "true") button.disabled = false;
        if (reloadLink) reloadLink.disabled = false;
      }
    }
function updateSampleDatasetControls(result = {}) {
      const button = el("loadSampleDatasetBtn");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!button || !reloadLink) return;
      const loaded = Boolean(result.loaded || result.already_loaded || result.locations);
      button.dataset.sampleLoaded = loaded ? "true" : "false";
      button.disabled = loaded;
      button.classList.toggle("ready", loaded);
      button.title = loaded ? "Sample data already in place." : "";
      button.textContent = loaded ? "Sample Dataset Loaded" : "Load Sample Dataset";
      reloadLink.classList.toggle("hidden", !loaded);
    }
async function refreshSampleDatasetStatus() {
      try {
        const response = await fetch("/api/sample/status");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not check sample dataset.");
        updateSampleDatasetControls(result);
        return result;
      } catch (error) {
        updateSampleDatasetControls({ loaded: false });
        return null;
      }
    }
async function saveMapper() {
      if (activeTemplateId) return saveEditedTemplate();
      const mapper = getMapper();
      const coverage = sourceFields.length ? Math.round(new Set(Object.values(mapper.fields).filter(Boolean)).size / sourceFields.length * 100) : 0;
      if (coverage < 50) {
        setStatus("Mapping coverage must reach 50% before saving.", "warn");
        return;
      }
      setStatus("Preparing your records...", "");
      setProgress(10, "Preparing your records");
      try {
        const batches = buildSaveBatches(sourceRows, mapper, sourceFields);
        const batchEventId = newSessionId();
        let mappedRows = 0;
        let errorListings = 0;
        let processedRows = 0;
        let eventId = "";
        for (let index = 0; index < batches.length; index += 1) {
          const batch = batches[index];
          const batchNumber = index + 1;
          const progress = Math.min(90, 20 + Math.round(processedRows / Math.max(sourceRows.length, 1) * 65));
          setProgress(progress, batches.length > 1 ? `Processing batch ${batchNumber} of ${batches.length}` : `Processing ${sourceRows.length} records`);
          const response = await fetch("/api/save", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              mapper,
              rows: batch.rows,
              source_fields: sourceFields,
              batch_event_id: batchEventId,
              row_offset: batch.rowOffset,
              save_template: index === 0
            })
          });
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "Could not save template.");
          eventId = result.event_id || batchEventId;
          mappedRows += result.mapped_rows || 0;
          errorListings += result.error_listings || 0;
          processedRows += batch.rows.length;
        }
        lastSaveEventId = eventId || batchEventId;
        el("reviewEventId").value = lastSaveEventId;
        await refreshReviewCount();
        hideProgress();
        setStatus(`Saved ${mappedRows} of ${sourceRows.length} records. ${errorListings} need review.`, "ok");
      } catch (error) {
        hideProgress();
        setStatus(productSafeError(error.message, "Could not save template."), "error");
      }
    }
async function clearSavedData() {
      const dialog = el("dangerDialog");
      if (typeof dialog.showModal === "function") {
        dialog.showModal();
        return;
      }
      if (window.confirm("DANGER: delete user-entered saved data?")) await performClearSavedData();
    }
async function performClearSavedData() {
      setStatus("Clearing saved data...", "warn");
      try {
        const response = await fetch("/api/clear", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{}"
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not clear saved data.");
        setStatus("Saved data cleared.", "ok");
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not clear saved data."), "error");
      }
    }

function resetMapping() {
      activeTemplateId = "";
      mappingSelections = {};
      autoMappedKeys = new Set();
      optionalMappingKeys = new Set();
      hiddenMappingKeys = new Set();
      customAliases = {};
      saveDraft();
      renderMappings();
      setStatus("Fields restored to the default suggestions.", "ok");
    }

function restartMapping() {
      sessionStorage.removeItem(draftStorageKey);
      location.reload();
    }
async function addCustomField() {
      const label = el("customFieldLabel").value.trim();
      if (!label) {
        setCustomFieldFeedback("Enter a label before adding a custom field.", "warn");
        return;
      }
      try {
        const response = await fetch("/api/custom-field", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
          label, slug: el("customFieldSlug").value.trim(), type: el("customFieldType").value, password: el("aliasPassword").value, business_id: selectedBrand?.business_id || ""
        }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not save custom field.");
        await loadFieldRegistry();
        el("customFieldLabel").value = "";
        el("customFieldSlug").value = "";
        el("aliasPassword").value = "";
        updateOptionalFieldPicker();
        updateDropCustomFieldPicker();
        setCustomFieldFeedback(`Custom field ${result.field.label} saved.`, "ok");
      } catch (error) { setCustomFieldFeedback(productSafeError(error.message, "Could not save custom field."), "error"); }
    }
async function toggleShowExistingBrands() {
      const box = el("existingBrandsDialog");
      if (box.style.display === "block") {
        box.style.display = "none";
        return;
      }
      box.style.display = "block";
      box.innerHTML = `<em>Fetching active businesses...</em>`;
      try {
        const response = await fetch("/api/brands?search=");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not fetch active businesses.");
        const brands = result.brands || [];
        if (!brands.length) {
          box.innerHTML = `<div style="color: var(--muted);">No existing businesses found.</div>`;
          return;
        }
        const optionsHtml = '<option class="create-new-option" value="__create_new__">+ Create New Business</option>' + brands.map(b => `<option value="${escapeHtml(b.business_id)}">${escapeHtml(b.name)} (ID: ${escapeHtml(b.business_id)})</option>`).join('');
        box.innerHTML = `
          <label style="display: block; font-weight: 700; margin-bottom: 4px; color: var(--navy);" for="activeBusinessesDropdown">
            Active Businesses (${brands.length})
          </label>
          <select id="activeBusinessesDropdown" style="width: 100%; padding: 6px 8px; border-radius: 4px; border: 1px solid var(--line); background: #ffffff;">
            ${optionsHtml}
          </select>
        `;
        el("activeBusinessesDropdown").addEventListener("change", (event) => {
          if (event.target.value === "__create_new__") {
            el("brandSelect").value = "__create_new__";
            el("brandSelect").dispatchEvent(new Event("change"));
          }
        });
      } catch (err) {
        box.innerHTML = `<div style="color: var(--error);">${escapeHtml(err.message)}</div>`;
      }
    }
