/**
 * Source Mapping UI Subpackage Module.
 * 
 * Manages source onboarding, brand & connector configuration, target schema field mapping,
 * draft save/restore, and save-to-warehouse pipeline logic.
 * Communicates with backend endpoints (`/api/schema`, `/api/preview`, `/api/save`, `/api/brands`, `/api/learning`)
 * routed to `whitespace_tool.mapping`.
 */

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
  const target = el("newBrandSourceType");
  if (target) target.innerHTML = `<option value="">Select source format</option>${options}`;
}

function resetTemplateSelection() {
  activeTemplateId = "";
  if (el("templateSearch")) el("templateSearch").value = "";
  if (el("templateResults")) {
    el("templateResults").className = "status";
    el("templateResults").textContent = "Search saved templates to edit an existing mapping.";
  }
}

function applyBusinessSourceType(business) {
  const sourceTypeId = business?.source_type_id || "";
  const format = sourceTypeIdToFormat(sourceTypeId) || sourceTypeNameToFormat(business?.source_type_name || "");
  if (el("sourceType")) el("sourceType").disabled = Boolean(format);
  if (format && el("sourceType")) {
    el("sourceType").value = format;
    resetSourceInputsForNewMode(format);
    updateSourceVisibility();
  }
  if (el("templateBusinessFilter")) el("templateBusinessFilter").value = business?.business_id || "";
  if (el("templateSourceFilter")) el("templateSourceFilter").value = sourceTypeId;
}

async function refreshTemplatesForBusiness() {
  resetTemplateSelection();
  if (typeof loadTemplateLibrary === "function") await loadTemplateLibrary();
}

function setCustomFieldFeedback(message, type = "") {
  const target = el("customFieldFeedback");
  if (!target) return;
  target.className = `action-feedback ${type}`;
  target.textContent = message;
}

function setConnectorFeedback(message, type = "") {
  const target = el("pythonConnectorFeedback");
  if (!target) return;
  target.className = `action-feedback ${type}`;
  target.textContent = message;
}

function getConnectorCode() {
  return connectorEditor ? connectorEditor.getValue() : (el("pythonConnectorCode")?.value || "");
}

function setConnectorCode(code) {
  if (connectorEditor) connectorEditor.setValue(code);
  else if (el("pythonConnectorCode")) el("pythonConnectorCode").value = code;
}

function dominosPythonCode() {
  const limit = window.APP_CONSTANTS?.dominosZipFetchLimit || 1;
  const storesPerZip = window.APP_CONSTANTS?.dominosStoresPerZipLimit || 1;
  const maxWorkers = window.APP_CONSTANTS?.dominosMaxWorkers || 8;
  const provider = encodeURIComponent(window.APP_CONSTANTS?.dominosProvider || "auto");
  const orderType = encodeURIComponent(window.APP_CONSTANTS?.dominosOrderType || "Delivery");
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
    brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
  } catch (e) {}

  const existing = brands.find((b) => b.name && b.name.toLowerCase() === brandName.toLowerCase());

  if (existing) {
    selectedBrand = existing;
    if (el("brandSelect")) el("brandSelect").value = existing.business_id;
    el("newBrandFields")?.classList.add("hidden");
    applyBusinessSourceType(existing);
  } else {
    selectedBrand = null;
    if (el("brandSelect")) el("brandSelect").value = "__create_new__";
    el("newBrandFields")?.classList.remove("hidden");
    setNewBusinessSourceType(el("sourceType")?.value || "csv");
    if (el("newBrandName")) el("newBrandName").value = brandConfig.name || "";
    if (el("newBrandSlug")) el("newBrandSlug").value = brandConfig.slug || "";
    if (el("newBrandDescription")) el("newBrandDescription").value = brandConfig.description || "";
    if (el("newBrandLogo")) el("newBrandLogo").value = "";
    if (el("newBrandWebsite")) el("newBrandWebsite").value = brandConfig.websiteUrl || "";
    if (el("newBrandStatus")) el("newBrandStatus").value = brandConfig.status || "active";
    if (el("newBrandMetaTitle")) el("newBrandMetaTitle").value = brandConfig.metaTitle || "";
    if (el("newBrandMetaDescription")) el("newBrandMetaDescription").value = brandConfig.metaDescription || "";
    if (el("newBrandOrigin")) el("newBrandOrigin").value = brandConfig.countryOfOrigin || "";
  }
}

