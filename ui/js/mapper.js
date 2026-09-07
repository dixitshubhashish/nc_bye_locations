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
let sourceRecordCount = 0;
let lastSourcePreviewPayload = null;
let resolvedRecordPath = "";
let mappingSelections = {};
let jsonRecordPaths = [];
let autoMappedKeys = new Set();
let learnedSuggestions = {};
let sourceParsed = false;
// True while a template loaded from the Template Library is being edited
// without a freshly parsed source file. The mapping grid and Save must work
// off the template's stored source_fields (there are no live sourceRows),
// so this flag stands in for sourceParsed wherever the mapper only needs the
// column list, not actual row data.
let templateEditMode = false;
let selectedBrand = null;
let csvFunctionMode = "new";
// Batch size limits to prevent memory/network issues with large files
const BATCH_MAX_BYTES = 5 * 1024 * 1024;  // 5MB per batch
const BATCH_MAX_ROWS = 10000;              // 10k rows per batch
let excelFunctionMode = "new";
let jsonFunctionMode = "new";
let apiFunctionMode = "new";
let customAliases = {};
let lastSaveEventId = "";
let activeTemplateId = "";
let templateSaveLocked = false;
let connectorEditor = null;
let pyodideRuntimePromise = null;
let activeCsvPresetConfig = null;
let presetBrandEditMode = false;
let presetCreateMode = false;
let brandEditMode = false;
const pythonEditorStarterCode = `# Return a JSON-compatible list of records in \`result\`.
result = [
    {
        "name": "Sample Bistro",
        "address": "100 Main St",
        "city": "Raleigh",
        "state": "NC",
        "postal_code": "27601"
    }
]`;

const draftStorageKey = "competitive_whitespace_mapping_draft";
const draftPreviewRowLimit = 10;
const saveBatchTargetBytes = 4 * 1024 * 1024;
const saveBatchMinRows = 250;

function normalizeName(value) {
      return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    }
function sourceReadyToParseMessage() {
      const sourceType = el("sourceType");
      const format = sourceType?.selectedOptions?.[0]?.textContent?.trim() || "source";
      const selectedRadio = document.querySelector(`input[name='${sourceType?.value === "csv" ? "csvFunction" : sourceType?.value === "excel" ? "excelFunction" : sourceType?.value === "json" ? "jsonFunction" : sourceType?.value === "xml" ? "xmlFunction" : sourceType?.value === "api_get_json" ? "apiFunction" : "pythonFunction"}']:checked`);
      const mode = selectedRadio?.value === "new" ? "New" : "Demo";
      const inputMode = el("sourceInputMode")?.value;
      const hasInput = sourceType?.value === "python_editor"
        ? Boolean(el("pythonCode")?.value?.trim())
        : inputMode === "file"
        ? Boolean(el("fileInput")?.files?.length)
        : Boolean(el("sourceUrl")?.value?.trim()) || Boolean(el("apiUrl")?.value?.trim());
      if (!hasInput) {
        if (sourceType?.value === "python_editor") return `${mode} ${format} source needs connector code before parsing.`;
        return inputMode === "file"
          ? `${mode} ${format} upload needs a file before parsing.`
          : `${mode} ${format} source needs a public URL before parsing.`;
      }
      const inputText = inputMode === "file" ? "as an upload" : "from a public URL";
      return `${mode} ${format} source ${inputText} is ready to parse.`;
    }
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
function similarBusinessKey(name = "") {
      return normalizeName(name).replace(/\b(inc|llc|ltd|usa|us|global|stores|locations)\b/g, "");
    }
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
function businessCreatedTime(brand = {}) {
      const value = Date.parse(brand.created_at || "");
      return Number.isFinite(value) ? value : 0;
    }
function businessOptionLabel(brand = {}, newestCreatedAt = 0) {
      const newest = newestCreatedAt && businessCreatedTime(brand) === newestCreatedAt ? "Newest, " : "";
      return `${formatBrandName(brand.name || "Unnamed")} (${brand.display_business_id || "BID --------"}, ${formatNumber(brand.listing_count || 0)} listings, ${newest}created ${brand.created_at ? new Date(brand.created_at).toLocaleDateString() : "unknown"})`;
    }
function businessOptionLabelShort(brand = {}) {
      return `${formatBrandName(brand.name || "Unnamed")} (${brand.display_business_id || "BID --------"})`;
    }
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
      const sourceTypeSelect = el("newBrandSourceType");
      if (!sourceTypeSelect) return;
      const match = Array.from(sourceTypeSelect.options).find((option) => option.dataset.format === format || option.value === format);
      if (match) el("newBrandSourceType").value = match.value;
    }
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
function presetMetadata(config = activeCsvPresetConfig || {}) {
      return {
        is_reference_data: true,
        reference_key: config.mode || "",
        default_source_url: el("sourceUrl")?.value.trim() || config.url || "",
        default_source_name: el("sourceName")?.value.trim() || config.sourceName || ""
      };
    }
function lockBrandFields(locked) {
      ["newBrandName", "newBrandSourceType", "newBrandSlug", "newBrandDescription", "newBrandLogo", "newBrandWebsite", "newBrandStatus", "newBrandMetaTitle", "newBrandMetaDescription", "newBrandOrigin", "createBrandBtn"].forEach((id) => {
        if (el(id)) el(id).disabled = Boolean(locked);
      });
    }
function populateSourceTypeSelects() {
      const fallbackSources = [
        { source_type_id: "csv", name: "csv" },
        { source_type_id: "api_get_json", name: "api_get_json" },
        { source_type_id: "excel", name: "excel" },
        { source_type_id: "json", name: "json" },
        { source_type_id: "python_editor", name: "python_editor" },
        { source_type_id: "xml", name: "xml" }
      ];
      const sources = sourceTypes.length ? [...sourceTypes] : fallbackSources;
      const orderedSources = sources.sort((left, right) => {
        const leftFormat = sourceTypeNameToFormat(left.name);
        const rightFormat = sourceTypeNameToFormat(right.name);
        if (leftFormat === "csv" && rightFormat !== "csv") return -1;
        if (rightFormat === "csv" && leftFormat !== "csv") return 1;
        return sourceTypeLabel(leftFormat || left.name).localeCompare(sourceTypeLabel(rightFormat || right.name));
      });
      const options = orderedSources.map((source) => {
        const format = sourceTypeNameToFormat(source.name);
        return `<option value="${escapeHtml(source.source_type_id)}" data-format="${escapeHtml(format)}">${escapeHtml(sourceTypeLabel(format || source.name))}</option>`;
      }).join("");
      el("newBrandSourceType").innerHTML = `<option value="">SELECT SOURCE FORMAT</option>${options}`;
    }
function resetTemplateSelection() {
      activeTemplateId = "";
      templateSaveLocked = false;
      el("templateSearch").value = "";
      el("templateResults").className = "status";
      el("templateResults").textContent = "Search saved templates to edit an existing mapping.";
    }
function applyBusinessSourceType(business, options = {}) {
      const preserveSourceType = options.preserveSourceType !== false;
      const sourceTypeId = business?.source_type_id || "";
      const format = sourceTypeIdToFormat(sourceTypeId) || sourceTypeNameToFormat(business?.source_type_name || "");
      if (format && !preserveSourceType) {
        el("sourceType").value = format;
        updateSourceVisibility();
      }
      el("sourceType").disabled = false;
      el("sourceInputMode").disabled = false;
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
      const code = connectorEditor ? connectorEditor.getValue() : el("pythonConnectorCode").value;
      return String(code || "").trim() ? code : pythonEditorStarterCode;
    }