function fillDominosBrand() {
  syncBrandSelection(window.APP_CONSTANTS?.dominosBrand || {});
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
  if (el("sourceType")) el("sourceType").value = "python_editor";
  if (el("sourceName")) el("sourceName").value = "dominos_store_locator";
  if (el("recordPath")) el("recordPath").value = "Stores";
  if (el("pythonPackages")) el("pythonPackages").value = "";
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

function setPresetLocked(locked, controlIds) {
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
  if (el("sourceUrl")) {
    el("sourceUrl").toggleAttribute("readonly", Boolean(locked));
    el("sourceUrl").classList.toggle("demo-url", Boolean(locked));
  }
}

function resetSourceInputsForNewMode(sourceType = el("sourceType")?.value || "csv") {
  setPresetLocked(false, []);
  setSourceUrlLocked(false);
  if (el("sourceUrl")) {
    el("sourceUrl").value = "";
    el("sourceUrl").placeholder = sourceUrlPlaceholders[sourceType] || "https://example.com/locations.json";
  }
  if (el("apiUrl")) {
    el("apiUrl").value = "";
    el("apiUrl").placeholder = sourceType === "api_get_json" ? "https://example.com/stores.json" : "https://example.com/locations.json";
  }
  if (el("sourceName")) el("sourceName").value = "";
  if (el("recordPath")) el("recordPath").value = "";
  if (el("jsonRecordPath")) el("jsonRecordPath").innerHTML = '<option value="">Automatically select the best record layer</option>';
  if (el("sheetName")) {
    el("sheetName").innerHTML = '<option value="">Upload Excel to load sheets</option>';
    el("sheetName").disabled = true;
  }
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
  if (el("sourceType")) el("sourceType").value = "csv";
  if (el("sourceInputMode")) el("sourceInputMode").value = "url";
  if (el("sourceUrl")) el("sourceUrl").value = window.APP_CONSTANTS?.pizzaHutCsvDemoUrl || "";
  setSourceUrlLocked(true);
  if (el("sourceName")) el("sourceName").value = "pizza_hut_locations_csv";
  if (el("recordPath")) el("recordPath").value = "";
  fillBrandFromConfig(window.APP_CONSTANTS?.pizzaHutBrand || {});
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
  if (el("sourceType")) el("sourceType").value = "csv";
  if (el("sourceInputMode")) el("sourceInputMode").value = "url";
  if (el("sourceUrl")) el("sourceUrl").value = window.APP_CONSTANTS?.globalHotelsCorruptDemoUrl || "";
  setSourceUrlLocked(true);
  if (el("sourceName")) el("sourceName").value = "global_hotels_mixed_csv";
  if (el("recordPath")) el("recordPath").value = "";
  fillBrandFromConfig(window.APP_CONSTANTS?.globalHotelsBrand || {});
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
  fillBrandFromConfig(window.APP_CONSTANTS?.laCityJsonDemoBrand || {});
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
  if (el("sourceType")) el("sourceType").value = "json";
  if (el("sourceInputMode")) el("sourceInputMode").value = "url";
  if (el("sourceUrl")) el("sourceUrl").value = window.APP_CONSTANTS?.laCityJsonDemoUrl || "";
  setSourceUrlLocked(true);
  if (el("sourceName")) el("sourceName").value = "la_city_restaurant_inspections_json";
  if (el("recordPath")) el("recordPath").value = "";
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
  if (el("sourceType")) el("sourceType").value = "api_get_json";
  if (el("apiUrl")) el("apiUrl").value = window.APP_CONSTANTS?.littleCaesarsApiDemoUrl || "";
  if (el("sourceName")) el("sourceName").value = "little_caesars_locations_api";
  if (el("recordPath")) el("recordPath").value = "locations";
  fillBrandFromConfig(window.APP_CONSTANTS?.littleCaesarsBrand || {});
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

function updateFileAccept() {
  const fileInput = el("fileInput");
  const sourceType = el("sourceType")?.value || "csv";
  const sourceFileAccept = {
    csv: ".csv,text/csv",
    excel: ".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel",
    json: ".json,.geojson,application/json,application/geo+json",
    xml: ".xml,application/xml,text/xml"
  };
  if (fileInput) fileInput.accept = sourceFileAccept[sourceType] || "";
}

function updateSourceVisibility() {
  const sourceType = el("sourceType")?.value || "csv";
  const isApi = sourceType === "api_get_json";
  const isPythonConnector = sourceType === "python_editor";
  const isExcel = sourceType === "excel";
  const isJson = sourceType === "json";
  const isCsv = sourceType === "csv";
  const hasRecordPath = ["json", "xml", "api_get_json", "python_editor"].includes(sourceType);
  const isFileSource = !isApi && !isPythonConnector;
  const inputMode = el("sourceInputMode")?.value || "file";

  document.querySelectorAll(".api-field").forEach((field) => field.classList.toggle("hidden", !isApi));
  document.querySelectorAll(".api-function-field").forEach((field) => field.classList.toggle("hidden", !isApi));
  document.querySelectorAll(".csv-function-field").forEach((field) => field.classList.toggle("hidden", !isCsv));
  document.querySelectorAll(".json-function-field").forEach((field) => field.classList.toggle("hidden", !isJson));
  document.querySelectorAll(".python-connector-field").forEach((field) => field.classList.toggle("hidden", !isPythonConnector));
  document.querySelectorAll(".excel-field").forEach((field) => field.classList.toggle("hidden", !isExcel));
  document.querySelectorAll(".file-field").forEach((field) => field.classList.toggle("hidden", isApi || isPythonConnector));
  document.querySelectorAll(".file-upload-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || inputMode !== "file"));
  document.querySelectorAll(".source-url-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || inputMode !== "url"));
  document.querySelectorAll(".record-field").forEach((field) => field.classList.toggle("hidden", !hasRecordPath));
  document.querySelectorAll(".json-record-path-field").forEach((field) => field.classList.toggle("hidden", sourceType !== "json"));

  document.querySelector("main")?.classList.toggle("connector-active", isPythonConnector);
  updateFileAccept();
  if (el("fileInput")) el("fileInput").disabled = isApi || isPythonConnector;
  if (el("apiUrl")) el("apiUrl").disabled = !isApi;
  if (el("sheetName")) el("sheetName").disabled = !isExcel || !el("sheetName").options.length;
}

async function loadFieldRegistry() {
  try {
    const response = await fetch("/api/field-registry");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load field definitions.");
    if (Array.isArray(result.fields) && result.fields.length) mappingTargets = result.fields;
    if (sourceParsed) {
      renderMappings();
    } else {
      updateOptionalFieldPicker();
      updateDropCustomFieldPicker();
    }
    if (result.warning) setStatus(result.warning, "warn");
  } catch (error) {
    setStatus(productSafeError(error.message, "Could not load field definitions."), "error");
  }
}

async function loadBrands(search = "") {
  try {
    const response = await fetch(`/api/brands?search=${encodeURIComponent(search)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load brands.");
    const brands = result.brands || [];
    const brandSelect = el("brandSelect");
    if (brandSelect) {
      brandSelect.innerHTML = '<option value="">Select an existing business</option><option class="create-new-option" value="__create_new__">+ Create New Business</option>' + brands.map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(brand.name)}</option>`).join("");
      brandSelect.dataset.brands = JSON.stringify(brands);
      if (selectedBrand) brandSelect.value = selectedBrand.business_id;
    }
  } catch (error) {
    setStatus(productSafeError(error.message, "Could not load businesses."), "error");
  }
}

async function createNewBrand(brandNameOverride = "") {
  const name = (brandNameOverride || el("newBrandName")?.value || "").trim();
  if (!name) { setStatus("Brand name is required.", "warn"); return null; }
  const sourceTypeId = el("newBrandSourceType")?.value || currentSourceTypeId();
  const selectedSourceOption = el("newBrandSourceType")?.selectedOptions?.[0];
  const sourceType = selectedSourceOption?.dataset.format || sourceTypeNameToFormat(selectedSourceOption?.textContent || "") || el("sourceType")?.value || "csv";
  if (!sourceTypeId) { setStatus("Source format is required.", "warn"); return null; }
  try {
    const response = await fetch("/api/brands", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name, source_type_id: sourceTypeId, source_type: sourceType,
        slug: el("newBrandSlug")?.value.trim() || "",
        description: el("newBrandDescription")?.value.trim() || "",
        logo_url: el("newBrandLogo")?.value.trim() || "",
        website_url: el("newBrandWebsite")?.value.trim() || "",
        status: el("newBrandStatus")?.value || "active",
        meta_title: el("newBrandMetaTitle")?.value.trim() || "",
        meta_description: el("newBrandMetaDescription")?.value.trim() || "",
        country_of_origin: el("newBrandOrigin")?.value.trim() || ""
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not create brand.");
    selectedBrand = result.brand;
    if (el("brandSelect")) el("brandSelect").value = selectedBrand.business_id;
    await loadBrands(selectedBrand.name);
    if (el("brandSelect")) el("brandSelect").value = selectedBrand.business_id;
    el("newBrandFields")?.classList.add("hidden");
    applyBusinessSourceType(selectedBrand);
    await refreshTemplatesForBusiness();
    setStatus(`Brand ${selectedBrand.name} is ready for mapping.`, "ok");
    updateOutput();
    return selectedBrand;
  } catch (error) {
    setStatus(productSafeError(error.message, "Could not create business."), "error");
    return null;
  }
}

async function saveMapper() {
  let mapper = getMapper();
  if (!mapper.brand) {
    setStatus("Please select or enter a Business/Brand name before saving.", "warn");
    return;
  }
  if (!mapper.business_id) {
    setStatus("Creating business for mapping...", "");
    const created = await createNewBrand(mapper.brand);
    if (!created || !created.business_id) {
      setStatus("Could not resolve business ID. Please save the business first.", "warn");
      return;
    }
    mapper = getMapper();
  }

  if (activeTemplateId && typeof saveEditedTemplate === "function") {
    try {
      await saveEditedTemplate();
    } catch (error) {
      setStatus(productSafeError(error.message, "Could not update template."), "error");
      return;
    }
  }

  if (!sourceRows.length) {
    if (!activeTemplateId) setStatus("Parse a source file before saving.", "warn");
    return;
  }

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
          save_template: !activeTemplateId && index === 0
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
    if (el("reviewEventId")) el("reviewEventId").value = lastSaveEventId;
    if (typeof refreshReviewCount === "function") await refreshReviewCount();
    hideProgress();
    const prefix = activeTemplateId ? "Template updated. " : "";
    setStatus(`${prefix}Saved ${mappedRows} of ${sourceRows.length} records. ${errorListings} need review.`, "ok");
  } catch (error) {
    hideProgress();
    setStatus(productSafeError(error.message, "Could not save template."), "error");
  }
}

/* ============================================================================
 * Missing Helper & Interactive Mapping Functions
 * ============================================================================ */

function addPairRow(containerId, defaultKey = "", defaultValue = "") {
  const container = el(containerId);
  if (!container) return;
  const row = document.createElement("div");
  row.className = "pair-row";
  row.style.cssText = "display: flex; gap: 6px; margin-top: 6px;";
  row.innerHTML = `
    <input type="text" class="pair-key" placeholder="Key" value="${escapeHtml(defaultKey)}" style="flex: 1;">
    <input type="text" class="pair-value" placeholder="Value" value="${escapeHtml(defaultValue)}" style="flex: 1;">
    <button type="button" class="secondary remove-pair-btn" title="Remove" style="padding: 4px 8px;">&times;</button>
  `;
  row.querySelector(".remove-pair-btn").addEventListener("click", () => {
    row.remove();
    updateOutput();
  });
  row.querySelectorAll("input").forEach((input) => input.addEventListener("input", updateOutput));
  container.appendChild(row);
  updateOutput();
}

function isNewSourceMode() {
  const sourceType = el("sourceType")?.value;
  if (sourceType === "csv") return csvFunctionMode === "new";
  if (sourceType === "json") return jsonFunctionMode === "new";
  if (sourceType === "api_get_json") return apiFunctionMode === "new";
  return true;
}

function updateAuthVisibility() {
  const authType = el("authType")?.value || "none";
  document.querySelectorAll(".auth-field").forEach((field) => field.classList.add("hidden"));
  if (authType === "bearer") document.querySelector(".auth-bearer")?.classList.remove("hidden");
  if (authType === "basic") document.querySelector(".auth-basic")?.classList.remove("hidden");
  if (authType === "api_key_header") document.querySelector(".auth-api-key")?.classList.remove("hidden");
  updateOutput();
}

function initializeConnectorEditor() {
  const container = el("pythonConnectorEditor");
  if (!container || connectorEditor) return;
  if (window.monaco) {
    try {
      connectorEditor = window.monaco.editor.create(container, {
        value: el("pythonConnectorCode")?.value || "",
        language: "python",
        theme: "vs-dark",
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 13
      });
      connectorEditor.onDidChangeModelContent(() => {
        if (el("pythonConnectorCode")) el("pythonConnectorCode").value = connectorEditor.getValue();
        updateOutput();
      });
    } catch (err) {
      console.warn("Monaco editor initialization fallback:", err);
    }
  }
}

function openConnectorEditor() {
  const editorField = el("pythonConnectorField");
  if (editorField) editorField.classList.remove("hidden");
  initializeConnectorEditor();
}

function minimizeConnectorEditor() {
  const editorField = el("pythonConnectorField");
  if (editorField) editorField.classList.add("hidden");
}

function addCustomField() {
  const input = el("customFieldName");
  const name = input?.value.trim();
  if (!name) return;
  const key = normalizeName(name);
  if (!mappingTargets.some((target) => target.key === key)) {
    mappingTargets.push({
      key: key,
      table: "listings",
      field: key,
      label: name,
      required: false,
      hints: [key, normalizeName(name)]
    });
    optionalMappingKeys.add(key);
  }
  if (input) input.value = "";
  renderMappings();
  updateDropCustomFieldPicker();
  updateOutput();
}

function dropCustomField() {
  const picker = el("dropCustomFieldSelect");
  const key = picker?.value;
  if (!key) return;
  mappingTargets = mappingTargets.filter((target) => target.key !== key);
  optionalMappingKeys.delete(key);
  hiddenMappingKeys.delete(key);
  delete mappingSelections[key];
  renderMappings();
  updateDropCustomFieldPicker();
  updateOutput();
}

function updateDropCustomFieldPicker() {
  const picker = el("dropCustomFieldSelect");
  if (!picker) return;
  const customTargets = mappingTargets.filter((target) => !primaryMappingKeys.has(target.key));
  picker.innerHTML = '<option value="">Select custom field to remove</option>' +
    customTargets.map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)}</option>`).join("");
}

function updateOptionalFieldPicker() {
  const picker = el("optionalFieldSelect");
  if (!picker) return;
  const availableOptional = mappingTargets.filter((target) => {
    if (primaryMappingKeys.has(target.key)) return false;
    return !optionalMappingKeys.has(target.key);
  });
  picker.innerHTML = '<option value="">Choose a field</option>' +
    availableOptional.map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)} (${escapeHtml(target.key)})</option>`).join("");
}

function toggleShowExistingBrands() {
  const dialog = el("existingBrandsDialog");
  if (!dialog) return;
  if (dialog.style.display === "none" || !dialog.style.display) {
    dialog.style.display = "block";
    loadBrands().then(() => {
      const picker = el("brandSelect");
      const brands = JSON.parse(picker?.dataset?.brands || "[]");
      if (!brands.length) {
        dialog.innerHTML = "<em>No saved business entities found.</em>";
      } else {
        dialog.innerHTML = "<strong>Existing Business Entities:</strong><ul style='margin: 4px 0 0 16px; padding: 0;'>" +
          brands.map((b) => `<li><strong>${escapeHtml(b.name)}</strong> (${escapeHtml(b.business_id)}) - ${escapeHtml(b.source_type)}</li>`).join("") +
          "</ul>";
      }
    });
  } else {
    dialog.style.display = "none";
  }
}

function clearSavedData() {
  const dialog = el("dangerDialog");
  if (dialog && typeof dialog.showModal === "function") {
    dialog.showModal();
  } else if (confirm("Are you sure you want to clear all local draft mappings and stored session state?")) {
    performClearSavedData();
  }
}

async function performClearSavedData() {
  localStorage.removeItem("mapper_login_remembered");
  sessionStorage.removeItem("competitive_whitespace_mapping_draft");
  sessionStorage.removeItem("competitive_whitespace_mapping_session");
  sourceRows = [];
  sourceFields = [];
  mappingSelections = {};
  resetMapping();
  if (typeof setStatus === "function") setStatus("Cleared local draft mappings and cached session state.", "ok");
}

function resetMapping() {
  mappingSelections = {};
  renderMappings();
  updateOutput();
  if (typeof setStatus === "function") setStatus("Field mappings reset.", "info");
}

function restartMapping() {
  sourceRows = [];
  sourceFields = [];
  mappingSelections = {};
  sourceParsed = false;
  const fileInput = el("fileInput");
  if (fileInput) fileInput.value = "";
  const sourceUrl = el("sourceUrl");
  if (sourceUrl) sourceUrl.value = "";
  renderMappings();
  updateOutput();
  if (typeof setStatus === "function") setStatus("Mapping process restarted.", "info");
}

function renderMappings() {
  const container = el("mappingContainer") || el("fieldsMappingGrid");
  if (!container) return;

  const visibleTargets = mappingTargets.filter((target) => {
    if (hiddenMappingKeys.has(target.key)) return false;
    if (primaryMappingKeys.has(target.key)) return true;
    return optionalMappingKeys.has(target.key);
  });

  visibleTargets.sort((a, b) => {
    const idxA = fieldOrderIndex.has(a.key) ? fieldOrderIndex.get(a.key) : 999;
    const idxB = fieldOrderIndex.has(b.key) ? fieldOrderIndex.get(b.key) : 999;
    return idxA - idxB;
  });

  let html = `<table class="mapping-table" style="width: 100%; border-collapse: collapse;">
    <thead>
      <tr>
        <th style="text-align: left; padding: 8px;">Target Field</th>
        <th style="text-align: left; padding: 8px;">Source Field</th>
        <th style="text-align: left; padding: 8px;">Sample Value</th>
        <th style="text-align: center; padding: 8px;">Actions</th>
      </tr>
    </thead>
    <tbody>`;

  visibleTargets.forEach((target) => {
    const selectedField = mappingSelections[target.key] || "";
    const sampleVal = sourceRows.length > 0 && selectedField ? sourceRows[0][selectedField] : "";
    const isRequired = target.required;
    const badgeHtml = isRequired ? '<span class="required-badge" style="color: var(--error); font-size: 11px;">*Required</span>' : '<span class="optional-badge" style="color: var(--muted); font-size: 11px;">Optional</span>';

    const fieldOptionsHtml = '<option value="">-- Unmapped --</option>' +
      sourceFields.map((f) => `<option value="${escapeHtml(f)}" ${f === selectedField ? 'selected' : ''}>${escapeHtml(f)}</option>`).join("");

    html += `<tr style="border-bottom: 1px solid var(--line);">
      <td style="padding: 8px;"><strong>${escapeHtml(target.label)}</strong> ${badgeHtml}<br><code style="font-size: 11px; color: var(--muted);">${escapeHtml(target.key)}</code></td>
      <td style="padding: 8px;">
        <select class="field-mapping-select" data-target-key="${escapeHtml(target.key)}" style="width: 100%;">
          ${fieldOptionsHtml}
        </select>
      </td>
      <td class="sample-value-cell" style="padding: 8px; font-family: monospace; font-size: 12px; color: var(--muted);">${escapeHtml(sampleVal ?? "")}</td>
      <td style="padding: 8px; text-align: center;">
        ${!isRequired ? `<button type="button" class="secondary hide-field-btn" data-target-key="${escapeHtml(target.key)}" title="Hide Field" style="padding: 2px 6px;">&times;</button>` : ''}
      </td>
    </tr>`;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;

  container.querySelectorAll(".field-mapping-select").forEach((select) => {
    select.addEventListener("change", (e) => {
      const key = e.target.dataset.targetKey;
      const val = e.target.value;
      if (val) mappingSelections[key] = val;
      else delete mappingSelections[key];
      updateOutput();
    });
  });

  container.querySelectorAll(".hide-field-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const key = e.target.dataset.targetKey;
      hiddenMappingKeys.add(key);
      renderMappings();
      updateOutput();
    });
  });
}