function setConnectorCode(code) {
      const nextCode = String(code || "").trim() ? String(code) : pythonEditorStarterCode;
      if (connectorEditor) connectorEditor.setValue(nextCode);
      else el("pythonConnectorCode").value = nextCode;
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
        presetCreateMode = false;
        el("brandSelect").value = existing.business_id;
        el("editExistingBrandLink")?.classList.remove("hidden");
        el("newBrandFields").classList.add("hidden");
        fillBrandFields(existing, brandConfig);
        lockBrandFields(Boolean(activeCsvPresetConfig));
        applyBusinessSourceType(existing);
        updatePresetBrandPanel(brandConfig, true);
      } else {
        selectedBrand = null;
        el("brandSelect").value = "__create_new__";
        el("newBrandFields").classList.toggle("hidden", Boolean(activeCsvPresetConfig));
        fillBrandFields({}, brandConfig);
        lockBrandFields(false);
        updatePresetBrandPanel(brandConfig, false);
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
      setStatus("Demo source ready. Click Parse.", "ok");
    }
function updatePythonFunctionSelection(value) {
      el("demoPeBrandActions")?.classList.toggle("hidden", value !== "demo_pe_brand");
      if (value === "la_city") applyLaCityPythonFunction();
      else if (value === "demo_pe_brand") applyDemoPeBrandFunction();
      else setDominosLocked(false);
    }