function updateOutput() {
  const outputEl = el("mapperOutput");
  if (!outputEl) return;
  const config = {
    brand_id: el("brandSelect")?.value || "",
    source_name: el("sourceName")?.value || "",
    source_type: el("sourceType")?.value || "csv",
    record_path: el("recordPath")?.value || "",
    mappings: mappingSelections
  };
  outputEl.value = JSON.stringify(config, null, 2);
}

function autoMapFields() {
  mappingTargets.forEach((target) => {
    if (mappingSelections[target.key]) return;
    const match = sourceFields.find((sf) => {
      const norm = normalizeName(sf);
      return target.hints.some((hint) => norm.includes(normalizeName(hint)));
    });
    if (match) mappingSelections[target.key] = match;
  });
}

async function parseSource() {
  const sourceType = el("sourceType")?.value || "csv";
  const inputMode = el("sourceInputMode")?.value || "file";
  const fileInput = el("fileInput");
  const sourceUrl = el("sourceUrl");
  if (typeof setStatus === "function") setStatus("Parsing source data...", "info");

  try {
    if (sourceType === "python_editor") {
      await runPythonConnector();
      return;
    }

    let rawData = "";
    if (inputMode === "file" && fileInput?.files?.length > 0) {
      const file = fileInput.files[0];
      rawData = await file.text();
    } else if (inputMode === "url" && sourceUrl?.value) {
      const resp = await fetch("/api/preview", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: sourceUrl.value, source_type: sourceType })
      });
      const data = await resp.json();
      if (data.records) {
        sourceRows = data.records;
        sourceFields = data.fields || (sourceRows.length ? Object.keys(sourceRows[0]) : []);
        autoMapFields();
        renderMappings();
        updateOutput();
        if (typeof setStatus === "function") setStatus(`Successfully parsed ${sourceRows.length} records.`, "ok");
        return;
      }
    }

    if (rawData) {
      if (sourceType === "csv") {
        const lines = rawData.split(/\r?\n/).filter((l) => l.trim());
        if (lines.length > 0) {
          const headers = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
          sourceFields = headers;
          sourceRows = lines.slice(1, 50).map((line) => {
            const vals = line.split(",").map((v) => v.trim().replace(/^"|"$/g, ""));
            const obj = {};
            headers.forEach((h, i) => { obj[h] = vals[i] || ""; });
            return obj;
          });
        }
      } else if (sourceType === "json" || sourceType === "api_get_json") {
        const parsed = JSON.parse(rawData);
        const records = Array.isArray(parsed) ? parsed : (parsed.locations || parsed.stores || parsed.data || [parsed]);
        sourceRows = records.slice(0, 50);
        sourceFields = sourceRows.length ? Object.keys(sourceRows[0]) : [];
      }
      autoMapFields();
      renderMappings();
      updateOutput();
      if (typeof setStatus === "function") setStatus(`Parsed source data with ${sourceFields.length} fields.`, "ok");
    } else {
      if (typeof setStatus === "function") setStatus("Please select a file or provide a valid source URL.", "warn");
    }
  } catch (err) {
    if (typeof setStatus === "function") setStatus(`Failed to parse source: ${err.message}`, "error");
  }
}

async function runPythonConnector() {
  const code = getConnectorCode();
  const feedback = el("pythonConnectorFeedback");
  const output = el("pythonConnectorOutput");
  if (feedback) { feedback.className = "action-feedback info"; feedback.textContent = "Running Python script..."; }

  try {
    if (!window.pyodide) {
      if (typeof loadPyodide === "function") {
        window.pyodide = await loadPyodide();
      } else {
        throw new Error("Pyodide library is loading or missing.");
      }
    }
    await window.pyodide.runPythonAsync(code);
    const pyResult = window.pyodide.globals.get("result");
    const records = pyResult ? pyResult.toJs({ dict_converter: Object.fromEntries }) : [];
    sourceRows = Array.isArray(records) ? records.slice(0, 50) : [];
    sourceFields = sourceRows.length ? Object.keys(sourceRows[0]) : [];
    autoMapFields();
    renderMappings();
    updateOutput();
    if (output) output.value = JSON.stringify(sourceRows.slice(0, 3), null, 2);
    if (feedback) { feedback.className = "action-feedback ok"; feedback.textContent = `Executed successfully. Extracted ${sourceRows.length} records.`; }
  } catch (err) {
    if (output) output.value = err.message;
    if (feedback) { feedback.className = "action-feedback error"; feedback.textContent = `Execution failed: ${err.message}`; }
  }
}

async function loadExcelSheets() {
  const fileInput = el("fileInput");
  const sheetSelect = el("sheetName");
  if (!fileInput?.files?.length || !sheetSelect) return;
  sheetSelect.disabled = false;
  sheetSelect.innerHTML = '<option value="Sheet1">Sheet1</option>';
}

// Global Window Exports for loader.js
window.addPairRow = addPairRow;
window.isNewSourceMode = isNewSourceMode;
window.updateAuthVisibility = updateAuthVisibility;
window.initializeConnectorEditor = initializeConnectorEditor;
window.openConnectorEditor = openConnectorEditor;
window.minimizeConnectorEditor = minimizeConnectorEditor;
window.addCustomField = addCustomField;
window.dropCustomField = dropCustomField;
window.updateDropCustomFieldPicker = updateDropCustomFieldPicker;
window.updateOptionalFieldPicker = updateOptionalFieldPicker;
window.toggleShowExistingBrands = toggleShowExistingBrands;
window.clearSavedData = clearSavedData;
window.performClearSavedData = performClearSavedData;
window.resetMapping = resetMapping;
window.restartMapping = restartMapping;
window.renderMappings = renderMappings;
window.updateOutput = updateOutput;
window.parseSource = parseSource;
window.runPythonConnector = runPythonConnector;
window.loadExcelSheets = loadExcelSheets;

// === fallbackDisplayBusinessId ===
async function fallbackDisplayBusinessId(brand = {}) {
      const payload = JSON.stringify({
        name: brand.name || "",
        slug: brand.slug || "",
        description: brand.description || "",
        logo_url: brand.logo_url || "",
        website_url: brand.website_url || "",
        status: brand.status || "",
        meta_title: brand.meta_title || "",
        meta_description: brand.meta_description || "",
        country_of_origin: brand.country_of_origin || "",
        is_reference_data: Boolean(brand.is_reference_data),
        reference_key: brand.reference_key || "",
        default_source_url: brand.default_source_url || "",
        default_source_name: brand.default_source_name || "",
        source_type_id: brand.source_type_id || ""
      });
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(payload));
      const hex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
      return `BID ${hex.slice(0, 8).toUpperCase()}`;
    }

// === similarBusinessKey ===
function similarBusinessKey(name = "") {
      return normalizeName(name).replace(/\b(inc|llc|ltd|usa|us|global|stores|locations)\b/g, "");
    }

// === duplicateBusinessGroups ===
function duplicateBusinessGroups(brands = []) {
      const groups = new Map();
      brands.forEach((brand) => {
        const key = similarBusinessKey(brand.name || "");
        if (!key) return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(brand);
      });
      return [...groups.values()].filter((group) => group.length > 1);
    }

// === businessCreatedTime ===
function businessCreatedTime(brand = {}) {
      const value = Date.parse(brand.created_at || "");
      return Number.isFinite(value) ? value : 0;
    }

// === businessOptionLabel ===
function businessOptionLabel(brand = {}, newestCreatedAt = 0) {
      const newest = newestCreatedAt && businessCreatedTime(brand) === newestCreatedAt ? "Newest, " : "";
      return `${brand.name || "Unnamed"} (${brand.display_business_id || "BID --------"}, ${formatNumber(brand.listing_count || 0)} listings, ${newest}created ${brand.created_at ? new Date(brand.created_at).toLocaleDateString() : "unknown"})`;
    }

// === businessOptionLabelShort ===
function businessOptionLabelShort(brand = {}) {
      return `${brand.name || "Unnamed"} (${brand.display_business_id || "BID --------"})`;
    }

// === mergeDuplicateBusinesses ===
async function mergeDuplicateBusinesses(targetId, sourceIds) {
      const response = await fetch("/api/brands/merge", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_business_id: targetId, source_business_ids: sourceIds })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not merge brands.");
      return result;
    }

// === presetMetadata ===
function presetMetadata(config = activeCsvPresetConfig || {}) {
      return {
        is_reference_data: true,
        reference_key: config.mode || "",
        default_source_url: el("sourceUrl")?.value.trim() || config.url || "",
        default_source_name: el("sourceName")?.value.trim() || config.sourceName || ""
      };
    }

// === fillBrandFields ===
function fillBrandFields(brand = {}, fallback = {}) {
      setNewBusinessSourceType(el("sourceType").value);
      el("newBrandName").value = brand.name || fallback.name || "";
      el("newBrandSlug").value = brand.slug || fallback.slug || "";
      el("newBrandDescription").value = brand.description || fallback.description || "";
      el("newBrandLogo").value = brand.logo_url || fallback.logoUrl || "";
      el("newBrandWebsite").value = brand.website_url || fallback.websiteUrl || "";
      el("newBrandStatus").value = brand.status || fallback.status || "active";
      el("newBrandMetaTitle").value = brand.meta_title || fallback.metaTitle || "";
      el("newBrandMetaDescription").value = brand.meta_description || fallback.metaDescription || "";
      el("newBrandOrigin").value = brand.country_of_origin || fallback.countryOfOrigin || "";
    }

// === lockBrandFields ===
function lockBrandFields(locked) {
      ["newBrandName", "newBrandSourceType", "newBrandSlug", "newBrandDescription", "newBrandLogo", "newBrandWebsite", "newBrandStatus", "newBrandMetaTitle", "newBrandMetaDescription", "newBrandOrigin", "createBrandBtn"].forEach((id) => {
        if (el(id)) el(id).disabled = Boolean(locked);
      });
    }

// === setLockedValue ===
function setLockedValue(id, value) {
      if (el(id)) el(id).value = value || "";
    }

// === updatePresetBrandPanel ===
function updatePresetBrandPanel(brandConfig = activeCsvPresetConfig?.brand || null, exists = Boolean(selectedBrand)) {
      const panel = el("presetBrandPanel");
      if (!panel) return;
      const isPreset = Boolean(activeCsvPresetConfig && brandConfig?.name);
      panel.classList.toggle("hidden", !isPreset);
      if (!isPreset) return;
      el("presetBrandTitle").textContent = brandConfig.name;
      el("presetBrandCreateBtn").textContent = exists ? "Save Changes" : "Create Brand";
      el("presetBrandCreateBtn").classList.toggle("hidden", exists && !presetBrandEditMode);
      el("presetBrandEditBtn").classList.toggle("hidden", !exists && !presetBrandEditMode);
      el("presetBrandEditBtn").textContent = presetBrandEditMode ? "Cancel Edit" : "Edit Brand Details";
      el("createBrandBtn").classList.toggle("hidden", exists);
      el("brandSelect").disabled = Boolean(exists);
      el("brandSelect").classList.remove("hidden");
      el("brandSelectLabel")?.classList.remove("hidden");
      lockBrandFields(Boolean(exists && !presetBrandEditMode));
      el("presetBrandStatus").textContent = exists
        ? "Locked to the existing brand. Edit only if these details need to change."
        : "No existing brand found. Create it once, then parse as usual.";
    }

// === hidePresetBrandPanel ===
function hidePresetBrandPanel() {
      activeCsvPresetConfig = null;
      presetBrandEditMode = false;
      el("presetBrandPanel")?.classList.add("hidden");
      el("brandSelect").disabled = false;
      el("brandSelect")?.classList.remove("hidden");
      el("brandSelectLabel")?.classList.remove("hidden");
      lockBrandFields(false);
      el("createBrandBtn")?.classList.remove("hidden");
      el("newBrandFields")?.classList.toggle("hidden", el("brandSelect")?.value !== "__create_new__");
    }

// === resetPresetBrandEditState ===
function resetPresetBrandEditState() {
      presetBrandEditMode = false;
      el("newBrandFields")?.classList.add("hidden");
      lockBrandFields(false);
      el("presetBrandEditBtn")?.classList.remove("hidden");
      el("presetBrandCreateBtn")?.classList.remove("hidden");
      el("createBrandBtn")?.classList.remove("hidden");
    }

// === applyBrandToCurrentSelection ===
function applyBrandToCurrentSelection(brand) {
      selectedBrand = brand || null;
      if (!selectedBrand) {
        el("brandSelect").value = "__create_new__";
        el("newBrandFields").classList.remove("hidden");
        return;
      }
      el("brandSelect").value = selectedBrand.business_id;
      el("newBrandFields").classList.add("hidden");
      applyBusinessSourceType(selectedBrand);
    }

// === firstExistingBrand ===
function firstExistingBrand() {
      const brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      return brands.find((brand) => brand?.business_id && String(brand.status || "active").toLowerCase() === "active")
        || brands.find((brand) => brand?.business_id)
        || null;
    }

// === createOrUsePresetBrand ===
async function createOrUsePresetBrand() {
      if (!activeCsvPresetConfig?.brand?.name) return null;
      if (selectedBrand?.business_id && presetBrandEditMode) {
        return updateExistingBrand();
      }
      const button = el("presetBrandCreateBtn");
      const previousButton = setButtonBusy(button, "Applying Brand");
      try {
        if (selectedBrand?.name && selectedBrand.name.toLowerCase() === activeCsvPresetConfig.brand.name.toLowerCase()) {
          updatePresetBrandPanel(activeCsvPresetConfig.brand, true);
          setStatus(`${selectedBrand.name} already exists and is selected.`, "ok");
          return selectedBrand;
        }
        fillBrandFromConfig(activeCsvPresetConfig.brand);
        if (selectedBrand) {
          updatePresetBrandPanel(activeCsvPresetConfig.brand, true);
          setStatus(`${selectedBrand.name} already exists and is selected.`, "ok");
          return selectedBrand;
        }
      el("newBrandFields").classList.add("hidden");
      const created = await createNewBrand(activeCsvPresetConfig.brand.name, presetMetadata());
      if (created) {
        el("newBrandFields").classList.add("hidden");
        lockBrandFields(true);
        updatePresetBrandPanel(activeCsvPresetConfig.brand, true);
      }
      return created;
    } finally {
      clearButtonBusy(button, previousButton);
    }
  }