async function loadDemoPeBrandCode(copyOnly = false) {
      const response = await fetch("/api/demo-python/pe-brand", { cache: "no-store" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load Demo PE Brand sample.");
      if (!copyOnly) setConnectorCode(result.code);
      return result.code;
    }
function setDemoPeBrandFeedback(message, type = "") {
      const target = el("demoPeBrandFeedback");
      if (!target) return;
      target.className = `demo-code-feedback ${type}`.trim();
      target.textContent = message;
    }
async function applyDemoPeBrandFunction() {
      el("sourceType").value = "python_editor";
      el("sourceName").value = "demo_pe_brand_osm_restaurants";
      el("recordPath").value = "";
      try {
        await loadDemoPeBrandCode();
        fillBrandFields({}, { name: "Demo PE Brand", slug: "demo-pe-brand", description: "Greater Los Angeles restaurant demo from Overpass.", websiteUrl: "https://www.openstreetmap.org/", status: "active", metaTitle: "Demo PE Brand", metaDescription: "Demo Python source for restaurant locations.", countryOfOrigin: "United States" });
        setStatus("Demo source loaded. Click Parse.", "ok");
        setDemoPeBrandFeedback("Sample loaded into the editor.", "ok");
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not load Demo PE Brand sample."), "error");
        setDemoPeBrandFeedback("Could not load the sample.", "error");
      }
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      updateSourceVisibility();
      renderMappings();
      updateOutput();
    }
function setLockedValue(id, value) {
      if (el(id)) el(id).value = value || "";
    }
function setPresetLocked(locked, controlIds) {
      // Keep all controls and mapping elements 100% enabled & fully editable
      (controlIds || []).forEach((id) => { if (el(id)) el(id).disabled = false; });
      if (!activeCsvPresetConfig || !selectedBrand) lockBrandFields(false);
      document.querySelectorAll("select[data-field]").forEach((select) => { select.disabled = false; });
      document.querySelectorAll("button[data-remove-field]").forEach((button) => { button.disabled = false; });
      if (el("addOptionalFieldBtn")) el("addOptionalFieldBtn").disabled = false;
      document.querySelector("aside .panel")?.classList.remove("locked-demo");
      el("mappingGrid")?.classList.remove("locked-demo");
    }
const sourceUrlPlaceholders = {
      csv: "https://example.com/restaurant_locations.csv",
      excel: "https://example.com/restaurant_locations.xlsx",
      json: "https://example.com/restaurant_locations.json",
      xml: "https://example.com/restaurant_locations.xml"
    };
const sourceNamePlaceholders = {
      csv: "restaurant_locations_csv",
      excel: "restaurant_locations_excel",
      json: "restaurant_locations_json",
      xml: "restaurant_locations_xml",
      api_get_json: "restaurant_locations_api",
      python_editor: "restaurant_locations_python"
    };
const recordPathPlaceholders = {
      csv: "",
      excel: "Sheet1",
      json: "stores or data.locations",
      xml: "locations.location",
      api_get_json: "stores or data.locations",
      python_editor: "records"
    };
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
function setSourceUrlLocked(locked) {
      el("sourceUrl").toggleAttribute("readonly", Boolean(locked));
      el("sourceUrl").classList.toggle("demo-url", Boolean(locked));
      const editButton = el("sourceUrlEditBtn");
      if (editButton) {
        editButton.classList.toggle("hidden", !locked || el("sourceInputMode").value !== "url");
        editButton.textContent = locked ? "Edit URL" : "URL editable";
      }
    }
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
function hidePresetBrandPanel() {
      activeCsvPresetConfig = null;
      presetBrandEditMode = false;
      presetCreateMode = false;
      el("presetBrandPanel")?.classList.add("hidden");
      el("brandSelect").disabled = false;
      el("brandSelect")?.classList.remove("hidden");
      el("brandSelectLabel")?.classList.remove("hidden");
      lockBrandFields(false);
      el("createBrandBtn")?.classList.toggle("hidden", Boolean(selectedBrand?.business_id) && !brandEditMode);
      el("newBrandFields")?.classList.toggle("hidden", el("brandSelect")?.value !== "__create_new__");
    }
function resetPresetBrandEditState() {
      presetBrandEditMode = false;
      presetCreateMode = false;
      el("newBrandFields")?.classList.add("hidden");
      lockBrandFields(false);
      el("presetBrandEditBtn")?.classList.remove("hidden");
      el("presetBrandCreateBtn")?.classList.remove("hidden");
      el("createBrandBtn")?.classList.toggle("hidden", Boolean(selectedBrand?.business_id) && !brandEditMode);
    }
function resetSourceInputsForNewMode(sourceType = el("sourceType").value) {
      const preservedBrand = selectedBrand;
      setPresetLocked(false, []);
      setSourceUrlLocked(false);
      hidePresetBrandPanel();
      selectedBrand = preservedBrand;
      if (selectedBrand?.business_id) {
        el("brandSelect").value = selectedBrand.business_id;
        el("editExistingBrandLink")?.classList.remove("hidden");
      }
      if (["csv", "excel", "json", "xml"].includes(sourceType)) {
      el("sourceInputMode").value = "url";
      }
      el("sourceUrl").value = "";
      el("apiUrl").value = "";
      updateSourcePlaceholders(sourceType);
      el("sourceName").value = "";
      el("recordPath").value = "";
      el("sheetName").innerHTML = '<option value="">Upload Excel to load sheets</option>';
      el("sheetName").disabled = true;
      const editLink = el("sourceUrlEditLink");
      if (editLink) editLink.remove();
      sourceRows = [];
      sourceFields = [];
      jsonRecordPaths = [];
      resolvedRecordPath = "";
      sourceParsed = false;
      templateEditMode = false;
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
      setStatus("Demo source ready. Click Parse.", "ok");
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
      applyCsvPreset({
        mode: "pizza_hut",
        brand: window.APP_CONSTANTS.pizzaHutBrand || {},
        url: window.APP_CONSTANTS.pizzaHutCsvDemoUrl || "",
        sourceName: "pizza_hut_locations_csv",
        status: "Demo source ready. Click Parse.",
        statusType: "ok"
      });
      setPizzaHutLocked(false);
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
      applyCsvPreset({
        mode: "global_hotels",
        brand: window.APP_CONSTANTS.globalHotelsBrand || {},
        url: window.APP_CONSTANTS.globalHotelsCorruptDemoUrl || "",
        sourceName: "global_hotels_mixed_csv",
        status: "Demo source ready. Click Parse.",
        statusType: "ok"
      });
      setPresetLocked(false, []);
    }
function resetCsvDemoLock() {
      resetPresetBrandEditState();
      csvFunctionMode = "new";
      resetSourceInputsForNewMode("csv");
      setStatus(sourceReadyToParseMessage(), "warn");
    }
function updateCsvFunctionSelection(value) {
      resetPresetBrandEditState();
      if (value === "pizza_hut") applyPizzaHutCsvDemo();
      else if (value === "global_hotels") applyGlobalHotelsCsvDemo();
      else resetCsvDemoLock();
    }
function firstExistingBrand() {
      const brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      return brands.find((brand) => brand?.business_id && String(brand.status || "active").toLowerCase() === "active")
        || brands.find((brand) => brand?.business_id)
        || null;
    }
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
      setStatus("Demo source ready. Click Parse.", "ok");
    }
function resetExcelDemoLock() {
      resetPresetBrandEditState();
      excelFunctionMode = "new";
      resetSourceInputsForNewMode("excel");
      setStatus(sourceReadyToParseMessage(), "warn");
    }
function updateExcelFunctionSelection(value) {
      resetPresetBrandEditState();
      if (value === "demo_restaurant") applyDemoRestaurantExcel();
      else resetExcelDemoLock();
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
function applyDominosJsonFunction() {
      jsonFunctionMode = "dominos";
      el("sourceType").value = "json";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.dominosJsonDemoUrl || "";
      setSourceUrlLocked(true);
      el("sourceName").value = "dominos_store_locator_json";
      el("recordPath").value = "Stores";
      fillDominosBrand();
      mappingSelections = {};
      sourceFields = [];
      sourceParsed = false;
      updateSourceVisibility();
      renderMappings();
      setDominosLocked(false);
      updateOutput();
      setStatus("Demo source ready. Click Parse.", "ok");
    }
function applyLaCityPythonFunction() {
      el("sourceType").value = "python_editor";
      el("sourceName").value = "la_city_restaurant_inspections_python";
      el("recordPath").value = "";
      setConnectorCode("");
      fillLaCityDemoBrand();
      mappingSelections = {};
      sourceFields = [];
      sourceRows = [];
      sourceParsed = false;
      renderMappings();
      updateOutput();
      setPresetLocked(false, []);
      setStatus("LA City Python editor ready. Add connector code when ready.", "ok");
    }
function resetJsonDemoLock() {
      jsonFunctionMode = "new";
      resetSourceInputsForNewMode("json");
      setStatus(sourceReadyToParseMessage(), "warn");
    }
function resetXmlDemoLock() {
      resetPresetBrandEditState();
      resetSourceInputsForNewMode("xml");
      setStatus(sourceReadyToParseMessage(), "warn");
    }
function applyDemoXml() {
      resetPresetBrandEditState();
      activeCsvPresetConfig = { mode: "demo_xml", brand: window.APP_CONSTANTS.demoXmlBrand || {}, url: window.APP_CONSTANTS.demoXmlUrl || "", sourceName: "demo_xml_complex_sample", status: "Demo source ready. Click Parse.", statusType: "ok" };
      el("sourceType").value = "xml";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.demoXmlUrl || "";
      el("sourceUrl").placeholder = window.APP_CONSTANTS.demoXmlUrl || sourceUrlPlaceholders.xml;
      setSourceUrlLocked(true);
      el("sourceName").value = "demo_xml_complex_sample";
      el("recordPath").value = "rootElement";
      fillBrandFromConfig(activeCsvPresetConfig.brand);
      updatePresetBrandPanel(activeCsvPresetConfig.brand, Boolean(selectedBrand));
      sourceFields = [];
      sourceRows = [];
      sourceParsed = false;
      mappingSelections = {};
      updateSourceVisibility();
      renderMappings();
      updateOutput();
      setStatus("Demo source ready. Click Parse.", "ok");
    }
function updateXmlFunctionSelection(value) {
      if (value === "demo_xml") applyDemoXml();
      else resetXmlDemoLock();
    }
function updateJsonFunctionSelection(value) {
      if (value === "dominos") applyDominosJsonFunction();
      else resetJsonDemoLock();
    }
function clearPairRows(targetId) {
      const target = el(targetId);
      if (target) target.innerHTML = "";
    }
function setLittleCaesarsApiMappings() {
      mappingSelections = {
        location_id: "place_id",
        name: "name",
        address: "display_name",
        city: "address.city",
        state: "address.state",
        postal_code: "address.postcode",
        country: "address.country",
        latitude: "lat",
        longitude: "lon",
        phone_number: "extratags.phone",
        website_url: "extratags.website"
      };
      optionalMappingKeys = new Set(["location_id", "country", "latitude", "longitude", "phone_number", "website_url"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function applyLittleCaesarsApiDemo() {
      apiFunctionMode = "little_caesars";
      activeCsvPresetConfig = {
        mode: "little_caesars",
        brand: window.APP_CONSTANTS.littleCaesarsBrand || {},
        url: window.APP_CONSTANTS.littleCaesarsApiDemoUrl || "",
        sourceName: "little_caesars_locations_api",
        status: "Little Caesars GET API source from a public URL is ready to parse.",
        statusType: "ok"
      };
      el("sourceType").value = "api_get_json";
      el("apiUrl").value = window.APP_CONSTANTS.littleCaesarsApiDemoUrl || "";
      el("sourceName").value = "little_caesars_locations_api";
      el("recordPath").value = "";
      el("authType").value = "none";
      clearPairRows("queryParams");
      clearPairRows("customHeaders");
      addPairRow("queryParams", "q", "restaurants near Manhattan New York", "q", "restaurants near Manhattan New York");
      addPairRow("queryParams", "viewbox", "-74.02,40.78,-73.94,40.70", "viewbox", "-74.02,40.78,-73.94,40.70");
      addPairRow("queryParams", "bounded", "1", "bounded", "1");
      addPairRow("queryParams", "countrycodes", "us", "countrycodes", "us");
      addPairRow("queryParams", "format", "json", "format", "json");
      addPairRow("queryParams", "addressdetails", "1", "addressdetails", "1");
      addPairRow("queryParams", "extratags", "1", "extratags", "1");
      addPairRow("queryParams", "namedetails", "1", "namedetails", "1");
      addPairRow("queryParams", "limit", "25", "limit", "25");
      addPairRow("customHeaders", "Accept", "application/json", "Accept", "application/json");
      addPairRow("customHeaders", "User-Agent", "CompetitiveWhitespaceTool/1.0", "User-Agent", "CompetitiveWhitespaceTool/1.0");
      addPairRow("customHeaders", "Accept-Language", "en", "Accept-Language", "en");
      fillBrandFromConfig(activeCsvPresetConfig.brand);
      updatePresetBrandPanel(activeCsvPresetConfig.brand, Boolean(selectedBrand));
      setLittleCaesarsApiMappings();
      updateAuthVisibility();
      updateSourceVisibility();
      renderMappings();
      setPresetLocked(false, []);
      updateOutput();
      setStatus("Little Caesars GET API source from a public URL is ready to parse.", "ok");
    }
function resetApiDemoLock() {
      apiFunctionMode = "new";
      activeCsvPresetConfig = null;
      presetCreateMode = false;
      clearPairRows("queryParams");
      clearPairRows("customHeaders");
      resetSourceInputsForNewMode("api_get_json");
      setStatus(sourceReadyToParseMessage(), "warn");
    }
function updateApiFunctionSelection(value) {
      if (value === "little_caesars") applyLittleCaesarsApiDemo();
      else resetApiDemoLock();
    }
function isNewSourceMode() {
      const sourceType = el("sourceType").value;
      return (
        sourceType === "csv" && csvFunctionMode === "new"
        || sourceType === "excel" && excelFunctionMode === "new"
        || sourceType === "json" && jsonFunctionMode === "new"
        || sourceType === "api_get_json" && apiFunctionMode === "new"
        || !["csv", "excel", "json", "api_get_json"].includes(sourceType)
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
        el("sourceInputMode").value = draft.sourceInputMode || "url";
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
        setDominosLocked(jsonFunctionMode === "dominos");
        setLaCityDemoLocked((draft.pythonFunction || "new") === "la_city");
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
        // The standard field catalog is fixed, independent of any parsed
        // source file - keep "Available optional fields" populated as soon
        // as it loads, not only after the user parses a source.
        if (sourceParsed) {
          renderMappings();
        } else {
          updateOptionalFieldPicker();
          updateDropCustomFieldPicker();
        }
        if (result.warning && result.warning !== "Default field definitions were loaded.") setStatus(result.warning, "warn");
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
      // The standalone "JSON record layer" dropdown was removed as redundant -
      // Automatic mode auto-detects the layer and Custom mode takes a typed
      // record path. We still track the detected paths for draft persistence
      // and auto-resolution, but no longer render a picker for them.
      jsonRecordPaths = Array.isArray(paths) ? paths : [];
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
      updateSourcePlaceholders(sourceType);
      const isApi = sourceType === "api_get_json";
      const isPythonConnector = sourceType === "python_editor";
      const isExcel = sourceType === "excel";
      const isJson = sourceType === "json";
      const isCsv = sourceType === "csv";
      const isXml = sourceType === "xml";
      const hasRecordPath = ["json", "xml", "api_get_json", "python_editor"].includes(sourceType);
      const isFileSource = !isApi && !isPythonConnector;
      if (!isFileSource) el("sourceInputMode").value = "url";

      document.querySelectorAll(".api-field").forEach((field) => field.classList.toggle("hidden", !isApi));
      document.querySelectorAll(".api-function-field").forEach((field) => field.classList.toggle("hidden", !isApi));
      document.querySelectorAll(".csv-function-field").forEach((field) => field.classList.toggle("hidden", !isCsv));
      document.querySelectorAll(".excel-function-field").forEach((field) => field.classList.toggle("hidden", !isExcel));
      document.querySelectorAll(".json-function-field").forEach((field) => field.classList.toggle("hidden", !isJson));
      document.querySelectorAll(".xml-function-field").forEach((field) => field.classList.toggle("hidden", !isXml));
      document.querySelectorAll(".python-connector-field").forEach((field) => field.classList.toggle("hidden", !isPythonConnector));
      document.querySelectorAll(".excel-field").forEach((field) => field.classList.toggle("hidden", !isExcel));
      document.querySelectorAll(".file-field").forEach((field) => field.classList.toggle("hidden", !isFileSource));
      document.querySelectorAll(".file-upload-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || el("sourceInputMode").value !== "file"));
      document.querySelectorAll(".source-url-control").forEach((field) => field.classList.toggle("hidden", !isFileSource || el("sourceInputMode").value !== "url"));
      const sourceUrlEditBtn = el("sourceUrlEditBtn");
      if (sourceUrlEditBtn) {
        sourceUrlEditBtn.classList.toggle("hidden", !isFileSource || el("sourceInputMode").value !== "url" || !el("sourceUrl").hasAttribute("readonly"));
      }
      document.querySelectorAll(".record-field").forEach((field) => field.classList.toggle("hidden", !hasRecordPath));
      document.querySelectorAll(".json-record-path-field").forEach((field) => field.classList.toggle("hidden", sourceType !== "json"));

      document.querySelector("main").classList.toggle("connector-active", isPythonConnector);

      updateFileAccept();
      el("sourceType").disabled = false;
      el("sourceInputMode").disabled = false;
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
      const componentsPanel = el("templateComponentsPanel");
      const optionalPanel = el("optionalFieldsPanel");
      const previewTabs = el("mappingPreviewTabs");
      const hasMappingContent = Boolean(sourceParsed || sourceFields.length || activeTemplateId);
      componentsPanel?.classList.toggle("hidden", !hasMappingContent);
      optionalPanel?.classList.toggle("hidden", !hasMappingContent);
      previewTabs?.classList.toggle("hidden", !hasMappingContent);
      const grid = el("mappingGrid");
      grid.innerHTML = `
        <div class="mapping-head">Brand Field</div>
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
          <div>${target.required ? '<span class="required">*</span> ' : ''}${escapeHtml(target.label)}</div>
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
          applyMappingSelection(key, nextValue, select);
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
        if (!primaryMappingKeys.has(previousOwner[0])) optionalMappingKeys.delete(previousOwner[0]);
        setStatus(`Moved ${nextValue} from ${previousTarget ? previousTarget.label : previousOwner[0]} to ${currentTarget ? currentTarget.label : key}.`, "warn");
      }
      mappingSelections[key] = nextValue;
      autoMappedKeys.delete(key);
      if (!nextValue && !primaryMappingKeys.has(key)) {
        optionalMappingKeys.delete(key);
        delete mappingSelections[key];
      }
      renderMappings();
    }
function updateOptionalFieldPicker() {
      const picker = el("optionalFieldSelect");
      // Before a source is parsed, the main mapping grid itself isn't
      // rendered yet (renderMappings() is gated on sourceParsed), so this
      // picker is the only place to see any fields at all - show every
      // field, required main/primary ones (name, address, city, state,
      // ZIP) included, rather than just the narrow "not-yet-added optional
      // field" subset that applies once a source is parsed and those
      // required fields are already on the grid.
      const available = !sourceParsed
        ? mappingTargets
        : mappingTargets.filter((target) => !target.required && ((primaryMappingKeys.has(target.key) && hiddenMappingKeys.has(target.key)) || (!primaryMappingKeys.has(target.key) && !optionalMappingKeys.has(target.key))));
      picker.innerHTML = '<option value="">Choose a field</option>' + available
        .map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)}</option>`)
        .join("");
      el("addOptionalFieldBtn").disabled = available.length === 0;
    }
function getVisibleTargets() {
      const targets = mappingTargets.filter((target) => primaryMappingKeys.has(target.key) && !hiddenMappingKeys.has(target.key));
      optionalMappingKeys.forEach((key) => {
        const found = mappingTargets.find((target) => target.key === key);
        if (found && !targets.some((target) => target.key === key)) targets.push(found);
      });
      const unique = [];
      const seen = new Set();
      targets.forEach((target) => {
        if (!target?.key || seen.has(target.key)) return;
        seen.add(target.key);
        unique.push(target);
      });
      const optionalOrder = new Map([...optionalMappingKeys].map((key, index) => [key, index]));
      return unique
        .map((target, index) => ({ target, index }))
        .sort((a, b) => {
          const requiredOrder = Number(Boolean(b.target.required)) - Number(Boolean(a.target.required));
          if (requiredOrder) return requiredOrder;
          const aAddedOptional = optionalOrder.has(a.target.key) && !primaryMappingKeys.has(a.target.key);
          const bAddedOptional = optionalOrder.has(b.target.key) && !primaryMappingKeys.has(b.target.key);
          if (aAddedOptional !== bAddedOptional) return aAddedOptional ? 1 : -1;
          if (aAddedOptional && bAddedOptional) return optionalOrder.get(a.target.key) - optionalOrder.get(b.target.key);
          const fieldOrder = (fieldOrderIndex.get(a.target.key) ?? 999) - (fieldOrderIndex.get(b.target.key) ?? 999);
          return fieldOrder || a.index - b.index;
        })
        .map(({ target }) => target);
    }
function autoAddDetectedOptionalFields() {
      if (!sourceParsed || !sourceFields.length) return;
      const usedFields = new Set(Object.values(mappingSelections).filter(Boolean));
      mappingTargets
        .filter((target) => !target.required && !primaryMappingKeys.has(target.key) && !optionalMappingKeys.has(target.key))
        .forEach((target) => {
          const selected = suggestField(target, usedFields);
          if (!selected) return;
          mappingSelections[target.key] = selected;
          optionalMappingKeys.add(target.key);
          autoMappedKeys.add(target.key);
          usedFields.add(selected);
        });
    }
function targetOptionsForSourceField(sourceField) {
      const currentTargetKey = Object.entries(mappingSelections).find(([, value]) => value === sourceField)?.[0] || "";
      const visibleKeys = new Set(getVisibleTargets().map((target) => target.key));
      const targets = mappingTargets
        .filter((target) => target.required || visibleKeys.has(target.key) || !hiddenMappingKeys.has(target.key))
        .map((target, index) => ({ target, index }))
        .sort((a, b) => {
          const requiredOrder = Number(Boolean(b.target.required)) - Number(Boolean(a.target.required));
          if (requiredOrder) return requiredOrder;
          const fieldOrder = (fieldOrderIndex.get(a.target.key) ?? 999) - (fieldOrderIndex.get(b.target.key) ?? 999);
          return fieldOrder || a.index - b.index;
        })
        .map(({ target }) => target);
      return ['<option value="">Map to field...</option>']
        .concat(targets.map((target) => {
          const selected = target.key === currentTargetKey ? " selected" : "";
          const status = mappingSelections[target.key] ? " \u2713" : "";
          return `<option value="${escapeHtml(target.key)}"${selected}>${target.required ? "* " : ""}${escapeHtml(target.label)}${escapeHtml(status)}</option>`;
        }))
        .join("");
    }
function handleSourceFieldTargetSelection(sourceField, targetKey, selectElement) {
      if (!targetKey) return;
      hiddenMappingKeys.delete(targetKey);
      if (!primaryMappingKeys.has(targetKey)) optionalMappingKeys.add(targetKey);
      applyMappingSelection(targetKey, sourceField);
    }
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
function updateDropCustomFieldPicker() {
      const picker = el("dropCustomFieldSelect");
      if (!picker) return;
      const businessId = customFieldBusinessId("drop");
      const removable = mappingTargets.filter((target) => target.is_custom && (!businessId || target.business_id === businessId));
      picker.innerHTML = '<option value="">Choose a custom field</option>' + removable
        .map((target) => `<option value="${escapeHtml(target.key)}">${escapeHtml(target.label)} (${escapeHtml(target.key)})</option>`)
        .join("");
    }
function customFieldBusinessId(mode = "add") {
      const pickerId = mode === "drop" ? "dropCustomFieldBusinessSelect" : "customFieldBusinessSelect";
      const pickerVal = el(pickerId)?.value;
      const brandVal = selectedBrand?.business_id;
      const topSelectVal = el("brandSelect")?.value;
      return pickerVal || brandVal || (topSelectVal && topSelectVal !== "__create_new__" ? topSelectVal : "") || "";
    }
function syncCustomFieldBusinessPickers() {
      const brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      const options = '<option value="">Select brand</option>' + brands
        .map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(formatBrandName(brand.name))}</option>`).join("");
      const activeBusinessId = selectedBrand?.business_id || (el("brandSelect")?.value !== "__create_new__" ? el("brandSelect")?.value : "") || "";
      ["customFieldBusinessSelect", "dropCustomFieldBusinessSelect"].forEach((id) => {
        const picker = el(id);
        if (!picker) return;
        picker.innerHTML = options;
        picker.value = activeBusinessId || picker.value || "";
      });
      updateDropCustomFieldPicker();
    }
async function dropCustomField() {
      const fieldKey = el("dropCustomFieldSelect").value;
      if (!fieldKey) {
        setDropCustomFieldFeedback("Choose a custom field to remove.", "warn");
        return;
      }
      const businessId = customFieldBusinessId("drop");
      if (!businessId) {
        setDropCustomFieldFeedback("Select a brand before removing a custom field.", "warn");
        return;
      }
      const password = el("dropCustomFieldPassword").value.trim();
      if (!password) {
        setDropCustomFieldFeedback("Admin password required (use '54321').", "warn");
        return;
      }
      setDropCustomFieldFeedback("Removing custom field...", "");
      try {
        const response = await fetch("/api/custom-field/delete", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            password,
            business_id: businessId,
            field_key: fieldKey
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not remove custom field.");
        mappingTargets = mappingTargets.filter((t) => !(t.key === fieldKey && (!businessId || t.business_id === businessId)));
        optionalMappingKeys.delete(fieldKey);
        delete mappingSelections[fieldKey];
        delete customAliases[fieldKey];
        updateOptionalFieldPicker();
        updateDropCustomFieldPicker();
        renderMappings();
        updateOutput();
        setDropCustomFieldFeedback("Custom field removed.", "ok");
        el("dropCustomFieldPassword").value = "";
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
async function loadBrands(search = "") {
      try {
        const response = await fetch(`/api/brands?search=${encodeURIComponent(search)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load brands.");
        const brands = result.brands || [];
        el("brandSelect").innerHTML = '<option value="">Select an existing brand</option><option class="create-new-option" value="__create_new__">+ Create New Brand</option>' + brands.map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(formatBrandName(brand.name))}</option>`).join("");
        el("brandSelect").dataset.brands = JSON.stringify(brands);
        if (selectedBrand) el("brandSelect").value = selectedBrand.business_id;
        el("editExistingBrandLink")?.classList.toggle("hidden", !selectedBrand);
        syncCustomFieldBusinessPickers();
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not load brands."), "error");
      }
    }
async function createNewBrand(brandNameOverride = "", extra = {}) {
      const name = (brandNameOverride || el("newBrandName").value).trim();
      if (!name) { setStatus("Brand name is required.", "warn"); return null; }
      const button = el("createBrandBtn");
      const previousButton = setButtonBusy(button, "Saving Brand");
      try {
        const response = await fetch("/api/brands", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
          name, slug: el("newBrandSlug").value.trim(), description: el("newBrandDescription").value.trim(), logo_url: el("newBrandLogo").value.trim(), website_url: el("newBrandWebsite").value.trim(), status: el("newBrandStatus").value, meta_title: el("newBrandMetaTitle").value.trim(), meta_description: el("newBrandMetaDescription").value.trim(), country_of_origin: el("newBrandOrigin").value.trim(), ...extra
        }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not create brand.");
        selectedBrand = result.brand;
        el("brandSelect").value = selectedBrand.business_id;
        el("editExistingBrandLink")?.classList.remove("hidden");
        await loadBrands(selectedBrand.name);
        el("brandSelect").value = selectedBrand.business_id;
        el("newBrandFields").classList.add("hidden");
        el("newBrandFields").classList.remove("is-open");
        el("newBrandFields").classList.remove("editing-brand");
        presetCreateMode = false;
        applyBusinessSourceType(selectedBrand);
        await refreshTemplatesForBusiness();
        setStatus(`Brand ${selectedBrand.name} is ready for mapping.`, "ok");
        updateOutput();
        return selectedBrand;
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not create brand."), "error");
        return null;
      } finally {
        clearButtonBusy(button, previousButton);
      }
    }
function brandPayloadFromFields(extra = {}) {
      return {
        ...extra,
        name: el("newBrandName").value.trim(),
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
        brandEditMode = false;
        presetCreateMode = false;
        el("newBrandFields").classList.add("hidden");
        el("newBrandFields").classList.remove("is-open");
        el("newBrandFields").classList.remove("editing-brand");
        el("createBrandBtn").textContent = "Save Brand";
        updatePresetBrandPanel(activeCsvPresetConfig?.brand || selectedBrand, true);
        updateOutput();
        setStatus(`Brand ${selectedBrand.name} updated.`, "ok");
        return selectedBrand;
      } catch (error) {
        setStatus(productSafeError(error.message, "Could not update business."), "error");
        return null;
      } finally {
        clearButtonBusy(button, previousButton);
        clearButtonBusy(presetButton, previousPresetButton);
      }
    }
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
        presetCreateMode = true;
        brandEditMode = false;
        fillBrandFields({}, activeCsvPresetConfig.brand);
        el("newBrandFields").classList.remove("hidden");
        el("newBrandFields").classList.add("is-open");
        el("newBrandFields").classList.remove("editing-brand");
        el("brandFormHeading").textContent = `Create ${activeCsvPresetConfig.brand.name}`;
        el("createBrandBtn").textContent = "Save Brand";
        el("createBrandBtn").classList.remove("hidden");
        setStatus(`Review ${activeCsvPresetConfig.brand.name} details, then save the brand.`, "warn");
        return null;
    } finally {
      clearButtonBusy(button, previousButton);
    }
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
      const canSave = (sourceParsed || templateEditMode) && (coverage >= 50 || (templateEditMode && mappedSourceFields.size > 0));
      el("saveBtn").disabled = !canSave;
      el("saveBtn").textContent = templateEditMode && !sourceRows.length ? "Save Template" : "Save Template and Listing Data";
      el("saveActionWrap").dataset.tooltip = canSave
        ? (templateEditMode ? "Save the updated template mapping." : "Ready to save.")
        : "Map at least 50% before saving.";
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
      const sourceItems = sourceFields.map((field) => {
        const mappedTarget = Object.entries(mappingSelections).find(([, source]) => source === field);
        const targetDefinition = mappedTarget && mappingTargets.find((item) => item.key === mappedTarget[0]);
        return `
          <div class="entity-field source-row-item">
            <div class="entity-field-name">${escapeHtml(field)}</div>
            <div class="entity-field-source ${mappedSourceFields.has(field) ? "mapped" : "unmapped"}">${targetDefinition ? `&#10003; ${escapeHtml(targetDefinition.label)}` : "Unmapped"}</div>
            <select class="source-map-select" data-source-field="${escapeHtml(field)}" aria-label="Map ${escapeHtml(field)}">${targetOptionsForSourceField(field)}</select>
          </div>
        `;
      }).join("");
      const entityItems = Object.entries(groupedTargets).map(([table, fields]) => `
        <div class="entity-box">
          <div class="entity-title">${escapeHtml(entityNames[table] || table)}</div>
          <div class="entity-subtitle">Fields received from the source</div>
          <div class="entity-fields">${fields.map((item) => {
            const source = mappingSelections[item.key] || "";
            return `
              <div class="entity-field">
                <div class="entity-field-name">${item.required ? '<span class="required">*</span> ' : ''}${escapeHtml(item.label)}</div>
                <div class="entity-field-source ${source ? "mapped" : "unmapped"}">${source ? `&#8592; ${escapeHtml(source)}` : "Unmapped"}</div>
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
      target.querySelectorAll(".source-map-select").forEach((select) => {
        select.addEventListener("change", () => {
          handleSourceFieldTargetSelection(select.dataset.sourceField, select.value, select);
        });
      });
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
          ? `<span class="source-column-standard">${targetDefinition.required ? '<span class="required">*</span> ' : ''}${escapeHtml(targetDefinition.label)}</span><span class="source-column-name">[${escapeHtml(column)}]</span>`
          : `<span class="source-column-name">${escapeHtml(column)}</span><select class="source-preview-map-select" data-source-field="${escapeHtml(column)}" aria-label="Map ${escapeHtml(column)}">${targetOptionsForSourceField(column)}</select>`;
      });
      const body = rows.map((row) => {
        const flat = flattenObject(row);
        return `<tr>${columns.map((col) => `<td>${escapeHtml(col === "__brand" ? formatBrandName(selectedBrand?.name || "") : flat[col] ?? "")}</td>`).join("")}</tr>`;
      }).join("");
      target.innerHTML = `
        <table>
          <thead><tr>${columnHeaders.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      `;
      target.querySelectorAll(".source-preview-map-select").forEach((select) => {
        select.addEventListener("change", () => {
          handleSourceFieldTargetSelection(select.dataset.sourceField, select.value, select);
          renderTable(targetId, rows);
        });
      });
    }
function mapperHasField(key) {
      return Boolean(mappingSelections[key]);
    }
function mapperHasSource(field) {
      return Object.values(mappingSelections).includes(field);
    }
function getMappedSourceLabel(key) {
      const sourceField = mappingSelections[key];
      return sourceField ? `&#10003; ${escapeHtml(sourceField)}` : "Unmapped";
    }
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
async function parseSource() {
      const parseBtn = el("parseBtn");
      const runBtn = el("runPythonConnectorBtn");
      const previousParseBtn = setButtonBusy(parseBtn, "Parsing");
      const previousRunBtn = setButtonBusy(runBtn, "Running & Parsing");
      setStatus("Reading your source...", "");
      try {
        const file = el("fileInput").files[0];
        let sourceType = el("sourceType").value;
        const recordExtractionMode = document.querySelector('input[name="recordExtractionMode"]:checked')?.value || "auto";
        const recordPathVal = recordExtractionMode === "custom" ? el("recordPath").value.trim() : "";
        const payload = {
          source_type: sourceType,
          record_path: recordPathVal,
          fields_only: true  // Fast initial preview: headers/keys only, no full row parsing
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
        lastSourcePreviewPayload = { ...payload };
        sourceRows = result.rows || [];
        sourceRecordCount = Number(result.record_count || sourceRows.length);
        sourceFields = [...new Set((result.fields || []).filter((field) => field !== null && field !== undefined && String(field).trim()))];
        jsonRecordPaths = result.record_paths || [];
        sourceParsed = true;
        templateEditMode = false;
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
        else if (excelFunctionMode === "demo_restaurant") setDemoRestaurantExcelMappings();
        else if (jsonFunctionMode === "dominos") setDominosMappings();
        else if (apiFunctionMode === "little_caesars") setLittleCaesarsApiMappings();
        else if (document.querySelector("input[name='pythonFunction']:checked")?.value === "la_city") setLaCityDemoMappings();
        autoAddDetectedOptionalFields();
        sessionStorage.removeItem(draftStorageKey);
        if (resolvedRecordPath && recordExtractionMode === "custom" && !el("recordPath").value.trim()) el("recordPath").value = resolvedRecordPath;
        if (sourceType === "excel" && resolvedRecordPath) el("sheetName").value = resolvedRecordPath;
        renderMappings();
        if (csvFunctionMode === "pizza_hut") setPizzaHutLocked(true);
        if (jsonFunctionMode === "dominos") setDominosLocked(true);
        if (document.querySelector("input[name='pythonFunction']:checked")?.value === "la_city") setLaCityDemoLocked(true);
        const recordCount = result.record_count;
        if (recordCount !== undefined) {
          setStatus(`Detected Records: ${recordCount}.`, "ok");
        }
        renderTable("sourcePreview", sourceRows.slice(0, 10).map((row) => flattenObject(row)));
      } catch (error) {
        sourceRows = [];
        sourceFields = [];
        sourceParsed = false;
        const timedOut = /timed out|timeout|time out|aborterror/i.test(String(error.message || ""));
        setStatus(
          timedOut
            ? "The source is taking longer than expected. Check the URL or reload it to try again."
            : productSafeError(error.message, "Preview failed."),
          "error",
          { retry: timedOut }
        );
      } finally {
        clearButtonBusy(parseBtn, previousParseBtn);
        clearButtonBusy(runBtn, previousRunBtn);
      }
    }
async function loadFullSourceForSave() {
      if (!lastSourcePreviewPayload || sourceRows.length >= sourceRecordCount) return;
      setStatus(`Loading all ${sourceRecordCount} source records for saving...`, "");
      const response = await fetch("/api/preview", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...lastSourcePreviewPayload, fields_only: false })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load the full source for saving.");
      sourceRows = result.rows || [];
      sourceRecordCount = Number(result.record_count || sourceRows.length);
      sourceFields = Array.from(new Set([
        ...sourceFields,
        ...(result.fields || []).filter((field) => field !== null && field !== undefined && String(field).trim())
      ]));
      renderTable("sourcePreview", sourceRows.slice(0, 10).map((row) => flattenObject(row)));
      setStatus(`Loaded ${sourceRows.length} records. Ready to save all source data.`, "ok");
    }
async function loadExcelSheets() {
      const file = el("fileInput").files[0];
      const isUrlMode = el("sourceInputMode").value === "url";
      el("sheetName").innerHTML = `<option value="">${isUrlMode ? "Enter Excel URL to load sheets" : "Upload Excel to load sheets"}</option>`;
      el("sheetName").disabled = true;
      if (el("sourceType").value !== "excel") return;
      if (!isUrlMode && !isExcelFile(file)) return;
      if (isUrlMode && !el("sourceUrl").value.trim()) return;
      try {
        let payload;
        if (isUrlMode) {
          el("sheetName").innerHTML = '<option value="">Loading sheets from URL...</option>';
          const sourceUrl = el("sourceUrl").value.trim();
          const sourceResponse = await fetch("/api/source-url", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ url: sourceUrl })
          });
          const sourceResult = await sourceResponse.json();
          if (!sourceResponse.ok) throw new Error(sourceResult.error || "Could not fetch the public Excel URL.");
          payload = {
            file_name: remoteFileNameForSource(sourceResult, sourceUrl, "remote_workbook"),
            content_base64: sourceResult.content_base64
          };
        } else {
          payload = {
            file_name: file.name,
            content_base64: await fileToBase64(file)
          };
        }
        const response = await fetch("/api/sheets", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load sheets.");
        const sheets = result.sheets || [];
        el("sheetName").innerHTML = sheets.length
          ? sheets.map((sheet) => `<option value="${escapeHtml(sheet)}">${escapeHtml(sheet)}</option>`).join("")
          : '<option value="">No sheets found</option>';
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
async function clearSampleDataset() {
      const clearLink = el("clearSampleDatasetLink");
      const previousClear = clearLink ? setButtonBusy(clearLink, "Clearing") : "";
      const status = el("reportStatus");
      status.className = "report-status loading";
      status.innerHTML = '<span class="spinner"></span> Clearing sample dataset...';
      status.classList.remove("hidden");
      try {
        const response = await fetch("/api/sample/clear", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({}),
          signal: activeAbortController?.signal
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not clear sample dataset.");
        await loadBrands();
        await loadTemplateFilters();
        reportLoaded = false;
        await loadReporting();
        const message = "Sample dataset cleared. Reporting now displays active real data only.";
        status.className = "report-status";
        status.textContent = message;
        status.classList.remove("hidden");
        setStatus(message, "ok");
        updateSampleDatasetControls({ loaded: false, locations: 0, businesses: 0 });
      } catch (error) {
        status.className = "report-status";
        const message = error.name === "AbortError" ? "Cancelled. No changes." : productSafeError(error.message, "Could not clear sample dataset.");
        status.textContent = message;
        status.classList.remove("hidden");
        setStatus(message, error.name === "AbortError" ? "warn" : "error");
      } finally {
        if (clearLink) clearButtonBusy(clearLink, previousClear);
      }
    }
function updateSampleDatasetControls(result = {}) {
      const button = el("loadSampleDatasetBtn");
      const clearLink = el("clearSampleDatasetLink");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!button) return;
      const loaded = Boolean(result.loaded || result.already_loaded || result.locations);
      button.dataset.sampleLoaded = loaded ? "true" : "false";
      button.disabled = loaded;
      button.classList.toggle("ready", loaded);
      button.title = loaded ? "Sample data already in place." : "";
      button.textContent = loaded ? "Sample Dataset Loaded" : "Load Sample Dataset";
      if (clearLink) clearLink.classList.toggle("hidden", !loaded);
      if (reloadLink) reloadLink.classList.toggle("hidden", !loaded);
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
      const saveBtn = el("saveBtn");
      const previousSaveBtn = setButtonBusy(saveBtn, "Saving");
      try {
        let mapper = getMapper();
        if (!mapper.brand) {
          setStatus("Please select or enter a Brand name before saving.", "warn");
          return;
        }
        if (!mapper.business_id) {
          setStatus("Creating brand for mapping...", "");
          const created = await createNewBrand(mapper.brand);
          if (!created || !created.business_id) {
            setStatus("Could not resolve brand ID. Please save the brand first.", "warn");
            return;
          }
          mapper = getMapper();
        }

        // A template loaded from the library keeps its own workflow_templates
        // row (activeTemplateId) - update that definition with any field-
        // mapping edits up front, regardless of whether a source file has
        // been (re)parsed yet below. Previously this button, when a template
        // was loaded, ONLY did this and returned - so editing a loaded
        // template's mapping and clicking "Save Template and Listing Data"
        // never actually reprocessed the parsed rows into listings, despite
        // the button's own label promising both.
        if (activeTemplateId) {
          try {
            await saveEditedTemplate();
          } catch (error) {
            setStatus(productSafeError(error.message, "Could not update template."), "error");
            return;
          }
        }

        if (!activeTemplateId) {
          await loadFullSourceForSave();
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
          const startTime = Date.now();
          for (let index = 0; index < batches.length; index += 1) {
            const batch = batches[index];
            const totalToProcess = sourceRows.length;
            const progress = Math.min(90, 20 + Math.round(processedRows / Math.max(totalToProcess, 1) * 65));

            // Estimate remaining time based on pace so far
            let etaSeconds = "...";
            if (processedRows > 0 && index > 0) {
              const elapsedMs = Date.now() - startTime;
              const msPerRow = elapsedMs / processedRows;
              const remainingRows = totalToProcess - processedRows;
              etaSeconds = Math.max(0, Math.round(remainingRows * msPerRow / 1000));
            }

            const progressDetail = processedRows
              ? `${processedRows} of ${totalToProcess} records processed`
              : `Starting batch ${index + 1} of ${batches.length}`;
            const etaDetail = etaSeconds !== "..." ? `, about ${etaSeconds}s remaining` : "";
            setProgress(progress, `${progressDetail}${etaDetail}`);
            const response = await fetch("/api/save", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                mapper,
                rows: batch.rows,
                source_fields: sourceFields,
                batch_event_id: batchEventId,
                row_offset: batch.rowOffset,
                // A loaded template's row is already kept in sync above -
                // never mint a second, duplicate template row for it here.
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
          el("reviewEventId").value = lastSaveEventId;
          // A save just created new error listings - force a live re-count so
          // the tab badge reflects them (and the SQLite cache is refreshed).
          await refreshReviewCount(true);
          if (typeof loadErrorBrandBreakdown === "function") loadErrorBrandBreakdown();
          hideProgress();
          const prefix = activeTemplateId ? "Template updated. " : "";
          showSaveCompletion(`${prefix}${processedRows} records processed. ${errorListings} need review.`);
        } catch (error) {
          hideProgress();
          setStatus(productSafeError(error.message, "Could not save template."), "error");
        }
      } finally {
        clearButtonBusy(saveBtn, previousSaveBtn);
      }
    }

function showSaveCompletion(message) {
      let dialog = document.getElementById("saveCompletionDialog");
      if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.id = "saveCompletionDialog";
        dialog.style.cssText = "border:1px solid var(--line);border-radius:10px;padding:24px;max-width:420px;color:var(--ink);box-shadow:0 24px 70px rgba(15,23,42,.28);";
        dialog.innerHTML = `<p id="saveCompletionMessage" style="margin:0 0 20px;font-size:16px;font-weight:650;line-height:1.45"></p><div style="display:flex;justify-content:flex-end"><button id="saveCompletionOk" type="button">OK</button></div>`;
        document.body.appendChild(dialog);
        dialog.querySelector("#saveCompletionOk").addEventListener("click", () => dialog.close());
      }
      dialog.querySelector("#saveCompletionMessage").textContent = message;
      if (typeof dialog.showModal === "function") dialog.showModal();
      else window.alert(message);
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
      const button = el("confirmClearBtn");
      const previousButton = setButtonBusy(button, "Clearing");
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
      } finally {
        clearButtonBusy(button, previousButton);
      }
    }
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

function resetMapping() {
      activeTemplateId = "";
      templateEditMode = false;
      mappingSelections = {};
      autoMappedKeys = new Set();
      optionalMappingKeys = new Set();
      hiddenMappingKeys = new Set();
      customAliases = {};
      sourceRows = [];
      sourceFields = [];
      sourceRecordCount = 0;
      sourceParsed = false;
      lastSourcePreviewPayload = null;
      resolvedRecordPath = "";
      jsonRecordPaths = [];
      populateJsonRecordPaths([]);
      renderTable("sourcePreview", []);
      el("entityPreview").innerHTML = "";
      saveDraft();
      renderMappings();
      setStatus("Choose a source and parse it to start mapping in left pane.", "ok");
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
      const businessId = customFieldBusinessId("add");
      if (!businessId) {
        setCustomFieldFeedback("Select a brand before adding a custom field.", "warn");
        return;
      }
      const password = el("aliasPassword").value.trim();
      if (!password) {
        setCustomFieldFeedback("Admin password required (use '54321').", "warn");
        return;
      }
      const button = el("addCustomFieldBtn");
      const previousButton = setButtonBusy(button, "Adding Field");
      try {
        const response = await fetch("/api/custom-field", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            label,
            slug: el("customFieldSlug").value.trim(),
            type: el("customFieldType").value,
            password: password,
            business_id: businessId
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not save custom field.");
        await loadFieldRegistry();
        if (result.field?.key) {
          optionalMappingKeys.add(result.field.key);
          hiddenMappingKeys.delete(result.field.key);
        }
        el("customFieldLabel").value = "";
        el("customFieldSlug").value = "";
        el("aliasPassword").value = "";
        renderMappings();
        updateOptionalFieldPicker();
        updateDropCustomFieldPicker();
        updateOutput();
        setCustomFieldFeedback(`Custom field ${result.field?.label || label} saved and added to mapping.`, "ok");
      } catch (error) {
        setCustomFieldFeedback(productSafeError(error.message, "Could not save custom field."), "error");
      } finally {
        clearButtonBusy(button, previousButton);
      }
    }
async function toggleShowExistingBrands() {
      const box = el("existingBrandsDialog");
      if (box.style.display === "block") {
        box.style.display = "none";
        return;
      }
      box.style.display = "block";
      box.innerHTML = `<em>Fetching active brands...</em>`;
      try {
        const response = await fetch("/api/brands?search=");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not fetch active brands.");
        const brands = result.brands || [];
        if (!brands.length) {
          box.innerHTML = `<div style="color: var(--muted);">No existing brands found.</div>`;
          return;
        }
        const brandsWithDisplayIds = await Promise.all(brands.map(async (brand) => ({
          ...brand,
          display_business_id: brand.display_business_id || await fallbackDisplayBusinessId(brand)
        })));
        const optionsHtml = '<option value="">Select an active brand</option>' + brandsWithDisplayIds.map(b => `<option value="${escapeHtml(b.business_id)}">${escapeHtml(businessOptionLabelShort(b))}</option>`).join('');
        const duplicateGroups = duplicateBusinessGroups(brandsWithDisplayIds);
        const mergeHtml = duplicateGroups.length ? `
          <div style="border-top: 1px solid var(--line); margin-top: 10px; padding-top: 10px;">
            <strong style="display: block; margin-bottom: 6px; color: var(--navy);">Similar Brands</strong>
            ${duplicateGroups.map((group, index) => {
              const newestCreatedAt = Math.max(...group.map(businessCreatedTime));
              return `
              <div data-merge-group="${index}" style="border: 1px solid #e5cfaa; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 8px; margin-top: 8px; background: #fff9ed;">
                <div style="font-weight: 700; margin-bottom: 6px;">${escapeHtml(group[0].name || "Similar brand")}</div>
                <label style="font-size: 12px;">Keep</label>
                <select data-merge-target="${index}" style="width: 100%; margin: 4px 0 8px; padding: 6px 8px; border: 1px solid var(--line); border-radius: 4px;">
                  ${group.map((brand) => `<option value="${escapeHtml(brand.business_id)}">${escapeHtml(businessOptionLabel(brand, newestCreatedAt))}</option>`).join("")}
                </select>
                <button type="button" class="secondary" data-merge-action="${index}">Merge Others Into Keep</button>
              </div>
            `}).join("")}
          </div>
        ` : "";
        box.innerHTML = `
          <label style="display: block; font-weight: 700; margin-bottom: 4px; color: var(--navy);" for="activeBusinessesDropdown">
            Active Brands (${brands.length})
          </label>
          <select id="activeBusinessesDropdown" style="width: 100%; padding: 6px 8px; border-radius: 4px; border: 1px solid var(--line); background: #ffffff;">
            ${optionsHtml}
          </select>
          ${mergeHtml}
        `;
        el("activeBusinessesDropdown").addEventListener("change", (event) => {
          if (!event.target.value) return;
          el("brandSelect").value = event.target.value;
          el("brandSelect").dispatchEvent(new Event("change"));
          box.style.display = "none";
        });
        box.querySelectorAll("[data-merge-action]").forEach((button) => {
          button.addEventListener("click", async () => {
            const index = Number(button.dataset.mergeAction);
            const group = duplicateGroups[index] || [];
            const targetId = box.querySelector(`[data-merge-target="${index}"]`)?.value || "";
            const sourceIds = group.map((brand) => brand.business_id).filter((id) => id && id !== targetId);
            if (!targetId || !sourceIds.length) return;
            const previousButton = setButtonBusy(button, "Merging");
            try {
              const result = await mergeDuplicateBusinesses(targetId, sourceIds);
              await loadBrands("");
              setStatus(`Merged ${result.merged_count} business record${result.merged_count === 1 ? "" : "s"}.`, "ok");
              box.style.display = "none";
            } catch (err) {
              clearButtonBusy(button, previousButton);
              setStatus(productSafeError(err.message, "Could not merge businesses."), "error");
            }
          });
        });
      } catch (err) {
        box.innerHTML = `<div style="color: var(--error);">${escapeHtml(err.message)}</div>`;
      }
    }