// === updateExistingBrand ===
async function updateExistingBrand() {
      if (!selectedBrand?.business_id) return null;
      const button = el("createBrandBtn");
      const presetButton = el("presetBrandCreateBtn");
      const previousButton = setButtonBusy(button, "Updating Brand");
      const previousPresetButton = setButtonBusy(presetButton, "Updating Brand");
      try {
        const response = await fetch("/api/brands/update", {
          method: "POST",
          headers: { "content-type": "application/json" },
        body: JSON.stringify(brandPayloadFromFields({ business_id: selectedBrand.business_id, ...(activeCsvPresetConfig ? presetMetadata() : {}) }))
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not update brand.");
        selectedBrand = result.brand;
        await loadBrands(selectedBrand.name);
        el("brandSelect").value = selectedBrand.business_id;
        fillBrandFields(selectedBrand, activeCsvPresetConfig?.brand || {});
        presetBrandEditMode = false;
        el("newBrandFields").classList.add("hidden");
        updatePresetBrandPanel(activeCsvPresetConfig?.brand || selectedBrand, true);
        updateOutput();
        setStatus(`Business ${selectedBrand.name} updated.`, "ok");
        return selectedBrand;
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not update business."), "error");
        return null;
      } finally {
        clearButtonBusy(button, previousButton);
        clearButtonBusy(presetButton, previousPresetButton);
      }
    }

// === brandPayloadFromFields ===
function brandPayloadFromFields(extra = {}) {
      return {
        ...extra,
        name: el("newBrandName").value.trim(),
        source_type_id: el("newBrandSourceType").value || currentSourceTypeId(),
        source_type: el("sourceType").value,
        slug: el("newBrandSlug").value.trim(),
        description: el("newBrandDescription").value.trim(),
        logo_url: el("newBrandLogo").value.trim(),
        website_url: el("newBrandWebsite").value.trim(),
        status: el("newBrandStatus").value,
        meta_title: el("newBrandMetaTitle").value.trim(),
        meta_description: el("newBrandMetaDescription").value.trim(),
        country_of_origin: el("newBrandOrigin").value.trim()
      };
    }

// === customFieldBusinessId ===
function customFieldBusinessId(mode = "add") {
      const pickerId = mode === "drop" ? "dropCustomFieldBusinessSelect" : "customFieldBusinessSelect";
      const pickerVal = el(pickerId)?.value;
      const brandVal = selectedBrand?.business_id;
      const topSelectVal = el("brandSelect")?.value;
      return pickerVal || brandVal || (topSelectVal && topSelectVal !== "__create_new__" ? topSelectVal : "") || "";
    }

// === syncCustomFieldBusinessPickers ===
function syncCustomFieldBusinessPickers() {
      const brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      const options = '<option value="">Select brand</option>' + brands
        .map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(brand.name)}</option>`).join("");
      const activeBusinessId = selectedBrand?.business_id || (el("brandSelect")?.value !== "__create_new__" ? el("brandSelect")?.value : "") || "";
      ["customFieldBusinessSelect", "dropCustomFieldBusinessSelect"].forEach((id) => {
        const picker = el(id);
        if (!picker) return;
        picker.innerHTML = options;
        picker.value = activeBusinessId || picker.value || "";
      });
      updateDropCustomFieldPicker();
    }

// === setDropCustomFieldFeedback ===
function setDropCustomFieldFeedback(message, type = "") {
      const target = el("dropCustomFieldFeedback");
      if (!target) return;
      target.className = `action-feedback ${type}`;
      target.textContent = message;
    }

// === saveDraft ===
function saveDraft() {
      if (!sourceParsed) return;
      const sessionId = sessionStorage.getItem(mappingSessionStorageKey);
      if (!sessionId) return;
      const draft = {
        sessionId,
        sourceType: el("sourceType").value,
        csvFunction: document.querySelector("input[name='csvFunction']:checked")?.value || "new",
        excelFunction: document.querySelector("input[name='excelFunction']:checked")?.value || "new",
        jsonFunction: document.querySelector("input[name='jsonFunction']:checked")?.value || "new",
        brandSelect: el("brandSelect").value,
        selectedBrand,
        sourceName: el("sourceName").value,
        sourceInputMode: el("sourceInputMode").value,
        sourceUrl: el("sourceUrl").value,
        recordExtractionMode: document.querySelector('input[name="recordExtractionMode"]:checked')?.value || "auto",
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

// === restoreDraft ===
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
        excelFunctionMode = draft.excelFunction || "new";
        jsonFunctionMode = draft.jsonFunction || "new";
        el("sourceType").value = draft.sourceType || "csv";
        const csvFunctionOption = document.querySelector(`input[name='csvFunction'][value="${CSS.escape(csvFunctionMode)}"]`);
        if (csvFunctionOption) csvFunctionOption.checked = true;
        const excelFunctionOption = document.querySelector(`input[name='excelFunction'][value="${CSS.escape(excelFunctionMode)}"]`);
        if (excelFunctionOption) excelFunctionOption.checked = true;
        const jsonFunctionOption = document.querySelector(`input[name='jsonFunction'][value="${CSS.escape(jsonFunctionMode)}"]`);
        if (jsonFunctionOption) jsonFunctionOption.checked = true;
        el("sourceName").value = draft.sourceName || "";
        el("sourceInputMode").value = draft.sourceInputMode || "file";
        el("sourceUrl").value = draft.sourceUrl || "";
        const restoredExtractionMode = draft.recordExtractionMode || (draft.recordPath ? "custom" : "auto");
        const extractionModeRadio = document.querySelector(`input[name='recordExtractionMode'][value="${CSS.escape(restoredExtractionMode)}"]`);
        if (extractionModeRadio) extractionModeRadio.checked = true;
        el("customRecordPathContainer")?.classList.toggle("hidden", restoredExtractionMode !== "custom");
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

// === masterDeleteData ===
function masterDeleteData() {
      const firstDialog = el("masterDeleteCredentialsDialog");
      el("masterDeletePassword").value = "";
      el("masterDeleteConfirmation").value = "";
      if (typeof firstDialog.showModal === "function") {
        firstDialog.showModal();
        return;
      }
      if (window.confirm("MASTER DATA DELETION: continue to credential confirmation?")) {
        el("masterDeleteCredentialNextBtn").click();
      }
    }

// === proceedMasterDeleteConfirmation ===
function proceedMasterDeleteConfirmation() {
      el("masterDeleteCredentialsDialog").close();
      const confirmDialog = el("masterDeleteConfirmDialog");
      if (typeof confirmDialog.showModal === "function") {
        confirmDialog.showModal();
        return;
      }
      if (window.confirm("Type confirmation is required in the app dialog.")) {
        confirmDialog.showModal();
      }
    }

// === performMasterDeleteData ===
async function performMasterDeleteData() {
      const status = el("masterDeleteStatus");
      const button = el("masterDeleteBtn");
      const confirmButton = el("confirmMasterDeleteBtn");
      const payload = {
        username: el("masterDeleteUser").value.trim(),
        password: el("masterDeletePassword").value,
        confirmation: el("masterDeleteConfirmation").value.trim()
      };
      if (payload.confirmation !== "DELETE ALL DATA") {
        status.className = "action-feedback error";
        status.textContent = "Type DELETE ALL DATA to confirm.";
        return;
      }
      button.disabled = true;
      const previousConfirmButton = setButtonBusy(confirmButton, "Deleting");
      status.className = "action-feedback";
      status.innerHTML = busyMarkup("Deleting");
      try {
        const response = await fetch("/api/master-delete", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Master deletion failed.");
        el("masterDeleteConfirmDialog").close();
        status.className = "action-feedback ok";
        status.textContent = `Master deletion complete. Dropped ${result.dropped_count || 0} tables.`;
        setStatus("Master data deletion complete. Warehouse is back to no-tables state.", "ok");
        window.alert(`Master data deletion complete. Dropped ${result.dropped_count || 0} warehouse objects across all layers. You will be logged out now.`);
        sourceRows = [];
        sourceFields = [];
        sourceParsed = false;
        mappingSelections = {};
        selectedBrand = null;
        appDataLoaded = false;
        logout();
        prepareReferenceData();
      } catch (error) {
        status.className = "action-feedback error";
        status.textContent = productSafeError(error.message, "Master deletion failed.");
      } finally {
        button.disabled = false;
        clearButtonBusy(confirmButton, previousConfirmButton);
      }
    }

// === applyDemoRestaurantExcel ===
function applyDemoRestaurantExcel() {
      resetPresetBrandEditState();
      excelFunctionMode = "demo_restaurant";
      activeCsvPresetConfig = null;
      presetBrandEditMode = false;
      el("sourceType").value = "excel";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.demoRestaurantExcelUrl || "";
      el("sourceUrl").placeholder = window.APP_CONSTANTS.demoRestaurantExcelUrl || sourceUrlPlaceholders.excel;
      setSourceUrlLocked(true);
      el("sourceName").value = "demo_restaurant_locations_excel";
      el("recordPath").value = "Sheet1";
      applyBrandToCurrentSelection(firstExistingBrand());
      sourceFields = [];
      sourceRows = [];
      sourceParsed = false;
      mappingSelections = {};
      updateSourceVisibility();
      loadExcelSheets();
      renderMappings();
      updateOutput();
      setStatus(selectedBrand ? "Demo Restaurant Excel URL is ready with an existing brand. Click Parse." : "Demo Restaurant Excel URL is ready. Choose or create a brand, then click Parse.", selectedBrand ? "ok" : "warn");
    }

// === setDemoRestaurantExcelMappings ===
function setDemoRestaurantExcelMappings() {
      mappingSelections = {
        name: "restaurant_name",
        address: "street_address",
        city: "city_name",
        state: "state",
        postal_code: "postal_code",
        latitude: "latitude",
        longitude: "longitude",
        country: "country_name",
        phone_number: "phone",
        franchise_name: "franchise_name",
        concept_type: "concept_type",
        cuisine_type: "cuisine",
        neighborhood: "neighborhood",
        district: "district",
        website_url: "website",
        google_maps_link: "google_maps_url"
      };
      optionalMappingKeys = new Set(["latitude", "longitude", "country", "phone_number", "franchise_name", "concept_type", "cuisine_type", "neighborhood", "district", "website_url", "google_maps_link"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }

// === resetExcelDemoLock ===
function resetExcelDemoLock() {
      resetPresetBrandEditState();
      excelFunctionMode = "new";
      resetSourceInputsForNewMode("excel");
    }

// === updateExcelFunctionSelection ===
function updateExcelFunctionSelection(value) {
      resetPresetBrandEditState();
      if (value === "demo_restaurant") applyDemoRestaurantExcel();
      else resetExcelDemoLock();
    }

// === applyCsvPreset ===
function applyCsvPreset(config) {
      resetPresetBrandEditState();
      activeCsvPresetConfig = config;
      csvFunctionMode = config.mode;
      el("sourceType").value = "csv";
      fillBrandFromConfig(config.brand || {});
      el("sourceInputMode").value = "url";
      const dbSourceUrl = selectedBrand?.reference_key === config.mode ? selectedBrand.default_source_url : "";
      const dbSourceName = selectedBrand?.reference_key === config.mode ? selectedBrand.default_source_name : "";
      el("sourceUrl").value = dbSourceUrl || config.url || "";
      el("sourceUrl").placeholder = dbSourceUrl || config.url || sourceUrlPlaceholders.csv;
      setSourceUrlLocked(true);
      el("sourceName").value = dbSourceName || config.sourceName || "";
      el("recordPath").value = "";
      sourceFields = [];
      sourceRows = [];
      sourceParsed = false;
      mappingSelections = {};
      updateSourceVisibility();
      renderMappings();
      updateOutput();
      updatePresetBrandPanel(config.brand || {}, Boolean(selectedBrand));
      setStatus(config.status || "CSV preset ready. Click Parse.", config.statusType || "ok");
    }

// === updateSourcePlaceholders ===
function updateSourcePlaceholders(sourceType = el("sourceType").value) {
      el("sourceUrl").placeholder = sourceUrlPlaceholders[sourceType] || "https://example.com/restaurant_locations.json";
      el("apiUrl").placeholder = sourceType === "api_get_json" ? "https://example.com/stores.json" : "https://example.com/restaurant_locations.json";
      el("sourceName").placeholder = sourceNamePlaceholders[sourceType] || "restaurant_locations";
      el("recordPath").placeholder = recordPathPlaceholders[sourceType] || "";
      el("fileInput").title = sourceType === "excel"
        ? "Upload an .xlsx or .xls workbook."
        : sourceType === "csv"
          ? "Upload a .csv file."
          : sourceType === "json"
            ? "Upload a .json or .geojson file."
            : sourceType === "xml"
              ? "Upload an .xml file."
              : "";
    }

// === remoteFileNameForSource ===
function remoteFileNameForSource(sourceResult, sourceUrl, fallbackName = "remote_source") {
      const rawName = sourceResult?.file_name || fallbackName;
      const hasExtension = /\.[a-z0-9]+$/i.test(rawName);
      if (hasExtension) return rawName;
      try {
        const url = new URL(sourceUrl);
        const output = (url.searchParams.get("output") || "").toLowerCase().replace(/^\./, "");
        if (["csv", "xlsx", "xls", "json", "xml"].includes(output)) return `${rawName}.${output}`;
      } catch (_error) {
        // Keep the server-provided name when the URL is not parseable in this browser.
      }
      return rawName;
    }

// === fileToBase64 ===
function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    }

// === textToBase64 ===
function textToBase64(value) {
      const bytes = new TextEncoder().encode(value);
      let binary = "";
      bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
      return btoa(binary);
    }

// === isExcelFile ===
function isExcelFile(file) {
      if (!file) return false;
      const lower = file.name.toLowerCase();
      return lower.endsWith(".xlsx") || lower.endsWith(".xls");
    }

// === loadSampleDataset ===
async function loadSampleDataset(reset = false) {
      const button = el("loadSampleDatasetBtn");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!reset && button?.dataset.sampleLoaded === "true") return;
      const previousButton = setButtonBusy(button, reset ? "Reloading" : "Loading Sample Data");
      const previousReload = reloadLink ? setButtonBusy(reloadLink, "Reloading") : "";
      const status = el("reportStatus");
      status.className = "report-status loading";
      status.classList.remove("hidden");
      // Sample loading now returns as soon as bronze data is in (silver/gold
      // rebuild in the background - see _background_medallion_refresh_status
      // server-side), so this is a much shorter wait than it used to be.
      // Show progress inline here, below the Refresh Report button, instead
      // of a full-screen overlay. The spinner + sliding bar (.report-status
      // .spinner / .loading::after) make clear it's actively working rather
      // than stuck, since the percentage alone is only an estimate.
      const estimatedSeconds = reset ? 25 : 15;
      const startedAt = Date.now();
      const progressLabel = reset ? "Clearing and reloading sample dataset" : "Loading sample dataset";
      const renderProgress = (percent) => {
        status.innerHTML = `<span class="spinner"></span> ${progressLabel} (${percent}%)...`;
      };
      renderProgress(0);
      const progressTimer = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000);
        const percent = Math.min(94, Math.round(elapsed / estimatedSeconds * 100));
        renderProgress(percent);
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
        status.textContent = `${progressLabel} (100%)...`;
        await loadBrands();
        await loadTemplateFilters();
        reportLoaded = false;
        await loadReporting();
        const sourceTypesSummary = Object.entries(result.source_types || {}).map(([name, count]) => `${name}: ${count}`).join(", ");
        const reportingRows = result.silver?.rows;
        const reportingStatusSuffix = reportingRows !== undefined
          ? `, ${formatNumber(reportingRows)} ready for reporting`
          : (result.silver?.status === "refreshing" ? ", reporting is updating in the background" : "");
        const message = result.already_loaded
          ? `Sample dataset already loaded${reportingStatusSuffix}.`
          : `Sample dataset loaded: ${formatNumber(result.locations)} records, ${formatNumber(result.errors)} in review${reportingStatusSuffix}${sourceTypesSummary ? ` (${sourceTypesSummary})` : ""}.`;
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
        clearButtonBusy(button, previousButton);
        if (reloadLink) clearButtonBusy(reloadLink, previousReload);
        if (button && button.dataset.sampleLoaded !== "true") button.disabled = false;
        if (reloadLink) reloadLink.disabled = false;
      }
    }

// === updateSampleDatasetControls ===
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

// === refreshSampleDatasetStatus ===
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

// === loadConnectorPackages ===
async function loadConnectorPackages(pyodide, code) {
      const requested = el("pythonPackages").value.split(",").map((name) => name.trim()).filter(Boolean);
      if (/^\s*(?:from\s+requests\s+import|import\s+requests\b)/m.test(code) && !requested.includes("requests")) requested.push("requests");
      if (requested.length) {
        setConnectorFeedback("Loading packages...", "");
        await pyodide.loadPackage(requested);
      }
    }

// === inferSourceType ===
function inferSourceType(fileName) {
      const lower = fileName.toLowerCase();
      if (lower.endsWith(".xlsx") || lower.endsWith(".xls")) return "excel";
      if (lower.endsWith(".json") || lower.endsWith(".geojson")) return "json";
      if (lower.endsWith(".xml")) return "xml";
      return "csv";
    }

// === validateSelectedFileType ===
function validateSelectedFileType(file) {
      const selectedType = el("sourceType").value;
      if (!sourceFileAccept[selectedType]) return;
      const inferredType = inferSourceType(file.name);
      if (inferredType !== selectedType) {
        throw new Error(`Selected source format is ${selectedType.toUpperCase()}. Choose a matching ${selectedType === "json" ? "JSON or GeoJSON" : selectedType.toUpperCase()} file.`);
      }
    }

// === populateJsonRecordPaths ===
function populateJsonRecordPaths(paths) {
      // The standalone "JSON record layer" dropdown was removed as redundant -
      // Automatic mode auto-detects the layer and Custom mode takes a typed
      // record path. We still track the detected paths for draft persistence
      // and auto-resolution, but no longer render a picker for them.
      jsonRecordPaths = Array.isArray(paths) ? paths : [];
    }

// === collectPairs ===
function collectPairs(targetId) {
      return Array.from(el(targetId).querySelectorAll(".source-row"))
        .map((row) => ({
          key: row.querySelector("[data-pair-key]").value.trim(),
          value: row.querySelector("[data-pair-value]").value.trim()
        }))
        .filter((pair) => pair.key);
    }

// === collectAuth ===
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

// === suggestField ===
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

// === sampleValue ===
function sampleValue(path) {
      for (const row of sourceRows.slice(0, 10)) {
        const value = getByPath(row, path);
        if (value !== undefined && value !== null && value !== "") return String(value);
      }
      return "";
    }

// === applyMappingSelection ===
function applyMappingSelection(key, nextValue, selectElement) {
      const previousOwner = Object.entries(mappingSelections).find(([otherKey, value]) => otherKey !== key && value === nextValue);
      if (nextValue && previousOwner) {
        const previousTarget = mappingTargets.find((target) => target.key === previousOwner[0]);
        const currentTarget = mappingTargets.find((target) => target.key === key);
        const move = window.confirm(`${nextValue} is already mapped to ${previousTarget ? previousTarget.label : previousOwner[0]}. Move it to ${currentTarget ? currentTarget.label : key}?\n\nChoose Cancel to keep it mapped to ${previousTarget ? previousTarget.label : previousOwner[0]}.`);
        if (!move) {
          if (selectElement) selectElement.value = mappingSelections[key] || "";
          return;
        }
        mappingSelections[previousOwner[0]] = "";
        autoMappedKeys.delete(previousOwner[0]);
        setStatus(`Moved ${nextValue} from ${previousTarget ? previousTarget.label : previousOwner[0]} to ${currentTarget ? currentTarget.label : key}.`, "warn");
      }
      mappingSelections[key] = nextValue;
      autoMappedKeys.delete(key);
      renderMappings();
    }

// === getVisibleTargets ===
function getVisibleTargets() {
      const targets = mappingTargets.filter((target) => primaryMappingKeys.has(target.key) && !hiddenMappingKeys.has(target.key));
      optionalMappingKeys.forEach((key) => {
        const found = mappingTargets.find((target) => target.key === key);
        if (found && !targets.some((target) => target.key === key)) targets.push(found);
      });
      return targets;
    }

// === buildTargetRow ===
function buildTargetRow(target, availableOptionsList, selected) {
      const row = document.createElement("div");
      row.className = "mapping-row";
      const sampleValue = getSampleValue(selected);
      const isAutoMapped = autoMappedKeys.has(target.key);
      row.innerHTML = `
        <div class="target-field">
          <strong>${escapeHtml(target.label)}</strong>
          ${target.required ? '<span class="required-badge">Required</span>' : ""}
          <span class="info-icon" tabindex="0" data-tooltip="${escapeHtml(target.note)}">i</span>
          ${isAutoMapped ? '<span class="auto-badge" title="Automatically mapped by source matcher">Auto</span>' : ""}
        </div>
        <select data-mapping-key="${escapeHtml(target.key)}">
          <option value="">(Not mapped)</option>
          ${availableOptionsList.map((field) => `<option value="${escapeHtml(field)}"${field === selected ? " selected" : ""}>${escapeHtml(field)}</option>`).join("")}
        </select>
        <div class="sample-value" title="${escapeHtml(sampleValue)}">${escapeHtml(sampleValue || "—")}</div>
        <div class="row-actions">
          ${!target.required ? `<button class="secondary remove-mapping-btn" type="button" data-remove-key="${escapeHtml(target.key)}" title="Remove this field">✕</button>` : ""}
        </div>
      `;
      const select = row.querySelector("select");
      select.addEventListener("change", (event) => {
        autoMappedKeys.delete(target.key);
        mappingSelections[target.key] = event.target.value;
        renderMappings();
      });
      const removeBtn = row.querySelector(".remove-mapping-btn");
      if (removeBtn) {
        removeBtn.addEventListener("click", () => {
          autoMappedKeys.delete(target.key);
          delete mappingSelections[target.key];
          if (primaryMappingKeys.has(target.key)) hiddenMappingKeys.add(target.key);
          else optionalMappingKeys.delete(target.key);
          renderMappings();
        });
      }
      return row;
    }

// === normalizedRows ===
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

// === validateMapper ===
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

// === renderEntityMap ===
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
        <div class="entity-field source-row-item">
          <div class="entity-field-name">${escapeHtml(field)}</div>
          <div class="entity-field-source ${mappedSourceFields.has(field) ? "mapped" : "unmapped"}">${mappedSourceFields.has(field) ? "&#10003; Mapped" : "Unmapped"}</div>
        </div>
      `).join("");
      const entityItems = Object.entries(groupedTargets).map(([table, fields]) => `
        <div class="entity-box">
          <div class="entity-title">${escapeHtml(entityNames[table] || table)}</div>
          <div class="entity-subtitle">Fields received from the source</div>
          <div class="entity-fields">${fields.map((item) => {
            const source = mappingSelections[item.key] || "";
            const options = ['<option value="">(Unmapped)</option>']
              .concat(sourceFields.map((field) => {
                const owner = Object.entries(mappingSelections).find(([, value]) => value === field);
                const ownerLabel = owner && owner[0] !== item.key ? mappingTargets.find((t) => t.key === owner[0])?.label : "";
                const isSelected = field === source;
                return `<option value="${escapeHtml(field)}"${isSelected ? " selected" : ""}>${escapeHtml(field)}${ownerLabel ? ` (mapped to ${escapeHtml(ownerLabel)})` : ""}</option>`;
              }))
              .join("");
            return `
              <div class="entity-field">
                <div class="entity-field-name">${escapeHtml(item.label)}${item.required ? ' <span style="color:#cf1322;">*</span>' : ''}</div>
                <div class="entity-field-source ${source ? "mapped" : "unmapped"}">${source ? `&#8592; ${escapeHtml(source)}` : "Unmapped"}</div>
                <select class="entity-map-select" data-field="${escapeHtml(item.key)}" aria-label="Map ${escapeHtml(item.label)}">${options}</select>
              </div>
            `;
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
      target.querySelectorAll(".entity-map-select").forEach((select) => {
        select.addEventListener("change", () => {
          const key = select.dataset.field;
          const nextValue = select.value;
          applyMappingSelection(key, nextValue, select);
        });
      });
    }

// === renderTable ===
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

// === mapperHasField ===
function mapperHasField(key) {
      return Boolean(mappingSelections[key]);
    }

// === mapperHasSource ===
function mapperHasSource(field) {
      return Object.values(mappingSelections).includes(field);
    }

// === getMappedSourceLabel ===
function getMappedSourceLabel(key) {
      const sourceField = mappingSelections[key];
      return sourceField ? `&#10003; ${escapeHtml(sourceField)}` : "Unmapped";
    }

// === buildSaveBatches ===
function buildSaveBatches(rows, mapper, sourceFields) {
      const overhead = JSON.stringify({ mapper, source_fields: sourceFields, rows: [] }).length;
      const batches = [];
      let currentRows = [];
      let currentBytes = overhead;
      let rowOffset = 0;
      rows.forEach((row, index) => {
        const rowBytes = JSON.stringify(row).length + 2;
        if (currentRows.length && (currentBytes + rowBytes > BATCH_MAX_BYTES || currentRows.length >= BATCH_MAX_ROWS)) {
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

// === getMapper ===
function getMapper() {
      const fields = {};
      mappingTargets.forEach((target) => {
        if (mappingSelections[target.key]) fields[target.key] = mappingSelections[target.key];
      });
      const selectedOption = el("brandSelect").selectedOptions[0];
      const manualBrand = selectedBrand?.name || el("newBrandName").value.trim() || (selectedOption && selectedOption.value !== "__create_new__" ? selectedOption.textContent : "");
      const resolvedBrand = manualBrand || "Default Brand";
      const sourceFieldUniverse = Array.from(new Set([
        ...sourceFields,
        ...Object.values(fields).filter(Boolean),
      ]));
      const recordExtractionMode = document.querySelector('input[name="recordExtractionMode"]:checked')?.value || "auto";
      const mapper = {
        brand: resolvedBrand,
        business_id: selectedBrand?.business_id || (selectedOption && selectedOption.value !== "__create_new__" ? selectedOption.value : "") || "",
        source_type_id: currentSourceTypeId(),
        source_name: el("sourceName").value.trim(),
        source_type: el("sourceType").value,
        record_extraction_mode: recordExtractionMode,
        fields,
        source_fields: sourceFieldUniverse,
        aliases: customAliases
      };
      if (el("sourceInputMode").value === "url" && el("sourceUrl").value.trim()) {
        mapper.source_url = el("sourceUrl").value.trim();
      }
      const recordPath = recordExtractionMode === "custom" ? (el("recordPath").value.trim() || resolvedRecordPath) : "";
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
