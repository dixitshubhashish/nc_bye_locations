// Mappings tab: source onboarding, brand/connector setup, mapping builder,
// draft save/restore, and save-to-warehouse logic.

let mappingTargets = [
      { key: "name", table: "listings", field: "name", label: "Brand Name", required: true, hints: ["name", "restaurantname", "storename", "displayname"] },
      { key: "address", table: "listings", field: "address", label: "Street Address", required: true, hints: ["address", "addressdescription", "line1", "street"] },
      { key: "city", table: "listings", field: "city_name", label: "City", required: true, hints: ["city", "town"] },
      { key: "state", table: "listings", field: "state_code", label: "State", required: true, hints: ["state", "region", "province", "state_code"] },
      { key: "postal_code", table: "listings", field: "zip_code", label: "ZIP Code", required: true, hints: ["zip", "zipcode", "zip_code", "postalcode", "postal_code"] },
      { key: "country", table: "listings", field: "country", label: "Country", required: false, hints: ["country", "countrycode"] },
      { key: "location_id", table: "listings", field: "location_key", label: "Store ID", required: false, hints: ["locationid", "storeid", "store_id", "id", "number"] },
      { key: "town", table: "listings", field: "town", label: "Town", required: false, hints: ["town", "locality"] },
      { key: "province", table: "listings", field: "province", label: "Province", required: false, hints: ["province", "region"] },
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
      "name", "address", "city", "state", "postal_code", "country", "location_id", "town", "province",
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
// Immutable snapshot of {target_key: source_field} taken right after
// auto-mapping settles post-parse - unlike autoMappedKeys (which loses
// entries as soon as the user touches them), this is never mutated, so at
// save time it can be diffed against the final mapping to score each
// auto-suggestion as kept/switched/removed - the raw signal the field-
// mapping confidence system learns from.
let originalAutoMapping = {};
let learnedSuggestions = {};
let sourceParsed = false;
// True from a successful parse until the next successful save (or the
// workspace is reset) - drives the "you have unsaved changes" nav guard so
// navigating away right after a parse doesn't silently discard it.
let pendingUnsavedParse = false;
let mappingWorkspaceActivated = false;
let preParseRelocatedNodes = null;
let preParseStatusLocation = null;
// True while a template loaded from the Template Library is being edited
// without a freshly parsed source file. The mapping grid and Save must work
// off the template's stored source_fields (there are no live sourceRows),
// so this flag stands in for sourceParsed wherever the mapper only needs the
// column list, not actual row data.
let templateEditMode = false;
// Above this many source columns the Data Model gets a search box and its
// own scroll region - below it, a plain list is easier to scan than one
// wrapped in chrome.
const DATA_MODEL_SEARCH_THRESHOLD = 100;
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
let businessRequirementTouched = false;
function setPreParseBrandValidation(message = "") {
  const inPreParse = el("mapperView")?.classList.contains("pre-parse-active");
  const ids = inPreParse ? ["parserBusinessValidation"] : ["brandSelectValidation"];
  ["preParseBrandValidation", "parserBusinessValidation", "brandSelectValidation"].forEach((id) => {
    const node = el(id);
    if (!node) return;
    const shouldShow = ids.includes(id) && Boolean(message);
    node.textContent = shouldShow ? message : "";
    node.classList.toggle("hidden", !shouldShow);
  });
}
function hasSelectedBusiness() {
  const value = el("brandSelect")?.value || "";
  return Boolean(selectedBrand?.business_id || (value && value !== "__create_new__"));
}
function syncParserBusinessSelect() {
  const sourceSelect = el("brandSelect");
  const parserSelect = el("parserBusinessSelect");
  if (!sourceSelect || !parserSelect) return;
  parserSelect.innerHTML = sourceSelect.innerHTML;
  parserSelect.dataset.brands = sourceSelect.dataset.brands || "[]";
  parserSelect.value = sourceSelect.value || "";
  parserSelect.disabled = sourceSelect.disabled;
}
function setBusinessSelectValue(value, dispatch = true) {
  const brandSelect = el("brandSelect");
  const parserSelect = el("parserBusinessSelect");
  if (brandSelect) brandSelect.value = value;
  if (parserSelect) parserSelect.value = value;
  if (dispatch && brandSelect) brandSelect.dispatchEvent(new Event("change"));
}
function markBusinessRequirementTouched() {
  businessRequirementTouched = true;
  if (!hasSelectedBusiness()) {
    setPreParseBrandValidation("Select an existing brand or create a new one before parsing.");
  }
}
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
// Dice coefficient over character bigrams: 1.0 identical, 0.0 nothing in
// common. Chosen over exact-key matching because that only caught brands
// whose normalized names were byte-identical - "Dominos Pizza" vs "Domino's
// Pizza Inc" scored nothing and stayed unmerged, which is why duplicates
// kept surviving in the dropdown.
const BRAND_SIMILARITY_THRESHOLD = 0.75;

function nameBigrams(value = "") {
      const text = String(value || "");
      const grams = new Set();
      for (let i = 0; i < text.length - 1; i += 1) grams.add(text.slice(i, i + 2));
      return grams;
    }
function brandNameSimilarity(a = "", b = "") {
      const left = similarBusinessKey(a);
      const right = similarBusinessKey(b);
      if (!left || !right) return 0;
      if (left === right) return 1;
      const first = nameBigrams(left);
      const second = nameBigrams(right);
      if (!first.size || !second.size) return 0;
      let shared = 0;
      first.forEach((gram) => { if (second.has(gram)) shared += 1; });
      return (2 * shared) / (first.size + second.size);
    }
// Group brands whose names are >=75% similar. Single-link clustering: a
// brand joins the first group it is similar enough to, so a chain of near
// matches lands in one group rather than several overlapping pairs.
function duplicateBusinessGroups(brands = [], threshold = BRAND_SIMILARITY_THRESHOLD) {
      const groups = [];
      brands.forEach((brand) => {
        if (!similarBusinessKey(brand.name || "")) return;
        const match = groups.find((group) =>
          group.some((member) => brandNameSimilarity(member.name || "", brand.name || "") >= threshold));
        if (match) match.push(brand);
        else groups.push([brand]);
      });
      return groups.filter((group) => group.length > 1);
    }
// duplicateContentHashGroups() was removed here rather than wired up: its
// premise is impossible. It grouped listings by shared content_hash to spot
// the same physical store filed under two brands - but business_id IS one of
// CONTENT_HASH_FIELDS, so two brand records can never collide on a hash by
// construction (verified: identical listing under brand-A vs brand-B produces
// two different hashes). Cross-brand overlap needs a hash over the physical
// identity WITHOUT business_id, computed warehouse-side, and a product call on
// whether a shared street address is evidence of a duplicate brand or just a
// shared strip mall. Both are open - see O2 in docs/bug_tracker.md.
function businessCreatedTime(brand = {}) {
      const value = Date.parse(brand.created_at || "");
      return Number.isFinite(value) ? value : 0;
    }
function businessOptionLabel(brand = {}, newestCreatedAt = 0) {
      const newest = newestCreatedAt && businessCreatedTime(brand) === newestCreatedAt ? "Newest, " : "";
      return `${formatBrandName(brand.name || "Unnamed")} (${brand.display_business_id || "BID --------"}, ${formatNumber(brand.listing_count || 0)} listings, ${newest}created ${brand.created_at ? formatTimestamp(brand.created_at) : "unknown"})`;
    }
function businessOptionLabelShort(brand = {}) {
      return `${formatBrandName(brand.name || "Unnamed")} (${brand.display_business_id || "BID --------"})`;
    }
// Label for the merge picker specifically. Unlike the brand dropdown - where
// inline detail was clutter - this is a DECISION, so which record is newest
// vs oldest and how many listings each holds has to be visible, not hidden
// behind a hover the user may never trigger.
function businessMergeChoiceLabel(brand = {}, newestCreatedAt = 0, oldestCreatedAt = 0) {
      const created = businessCreatedTime(brand);
      let age = "";
      if (newestCreatedAt && oldestCreatedAt && newestCreatedAt !== oldestCreatedAt) {
        if (created === newestCreatedAt) age = " - Newest";
        else if (created === oldestCreatedAt) age = " - Oldest";
      }
      const listings = formatNumber(brand.listing_count || 0);
      const when = brand.created_at ? formatTimestamp(brand.created_at) : "unknown date";
      return `${formatBrandName(brand.name || "Unnamed")} (${brand.display_business_id || "BID --------"}) - ${listings} listings${age} - created ${when}`;
    }
// DAT-04: render the duplicate groups into the left rail, one at a time.
// Detail (business id, listing count, newest/oldest created_at) is hover
// text on each option rather than inline, per the explicit ask.
function renderDuplicateBrandRail(groups = []) {
      const panel = el("duplicateBrandPanel");
      const list = el("duplicateBrandList");
      if (!panel || !list) return;
      if (!groups.length) {
        panel.classList.add("hidden");
        list.innerHTML = "";
        return;
      }
      panel.classList.remove("hidden");
      // One row per candidate brand, radio-selected, every group submitted
      // together. Handling groups one at a time meant ten duplicates cost ten
      // round trips; the decision for each is independent, so they may as
      // well all be made before a single submit.
      list.innerHTML = groups.map((group, groupIndex) => {
        const times = group.map(businessCreatedTime).filter(Boolean);
        const newest = times.length ? Math.max(...times) : 0;
        const oldest = times.length ? Math.min(...times) : 0;
        // Default selection: most listings, then oldest - the record other
        // rows already point at.
        const ranked = [...group].sort((a, b) =>
          (Number(b.listing_count || 0) - Number(a.listing_count || 0))
          || (businessCreatedTime(a) - businessCreatedTime(b)));
        const keepId = ranked[0].business_id;
        // Always show all four facts - BID, listing count, Newest/Oldest and
        // the created date - so the choice can be made from the row itself
        // without opening anything. The recommended row (pre-selected) is the
        // one with the most listings; on a tie, the older record wins, since
        // that is the one other records already point at.
        const rows = ranked.map((brand, index) => {
          const created = businessCreatedTime(brand);
          const age = created === newest && newest !== oldest ? "Newest"
            : (created === oldest && newest !== oldest ? "Oldest" : "Same age");
          return `
            <label class="dup-brand-row">
              <input type="radio" name="dupKeep${groupIndex}" value="${escapeHtml(brand.business_id)}"${brand.business_id === keepId ? " checked" : ""}>
              <span class="dup-brand-meta">
                <span class="dup-brand-id">${escapeHtml(brand.display_business_id || "BID --------")}${index === 0 ? ' <em class="dup-brand-pick">recommended</em>' : ""}</span>
                <span class="dup-brand-facts">${formatNumber(brand.listing_count || 0)} listings &middot; <strong>${age}</strong> &middot; ${escapeHtml(brand.created_at ? formatTimestamp(brand.created_at) : "date unknown")}</span>
              </span>
            </label>`;
        }).join("");
        // Name shown once per group, not repeated on every row.
        return `
          <div class="dup-brand-group" data-dup-group="${groupIndex}">
            <div class="dup-brand-name">${escapeHtml(formatBrandName(group[0].name || "Similar brand"))} <span class="dup-brand-count">${group.length} copies</span></div>
            ${rows}
          </div>`;
      }).join("");
      list.insertAdjacentHTML("beforeend", `
        <button type="button" class="secondary" id="duplicateBrandMergeBtn">Combine selected</button>
        <div style="font-size: 11px; color: var(--muted); margin-top: 6px;">Pick the one to keep in each group. Everything from the others moves into it. Nothing is lost. We recommend the one with the most listings, or the older record when counts match.</div>`);
      el("duplicateBrandMergeBtn")?.addEventListener("click", async () => {
        const button = el("duplicateBrandMergeBtn");
        const status = el("duplicateBrandStatus");
        // Read every group's choice, then submit them together.
        const plans = groups.map((group, groupIndex) => {
          const targetId = list.querySelector(`input[name="dupKeep${groupIndex}"]:checked`)?.value || "";
          return { targetId, sourceIds: group.map((b) => b.business_id).filter((id) => id && id !== targetId) };
        }).filter((plan) => plan.targetId && plan.sourceIds.length);
        if (!plans.length) return;
        // Combining is irreversible from the UI, so it gets an explicit
        // confirmation naming what moves - counted in the warehouse, not
        // guessed from the dropdown's listing_count.
        const checking = setButtonBusy(button, "Checking");
        const summary = await describeMergeImpact(plans);
        clearButtonBusy(button, checking);
        const confirmed = await showAppConfirm(summary, "Combine these brands?");
        if (!confirmed) return;
        const previous = setButtonBusy(button, "Combining");
        if (status) { status.className = "action-feedback"; status.textContent = ""; }
        let merged = 0;
        const failures = [];
        let listingsMoved = 0;
        let reviewMoved = 0;
        for (const plan of plans) {
          try {
            const outcome = await mergeDuplicateBusinesses(plan.targetId, plan.sourceIds);
            merged += plan.sourceIds.length;
            // Weighting: what the merge actually consolidated. "Combined 2
            // brands" says nothing about impact.
            listingsMoved += Number(outcome?.listings_moved || 0);
            reviewMoved += Number(outcome?.review_rows_moved || 0);
          } catch (error) {
            // One bad group must not discard the ones that worked.
            failures.push(productSafeError(error.message, "one group could not be combined"));
          }
        }
        if (status) {
          status.className = failures.length ? "action-feedback error" : "action-feedback ok";
          status.textContent = failures.length
            ? `Combined ${merged}, but ${failures.length} group${failures.length === 1 ? "" : "s"} failed: ${failures[0]}`
            : `Combined ${merged} duplicate brand${merged === 1 ? "" : "s"}.${
                listingsMoved || reviewMoved
                  ? ` Moved ${formatNumber(listingsMoved)} listing${listingsMoved === 1 ? "" : "s"}${reviewMoved ? ` and ${formatNumber(reviewMoved)} review row${reviewMoved === 1 ? "" : "s"}` : ""}.`
                  : " The copies held no records, so nothing needed moving."
              }`;
        }
        clearButtonBusy(button, previous);
        await loadBrands();
      });
    }

// What the user is about to agree to, in their own terms. Counts come from
// the warehouse via the merge endpoint's preview mode; a table whose count
// could not be read is reported as unknown rather than as zero, so "nothing
// will move" is only ever said when it is actually true.
async function describeMergeImpact(plans) {
      const brandCount = plans.reduce((total, plan) => total + plan.sourceIds.length, 0);
      const lines = [
        `${brandCount} duplicate brand${brandCount === 1 ? "" : "s"} will be combined into ${plans.length} kept brand${plans.length === 1 ? "" : "s"}.`,
        ""
      ];
      let listings = 0;
      let templates = 0;
      let reviewRows = 0;
      let complete = true;
      for (const plan of plans) {
        try {
          const preview = await mergeDuplicateBusinesses(plan.targetId, plan.sourceIds, { preview: true });
          listings += Number(preview?.listings_moved || 0);
          templates += Number(preview?.templates_moved || 0);
          reviewRows += Number(preview?.review_rows_moved || 0);
          if (preview?.counts_complete === false) complete = false;
        } catch (error) {
          complete = false;
        }
      }
      if (!complete) {
        lines.push("Everything the duplicates hold - listings, saved templates and review rows - moves to the brand you kept.");
        lines.push("We could not count all of it up front, so no totals are shown here.");
      } else if (!listings && !templates && !reviewRows) {
        lines.push("The duplicates hold no records, so nothing needs to move. Only the extra brand entries go away.");
      } else {
        lines.push("Moving to the brand you kept:");
        lines.push(`\u2022 ${formatNumber(listings)} listing${listings === 1 ? "" : "s"}`);
        lines.push(`\u2022 ${formatNumber(templates)} saved template${templates === 1 ? "" : "s"}`);
        lines.push(`\u2022 ${formatNumber(reviewRows)} review row${reviewRows === 1 ? "" : "s"}`);
      }
      lines.push("");
      lines.push("Nothing is deleted, and the duplicate brand entries are retired. This cannot be undone from this app.");
      return lines.join("\n");
    }

async function mergeDuplicateBusinesses(targetId, sourceIds, options = {}) {
      const response = await fetch("/api/brands/merge", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_business_id: targetId, source_business_ids: sourceIds, preview: !!options.preview })
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
function autoGrowBrandTextarea(node) {
      if (!node) return;
      node.style.height = "38px";
      node.style.height = `${Math.min(Math.max(node.scrollHeight, 38), 140)}px`;
    }
function autoGrowBrandTextareas() {
      autoGrowBrandTextarea(el("newBrandDescription"));
      autoGrowBrandTextarea(el("newBrandMetaDescription"));
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
      autoGrowBrandTextareas();
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
function openPrefilledBrandCreateForm(brandConfig = {}) {
      selectedBrand = null;
      presetCreateMode = Boolean(activeCsvPresetConfig);
      brandEditMode = false;
      el("brandSelect").value = "__create_new__";
      syncParserBusinessSelect();
      fillBrandFields({}, brandConfig);
      el("newBrandFields").classList.remove("hidden");
      el("newBrandFields").classList.toggle("is-open", Boolean(el("mapperView")?.classList.contains("pre-parse-active")));
      el("newBrandFields").classList.remove("editing-brand");
      el("brandFormHeading").textContent = brandConfig.name ? `Create ${brandConfig.name}` : "Create new brand";
      el("createBrandBtn").textContent = "Save Brand";
      el("createBrandBtn").classList.remove("hidden");
      lockBrandFields(false);
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
        syncParserBusinessSelect();
        el("editExistingBrandLink")?.classList.remove("hidden");
        el("newBrandFields").classList.add("hidden");
        fillBrandFields(existing, brandConfig);
        lockBrandFields(Boolean(activeCsvPresetConfig));
        applyBusinessSourceType(existing);
        updatePresetBrandPanel(brandConfig, true);
      } else {
        openPrefilledBrandCreateForm(brandConfig);
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
      activeCsvPresetConfig = {
        mode: "demo_pe_brand",
        brand: { name: "Demo PE Brand", slug: "demo-pe-brand", description: "Greater Los Angeles restaurant demo from Overpass.", websiteUrl: "https://www.openstreetmap.org/", status: "active", metaTitle: "Demo PE Brand", metaDescription: "Demo Python source for restaurant locations.", countryOfOrigin: "United States" },
        url: "",
        sourceName: "demo_pe_brand_osm_restaurants",
        status: "Demo source loaded. Click Parse.",
        statusType: "ok"
      };
      el("sourceType").value = "python_editor";
      el("sourceName").value = "demo_pe_brand_osm_restaurants";
      el("recordPath").value = "";
      try {
        await loadDemoPeBrandCode();
        fillBrandFromConfig(activeCsvPresetConfig.brand);
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
      el("mapperView")?.classList.remove("template-edit-mode");
      // Release the business lock taken while editing a saved template,
      // or the mapper stays stuck with an un-selectable brand.
      if (typeof setTemplateEditBrandLock === "function") setTemplateEditBrandLock(false);
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
function pruneMappingSelectionsToParsedFields() {
      // Preset auto-mappings (Domino's/Pizza Hut/Global Hotels/Little
      // Caesars demos) hardcode field names by convention (e.g.
      // "Latitude") that don't always exist in the real parsed source -
      // saving with one of those still mapped fails backend validation
      // ("unknown source fields"). Only keep a preset mapping when the
      // value is a field the parser actually found; only parsed fields
      // should ever end up selected.
      const parsedSet = new Set(sourceFields);
      Object.keys(mappingSelections).forEach((key) => {
        const value = mappingSelections[key];
        if (value && !parsedSet.has(value)) {
          delete mappingSelections[key];
          autoMappedKeys.delete(key);
        }
      });
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
      optionalMappingKeys = new Set(["location_id", "latitude", "longitude", "status"]);
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
      setStatus("Choose a source and parse it to start mapping in left pane.", "");
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
      optionalMappingKeys = new Set(["latitude", "longitude", "phone_number", "franchise_name", "concept_type", "cuisine_type", "neighborhood", "district", "website_url", "google_maps_link"]);
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set(Object.keys(mappingSelections));
    }
function applyDemoRestaurantExcel() {
      resetPresetBrandEditState();
      excelFunctionMode = "demo_restaurant";
      activeCsvPresetConfig = {
        mode: "demo_restaurant",
        brand: window.APP_CONSTANTS.demoRestaurantBrand || {},
        url: window.APP_CONSTANTS.demoRestaurantExcelUrl || "",
        sourceName: "demo_restaurant_locations_excel",
        status: "Demo source ready. Click Parse.",
        statusType: "ok"
      };
      presetBrandEditMode = false;
      el("sourceType").value = "excel";
      el("sourceInputMode").value = "url";
      el("sourceUrl").value = window.APP_CONSTANTS.demoRestaurantExcelUrl || "";
      el("sourceUrl").placeholder = window.APP_CONSTANTS.demoRestaurantExcelUrl || sourceUrlPlaceholders.excel;
      setSourceUrlLocked(true);
      el("sourceName").value = "demo_restaurant_locations_excel";
      el("recordPath").value = "Sheet1";
      fillBrandFromConfig(activeCsvPresetConfig.brand);
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
      setStatus("Choose a source and parse it to start mapping in left pane.", "");
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
      setStatus("Choose a source and parse it to start mapping in left pane.", "");
    }
function resetXmlDemoLock() {
      resetPresetBrandEditState();
      resetSourceInputsForNewMode("xml");
      setStatus("Choose a source and parse it to start mapping in left pane.", "");
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
      optionalMappingKeys = new Set(["location_id", "latitude", "longitude", "phone_number", "website_url"]);
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
      setStatus("Choose a source and parse it to start mapping in left pane.", "");
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
        connectorEditor.onDidChangeModelContent(() => {
          if (connectorEditor.getValue().trim()) markBusinessRequirementTouched();
          saveDraft();
        });
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
        setConnectorFeedback("Loading packages", "");
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
        setConnectorFeedback("Loading runtime", "");
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
        // "Draft restored." is the whole message. The old version explained
        // the in-memory row count and told the user to re-parse - three
        // clauses of internal detail for something that either worked or
        // did not.
        setStatus("Draft restored.", "ok");
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
      const hasMappingContent = Boolean(mappingWorkspaceActivated || sourceParsed || sourceFields.length || activeTemplateId);
      const mapperMain = document.querySelector("#mapperView main");
      const mapperView = el("mapperView");
      const defaultBrandPanel = el("defaultBrandModelPanel");
      mapperMain?.classList.toggle("pre-parse-layout", !hasMappingContent);
      mapperView?.classList.toggle("pre-parse-active", !hasMappingContent);
      defaultBrandPanel?.classList.toggle("hidden", hasMappingContent);
      syncPreParseWorkspace(hasMappingContent);
      componentsPanel?.classList.toggle("hidden", !hasMappingContent);
      optionalPanel?.classList.toggle("hidden", !hasMappingContent);
      previewTabs?.classList.toggle("hidden", !hasMappingContent);
      const defaultBrandSummary = el("defaultBrandModelSummary");
      const defaultBrandButton = el("defaultBrandModelBtn");
      if (defaultBrandSummary && defaultBrandButton) {
        if (selectedBrand?.name) {
          defaultBrandSummary.innerHTML = `<strong>${escapeHtml(formatBrandName(selectedBrand.name))}</strong><br>Existing brand selected. You can edit its profile before parsing.`;
          defaultBrandButton.textContent = "Edit Brand Details";
        } else {
          defaultBrandSummary.innerHTML = "<strong>No brand selected</strong><br>Choose an existing brand or create a new one to begin.";
          defaultBrandButton.textContent = "Create Default Brand";
        }
      }
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
        select.addEventListener("change", async () => {
          const key = select.dataset.field;
          const nextValue = select.value;
          await applyMappingSelection(key, nextValue, select);
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
function syncPreParseWorkspace(hasMappingContent) {
      const sourcePanel = el("sourceControlsPanel");
      const brandPanel = el("preParseBrandPanel");
      const brandHost = el("preParseBrandHost");
      const parserHost = el("preParseParserHost");
      const parserBusinessField = el("parserBusinessField");
      if (!sourcePanel || !brandPanel || !brandHost || !parserHost) return;
      const brandIds = new Set(["brandSelectLabel", "brandSelect", "editExistingBrandLink", "presetBrandPanel", "newBrandFields"]);
      if (!hasMappingContent && !preParseRelocatedNodes) {
        preParseRelocatedNodes = Array.from(sourcePanel.children).map((node, index) => ({ node, index }));
        preParseRelocatedNodes.forEach(({ node }) => {
          if (brandIds.has(node.id)) brandHost.appendChild(node);
          else if (node.tagName === "H2") parserHost.appendChild(node);
          else parserHost.appendChild(node);
        });
        brandPanel.classList.remove("hidden");
        parserHost.classList.remove("hidden");
        parserBusinessField?.classList.remove("hidden");
        syncParserBusinessSelect();
        const parserTitle = parserHost.querySelector("h2");
        if (parserTitle) parserTitle.textContent = "Source Parser";
        updatePreParseBrandMode();
      } else if (hasMappingContent && preParseRelocatedNodes) {
        preParseRelocatedNodes.sort((left, right) => left.index - right.index).forEach(({ node }) => sourcePanel.appendChild(node));
        preParseRelocatedNodes = null;
        brandPanel.classList.add("hidden");
        parserHost.classList.add("hidden");
        parserBusinessField?.classList.add("hidden");
      }
      const status = el("status");
      if (!hasMappingContent && status && status.parentElement !== parserHost) {
        preParseStatusLocation = { parent: status.parentElement, nextSibling: status.nextSibling };
        const parserTitle = parserHost.querySelector("h2");
        parserHost.insertBefore(status, parserTitle?.nextSibling || parserHost.firstChild);
      } else if (hasMappingContent && status && preParseStatusLocation) {
        const { parent, nextSibling } = preParseStatusLocation;
        if (nextSibling && nextSibling.parentElement === parent) parent.insertBefore(status, nextSibling);
        else parent.insertBefore(status, parent.querySelector("main"));
        preParseStatusLocation = null;
      }
      if (!hasMappingContent) updatePreParseBrandMode();
    }
function updatePreParseBrandMode() {
      const createRadio = el("preParseCreateBrand");
      const editRadio = el("preParseEditBrand");
      if (!createRadio || !editRadio) return;
      const brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
      editRadio.disabled = !brands.some((brand) => brand?.business_id);
      syncParserBusinessSelect();
      if (hasSelectedBusiness()) setPreParseBrandValidation("");
      // loadAppData() (common.js) calls renderMappings() -> here on every
      // view's initial load, not just the Mapper's - without this guard,
      // opening Template Library (or any other tab) on a fresh session
      // would silently open the "Create Brand" form underneath it.
      if (el("mapperView")?.classList.contains("hidden")) return;
      if (createRadio.checked && !selectedBrand && !el("newBrandFields")?.classList.contains("is-open")) openBrandEditorForm("create");
    }
function openBrandEditorForm(mode = "create") {
      const form = el("newBrandFields");
      if (!form) return;
      if (mode === "edit" && !selectedBrand) {
        form.classList.add("hidden");
        form.classList.remove("is-open", "editing-brand");
        return;
      }
      brandEditMode = mode === "edit";
      presetCreateMode = false;
      if (brandEditMode) {
        fillBrandFields(selectedBrand, {});
        el("brandFormHeading").textContent = "Edit brand details";
        el("createBrandBtn").textContent = "Update Brand";
      } else {
        selectedBrand = null;
        el("brandSelect").value = "__create_new__";
        fillBrandFields({}, {});
        el("brandFormHeading").textContent = "Create new brand";
        el("createBrandBtn").textContent = "Save Brand";
      }
      form.classList.remove("hidden");
      form.classList.add("is-open");
      form.classList.toggle("editing-brand", brandEditMode);
      el("createBrandBtn").classList.remove("hidden");
      updatePreParseBrandMode();
    }
// Async because the move prompt is now the themed dialog rather than the
// browser's blocking confirm(); both call sites are event handlers, so
// awaiting is safe.
async function applyMappingSelection(key, nextValue, selectElement) {
      const previousOwner = Object.entries(mappingSelections).find(([otherKey, value]) => otherKey !== key && value === nextValue);
      if (nextValue && previousOwner) {
        const previousTarget = mappingTargets.find((target) => target.key === previousOwner[0]);
        const currentTarget = mappingTargets.find((target) => target.key === key);
        const move = await showAppConfirm(
          `${nextValue} is already mapped to ${previousTarget ? previousTarget.label : previousOwner[0]}. Move it to ${currentTarget ? currentTarget.label : key}? Cancel keeps it where it is.`,
          "Move this mapping?");
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
async function handleSourceFieldTargetSelection(sourceField, targetKey, selectElement) {
      if (!targetKey) return;
      hiddenMappingKeys.delete(targetKey);
      if (!primaryMappingKeys.has(targetKey)) optionalMappingKeys.add(targetKey);
      await applyMappingSelection(targetKey, sourceField);
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
function computeMappingConfidenceEvents() {
      // Diffs the immutable post-parse auto-mapping snapshot against the
      // final mapping the user is actually saving, scoring each
      // auto-suggestion (or fresh manual pairing) so the confidence layer
      // can learn which (target field, source column name) pairings are
      // reliable over time: kept as suggested = +1, switched to a
      // different mapped field = +0.5 (partial credit - it wasn't the
      // suggestion, but something was clearly relevant here), switched to
      // unmapped = -0.5 (a real negative signal), and a brand-new manual
      // pairing that had no prior suggestion at all = +1 (how a newer
      // field like "cuisine type" first builds confidence).
      const events = [];
      const keys = new Set([...Object.keys(originalAutoMapping), ...Object.keys(mappingSelections)]);
      keys.forEach((key) => {
        const originalSource = originalAutoMapping[key] || "";
        const finalSource = mappingSelections[key] || "";
        if (!originalSource && finalSource) {
          events.push({ target_key: key, source_field: finalSource, delta: 1 });
        } else if (originalSource && finalSource === originalSource) {
          events.push({ target_key: key, source_field: originalSource, delta: 1 });
        } else if (originalSource && finalSource) {
          events.push({ target_key: key, source_field: originalSource, delta: 0.5 });
        } else if (originalSource && !finalSource) {
          events.push({ target_key: key, source_field: originalSource, delta: -0.5 });
        }
      });
      return events;
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
        // DAT-04: a brand loaded twice produced two identical-looking rows in
        // this dropdown ("Domino's Pizza" listed twice), with no way to tell
        // them apart or merge them. Duplicates must NEVER reach the dropdown:
        // only the survivor of each similar-name group is offered, and the
        // rest are surfaced in the left rail to be merged one by one.
        const duplicateGroups = duplicateBusinessGroups(brands);
        const survivorIds = new Set();
        const hiddenDuplicateIds = new Set();
        duplicateGroups.forEach((group) => {
          // Keep the richest row - most listings, then oldest (the original
          // the later load duplicated), so the id other records already
          // point at is the one that stays selectable.
          const ranked = [...group].sort((a, b) =>
            (Number(b.listing_count || 0) - Number(a.listing_count || 0))
            || (businessCreatedTime(a) - businessCreatedTime(b)));
          survivorIds.add(ranked[0].business_id);
          ranked.slice(1).forEach((brand) => hiddenDuplicateIds.add(brand.business_id));
        });
        // A duplicate that is currently selected stays visible, or the
        // dropdown would silently blank out the user's own selection.
        if (selectedBrand?.business_id) hiddenDuplicateIds.delete(selectedBrand.business_id);
        const selectableBrands = brands.filter((brand) => !hiddenDuplicateIds.has(brand.business_id));
        // Name/ID/created_at ride along as hover detail, never in the option
        // text - an explicit ask, since inline detail made the list unreadable.
        el("brandSelect").innerHTML = '<option value="">Select an existing brand</option><option class="create-new-option" value="__create_new__">+ Create New Brand</option>' + selectableBrands.map((brand) => `<option value="${escapeHtml(brand.business_id)}" title="${escapeHtml(businessOptionLabel(brand))}">${escapeHtml(formatBrandName(brand.name))}</option>`).join("");
        el("brandSelect").dataset.brands = JSON.stringify(brands);
        renderDuplicateBrandRail(duplicateGroups);
        if (selectedBrand) el("brandSelect").value = selectedBrand.business_id;
        // FLT-05: only a plain list below the threshold, so a short list
        // doesn't gain unnecessary search chrome - explicit 1-character
        // threshold for this dropdown (FLT-02/FLT-03 use 2).
        if (typeof attachSearchableSelect === "function") attachSearchableSelect("brandSelect", { threshold: 15, minChars: 1 });
        syncParserBusinessSelect();
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
        setPreParseBrandValidation("");
        el("brandSelect").value = selectedBrand.business_id;
        syncParserBusinessSelect();
        el("editExistingBrandLink")?.classList.remove("hidden");
        await loadBrands(selectedBrand.name);
        el("brandSelect").value = selectedBrand.business_id;
        syncParserBusinessSelect();
        el("newBrandFields").classList.add("hidden");
        el("newBrandFields").classList.remove("is-open");
        el("newBrandFields").classList.remove("editing-brand");
        presetCreateMode = false;
        applyBusinessSourceType(selectedBrand);
        await refreshTemplatesForBusiness();
        setStatus(`Brand ${selectedBrand.name} is ready for mapping.`, "ok");
        showAppNotice(`${formatBrandName(selectedBrand.name)} was created and is ready for mapping.`, "Brand saved");
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
        setPreParseBrandValidation("");
        await loadBrands(selectedBrand.name);
        el("brandSelect").value = selectedBrand.business_id;
        syncParserBusinessSelect();
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
        showAppNotice(`${formatBrandName(selectedBrand.name)} was updated.`, "Brand updated");
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
      // Only count a mapped value if it's actually still a real parsed
      // source column - a re-parse (or source-type change) that shrinks
      // sourceFields can leave mappingSelections holding a stale value no
      // longer present, which used to inflate this count past
      // sourceFields.length (e.g. "105% - 21 of 20 columns mapped").
      const mappedSourceFields = new Set(Object.values(mapper.fields).filter((value) => value && sourceFields.includes(value)));
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
        // Searchable on the raw column name AND its mapped target label, so
        // "zip" finds address.postcode through its "ZIP Code" mapping.
        const searchKey = `${field} ${targetDefinition?.label || ""}`.toLowerCase();
        return `
          <div class="entity-field source-row-item" data-field-search="${escapeHtml(searchKey)}">
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
              <div class="entity-field" data-entity-search="${escapeHtml(`${item.label} ${source}`.toLowerCase())}">
                <div class="entity-field-name">${item.required ? '<span class="required">*</span> ' : ''}${escapeHtml(item.label)}</div>
                <div class="entity-field-source ${source ? "mapped" : "unmapped"}">${source ? `&#8592; ${escapeHtml(source)}` : "Unmapped"}</div>
              </div>
            `;
          }).join("")}</div>
        </div>
      `).join("");
      // A wide source (this one has 71 columns; OSM-style sources run past
      // 100) made this an unusable wall of fields - no way to scroll one
      // side independently, and no way to find a field without eyeballing
      // every row. Search + independent scrolling only appear once the list
      // is actually long enough to need them.
      const needsFieldSearch = sourceFields.length >= DATA_MODEL_SEARCH_THRESHOLD;
      const searchHtml = needsFieldSearch
        ? `<input type="search" id="dataModelFieldSearch" class="entity-field-search" placeholder="Search ${sourceFields.length} fields to map..." aria-label="Search source fields" autocomplete="off">`
        : "";
      target.innerHTML = `
        <div class="entity-map${needsFieldSearch ? " entity-map-scrollable" : ""}">
          <div class="entity-column">
            <div class="entity-box">
              <div class="entity-title">Source Fields</div>
              <div class="entity-subtitle">Available fields from the parsed source</div>
              ${searchHtml}
              <div class="entity-fields" id="dataModelSourceFields">${sourceItems || '<div class="entity-field-source unmapped">Parse a source to view fields.</div>'}</div>
              <div id="dataModelNoMatches" class="entity-field-source unmapped hidden">No field matches that search.</div>
            </div>
          </div>
          <div class="entity-column" id="dataModelEntityColumn">${entityItems || '<div class="status">Parse a source to view the data model.</div>'}</div>
        </div>
      `;
      target.querySelectorAll(".source-map-select").forEach((select) => {
        select.addEventListener("change", () => {
          handleSourceFieldTargetSelection(select.dataset.sourceField, select.value, select);
        });
      });
      const searchInput = el("dataModelFieldSearch");
      if (searchInput) {
        searchInput.addEventListener("input", () => {
          const term = searchInput.value.trim().toLowerCase();
          let visible = 0;
          // Match the source column name AND the mapped target label, so
          // "zip" finds address.postcode via its "ZIP Code" mapping.
          target.querySelectorAll("#dataModelSourceFields [data-field-search]").forEach((rowNode) => {
            const hit = !term || rowNode.dataset.fieldSearch.includes(term);
            rowNode.classList.toggle("hidden", !hit);
            if (hit) visible += 1;
          });
          el("dataModelNoMatches")?.classList.toggle("hidden", visible > 0);
          // Filtering the source side and leaving the target side untouched
          // breaks the visual pairing, so hide unmatched targets too.
          target.querySelectorAll("#dataModelEntityColumn [data-entity-search]").forEach((rowNode) => {
            rowNode.classList.toggle("hidden", Boolean(term) && !rowNode.dataset.entitySearch.includes(term));
          });
        });
      }
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
      if (el("mapperView")?.classList.contains("pre-parse-active") && !hasSelectedBusiness()) {
        const message = "Select an existing brand or create a new one before parsing.";
        businessRequirementTouched = true;
        setPreParseBrandValidation(message);
        (el("parserBusinessSelect") || el("brandSelect"))?.focus();
        return;
      }
      setPreParseBrandValidation("");
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
        pendingUnsavedParse = true;
        mappingWorkspaceActivated = true;
        templateEditMode = false;
        el("mapperView")?.classList.remove("template-edit-mode");
      // Release the business lock taken while editing a saved template,
      // or the mapper stays stuck with an un-selectable brand.
      if (typeof setTemplateEditBrandLock === "function") setTemplateEditBrandLock(false);
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
        pruneMappingSelectionsToParsedFields();
        autoAddDetectedOptionalFields();
        originalAutoMapping = { ...mappingSelections };
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
          el("sheetName").innerHTML = '<option value="">Loading sheets from URL</option>';
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
      const headerButton = el("loadSampleDatasetHeaderBtn");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!reset && button?.dataset.sampleLoaded === "true") return;
      const previousButton = setButtonBusy(button, reset ? "Reloading" : "Loading Sample Data");
      const previousHeaderButton = setButtonBusy(headerButton, reset ? "Reloading" : "Loading Sample Data");
      const previousReload = reloadLink ? setButtonBusy(reloadLink, "Reloading") : "";
      headerButton?.classList.remove("sample-state-idle", "sample-state-ready");
      headerButton?.classList.add("sample-state-loading");
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
      // No progress readout at all. The percentage was never a measurement
      // (elapsed/estimate, capped, so a slow load parked on "94%"), and the
      // honest elapsed-time version that replaced it was still a running
      // commentary nobody asked for. The button's own busy state says it is
      // working; the completion dialog says what happened. Nothing in
      // between earns the space.
      const progressTimer = null;
      try {
        const response = await fetch("/api/sample/load", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ reset }),
          signal: activeAbortController?.signal
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load sample dataset.");
        // Nothing written here either - the completion dialog reports the
        // outcome, and the status band stays out of the layout entirely.
        status.className = "report-status hidden";
        status.textContent = "";
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
        // The confirmation dialog below is the single acknowledgement for
        // this action now - a second, persistent bordered status card
        // repeating the same text underneath the button just lingered on
        // screen with nothing to dismiss it. Keep the status area hidden.
        status.className = "report-status hidden";
        status.textContent = "";
        updateSampleDatasetControls(result);
        const dialog = el("sampleLoadedDialog");
        if (dialog) {
          const dialogText = el("sampleLoadedDialogText");
          if (dialogText) dialogText.textContent = message;
          dialog.showModal();
        }
      } catch (error) {
        status.className = "report-status";
        const message = error.name === "AbortError" ? "Cancelled. No changes." : productSafeError(error.message, "Could not load sample dataset.");
        status.textContent = message;
        status.classList.remove("hidden");
        setStatus(message, error.name === "AbortError" ? "warn" : "error");
      } finally {
        if (progressTimer) window.clearInterval(progressTimer);
        clearButtonBusy(button, previousButton);
        clearButtonBusy(headerButton, previousHeaderButton);
        if (reloadLink) clearButtonBusy(reloadLink, previousReload);
        if (button && button.dataset.sampleLoaded !== "true") button.disabled = false;
        if (reloadLink) reloadLink.disabled = false;
        headerButton?.classList.remove("sample-state-loading");
        if (headerButton && headerButton.dataset.sampleLoaded !== "true") headerButton.classList.add("sample-state-idle");
      }
    }
async function clearSampleDataset() {
      const clearLink = el("clearSampleDatasetLink");
      // The button's own busy state (verb-ing label + spinner) already
      // shows this is in progress - a second, separate long-text loading
      // bar underneath it is redundant and was the thing flagged as
      // unwanted "keeps going and coming" text, not a real status update.
      const previousClear = clearLink ? setButtonBusy(clearLink, "Clearing") : "";
      const status = el("reportStatus");
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
      const headerButton = el("loadSampleDatasetHeaderBtn");
      const clearLink = el("clearSampleDatasetLink");
      const reloadLink = el("reloadSampleDatasetLink");
      if (!button && !headerButton) return;
      const loaded = Boolean(result.loaded || result.already_loaded || result.locations);
      [button, headerButton].filter(Boolean).forEach((sampleButton) => {
        sampleButton.dataset.sampleLoaded = loaded ? "true" : "false";
        sampleButton.disabled = loaded;
        sampleButton.classList.remove("sample-state-loading");
        sampleButton.classList.toggle('sample-state-ready', loaded);
        sampleButton.classList.toggle('sample-state-idle', !loaded);
        sampleButton.title = loaded ? "Sample data already in place." : "";
        sampleButton.textContent = loaded ? "Sample Dataset Already Loaded" : "Load Sample Dataset";
      });
      if (clearLink) clearLink.classList.toggle("hidden", !loaded);
      if (reloadLink) reloadLink.classList.toggle("hidden", !loaded);
    }
const JOB_HISTORY_STATUS_STYLE = {
  OK: "background:#dcfce7;color:#15803d;",
  NEEDS_REVIEW: "background:#fef3c7;color:#a16207;",
  FAILED: "background:#fee2e2;color:#b91c1c;",
};
function renderJobHistoryRow(job) {
      const style = JOB_HISTORY_STATUS_STYLE[job.status] || "background:#f1f5f9;color:#64748b;";
      const brandLabel = job.brand ? formatBrandName(job.brand) : "Unknown brand";
      return `<div style="border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
          <strong style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(brandLabel)}</strong>
          <span style="display:inline-block; padding:1px 8px; border-radius:999px; font-weight:700; font-size:11px; ${style}">${escapeHtml(job.status)}</span>
        </div>
        <div style="color:var(--muted); margin-top:3px;">${formatNumber(job.total_rows)} total &middot; ${formatNumber(job.mapped_rows)} valid &middot; ${formatNumber(job.error_listings)} in review${job.duplicate_listings_skipped ? ` &middot; ${formatNumber(job.duplicate_listings_skipped)} duplicate` : ""}</div>
      </div>`;
    }
const JOB_HISTORY_PANEL_LIMIT = 10;
async function loadJobHistory() {
      const target = el("jobHistoryList");
      if (!target) return;
      try {
        const response = await fetch(`/api/jobs/recent?limit=${JOB_HISTORY_PANEL_LIMIT}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load job history.");
        const jobs = Array.isArray(result.jobs) ? result.jobs : [];
        if (!jobs.length) {
          target.innerHTML = '<div class="report-status" style="padding: 8px 0; font-size: 12px;">No jobs yet this session.</div>';
          el("jobHistoryShowMoreBtn")?.classList.add("hidden");
          return;
        }
        target.innerHTML = jobs.map(renderJobHistoryRow).join("");
        // "Show More" only matters once there could be more than the panel
        // already shows - total comes straight from the same response so
        // there's no separate count round-trip just to decide visibility.
        const total = Number(result.total || 0);
        el("jobHistoryShowMoreBtn")?.classList.toggle("hidden", total <= jobs.length);
      } catch (error) {
        target.innerHTML = `<div class="report-status" style="padding: 8px 0; font-size: 12px;">${escapeHtml(productSafeError(error.message, "Job history is temporarily unavailable."))}</div>`;
        el("jobHistoryShowMoreBtn")?.classList.add("hidden");
      }
    }
const JOB_HISTORY_DIALOG_PAGE_SIZE = 20;
let jobHistoryDialogPage = 0;
let jobHistoryDialogTotal = 0;
async function loadJobHistoryDialogPage() {
      const listEl = el("jobHistoryDialogList");
      const pageInfoEl = el("jobHistoryDialogPageInfo");
      if (!listEl) return;
      listEl.innerHTML = '<div class="report-status" style="padding: 8px 0; font-size: 12px;">Loading…</div>';
      try {
        const offset = jobHistoryDialogPage * JOB_HISTORY_DIALOG_PAGE_SIZE;
        const response = await fetch(`/api/jobs/recent?limit=${JOB_HISTORY_DIALOG_PAGE_SIZE}&offset=${offset}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load job history.");
        const jobs = Array.isArray(result.jobs) ? result.jobs : [];
        jobHistoryDialogTotal = Number(result.total || 0);
        listEl.innerHTML = jobs.length
          ? jobs.map(renderJobHistoryRow).join("")
          : '<div class="report-status" style="padding: 8px 0; font-size: 12px;">No jobs on this page.</div>';
        const lastPage = jobHistoryDialogTotal > 0 ? Math.ceil(jobHistoryDialogTotal / JOB_HISTORY_DIALOG_PAGE_SIZE) - 1 : 0;
        if (pageInfoEl) pageInfoEl.textContent = `Page ${jobHistoryDialogPage + 1} of ${lastPage + 1} (${formatNumber(jobHistoryDialogTotal)} total)`;
        el("jobHistoryDialogPrevBtn")?.toggleAttribute("disabled", jobHistoryDialogPage <= 0);
        el("jobHistoryDialogNextBtn")?.toggleAttribute("disabled", jobHistoryDialogPage >= lastPage);
      } catch (error) {
        listEl.innerHTML = `<div class="report-status" style="padding: 8px 0; font-size: 12px;">${escapeHtml(productSafeError(error.message, "Job history is temporarily unavailable."))}</div>`;
      }
    }
function openJobHistoryDialog() {
      jobHistoryDialogPage = 0;
      el("jobHistoryDialog")?.showModal();
      loadJobHistoryDialogPage();
    }
function jobHistoryDialogPrev() {
      if (jobHistoryDialogPage > 0) { jobHistoryDialogPage -= 1; loadJobHistoryDialogPage(); }
    }
function jobHistoryDialogNext() {
      const lastPage = jobHistoryDialogTotal > 0 ? Math.ceil(jobHistoryDialogTotal / JOB_HISTORY_DIALOG_PAGE_SIZE) - 1 : 0;
      if (jobHistoryDialogPage < lastPage) { jobHistoryDialogPage += 1; loadJobHistoryDialogPage(); }
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

        const coverage = sourceFields.length ? Math.round(new Set(Object.values(mapper.fields).filter((value) => value && sourceFields.includes(value))).size / sourceFields.length * 100) : 0;
        if (coverage < 50) {
          setStatus("Mapping coverage must reach 50% before saving.", "warn");
          return;
        }
        // setStatus() writes plain textContent - it can't host the spinner
        // element the rest of the app uses for in-progress states, and a
        // trailing "..." string is against that same convention (busyMarkup()
        // strips it and adds a real spinner instead). Match that here rather
        // than a bare ellipsis with no visible spinner.
        const statusEl = el("status");
        if (statusEl) {
          statusEl.className = "status";
          statusEl.innerHTML = '<span class="spinner"></span> Preparing your records';
        }
        setProgress(10, "Preparing your records");
        try {
          const batches = buildSaveBatches(sourceRows, mapper, sourceFields);
          const batchEventId = newSessionId();
          let mappedRows = 0;
          let errorListings = 0;
          let duplicateListings = 0;
          let processedRows = 0;
          let eventId = "";
          const startTime = Date.now();
          for (let index = 0; index < batches.length; index += 1) {
            const batch = batches[index];
            const totalToProcess = sourceRows.length;
            const batchStartProcessed = processedRows;
            // Before any batch has finished there's no real pace yet, so
            // assume a conservative rows/ms rate; once at least one batch
            // has completed, use its actual measured pace instead. Either
            // way this keeps climbing every tick instead of freezing at a
            // single static "Starting batch..." message for the whole
            // (often single-batch) save.
            const priorMsPerRow = processedRows > 0 ? (Date.now() - startTime) / processedRows : 20;
            const batchEstimatedMs = Math.max(600, batch.rows.length * priorMsPerRow);
            const batchStartedAt = Date.now();
            const renderBatchProgress = () => {
              const elapsed = Date.now() - batchStartedAt;
              const withinBatchFraction = Math.min(0.98, elapsed / batchEstimatedMs);
              const rowsEstimate = Math.min(totalToProcess, batchStartProcessed + Math.round(withinBatchFraction * batch.rows.length));
              const progress = Math.min(90, 20 + Math.round(rowsEstimate / Math.max(totalToProcess, 1) * 65));
              const remainingMs = Math.max(0, batchEstimatedMs - elapsed) + (batches.length - 1 - index) * batchEstimatedMs;
              const etaSeconds = Math.round(remainingMs / 1000);
              setProgress(progress, `${rowsEstimate} of ${totalToProcess} records processed, about ${etaSeconds}s remaining`);
            };
            renderBatchProgress();
            const batchProgressTimer = window.setInterval(renderBatchProgress, 400);
            let response;
            try {
              response = await fetch("/api/save", {
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
                  save_template: !activeTemplateId && index === 0,
                  // Same mapping applies to every batch of one save - only
                  // record the confidence signal once, not once per batch.
                  mapping_confidence_events: index === 0 ? computeMappingConfidenceEvents() : []
                })
              });
            } finally {
              window.clearInterval(batchProgressTimer);
            }
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Could not save template.");
            eventId = result.event_id || batchEventId;
            mappedRows += result.mapped_rows || 0;
            errorListings += result.error_listings || 0;
            duplicateListings += result.duplicate_listings_skipped || 0;
            processedRows += batch.rows.length;
            setProgress(Math.min(90, 20 + Math.round(processedRows / Math.max(totalToProcess, 1) * 65)), `${processedRows} of ${totalToProcess} records processed`);
          }
          lastSaveEventId = eventId || batchEventId;
          el("reviewEventId").value = lastSaveEventId;
          // A save just created new error listings - force a live re-count so
          // the tab badge reflects them (and the SQLite cache is refreshed).
          await refreshReviewCount(true);
          if (typeof loadErrorBrandBreakdown === "function") loadErrorBrandBreakdown();
          hideProgress();
          // The completion dialog below is now the single acknowledgement
          // for a finished save - the "Preparing your records" spinner
          // status (set at the very start of this function) must not keep
          // showing underneath it once there's something to actually read.
          const statusEl = el("status");
          if (statusEl) {
            statusEl.className = "status hidden";
            statusEl.textContent = "";
          }
          const prefix = activeTemplateId ? "Template updated. " : "";
          const insertedCount = Math.max(0, mappedRows - duplicateListings);
          const duplicateNote = duplicateListings ? `, ${duplicateListings} duplicate${duplicateListings === 1 ? "" : "s"} found` : "";
          // Compact one-line summary naming the brand and source type, not
          // just bare counts, so this reads clearly even if the user only
          // sees it after the save finished in the background.
          const brandLabel = mapper.brand ? formatBrandName(mapper.brand) : "This brand";
          const sourceLabel = String(mapper.source_type || "source").replace(/_/g, " ");
          const reviewNote = errorListings ? ` (AI will attempt the best fixes)` : "";
          showSaveCompletion(`${prefix}${brandLabel} ${sourceLabel}: ${sourceRows.length} read, ${insertedCount} saved${duplicateNote}, ${errorListings} need${errorListings === 1 ? "s" : ""} review${reviewNote}.`);
          pendingUnsavedParse = false;
          loadJobHistory();
        } catch (error) {
          // Read BEFORE hideProgress(), which resets the flag. A save the
          // user sent to the background has to announce its own failure the
          // same way it would have announced success: they are no longer
          // looking at the mapper (resetMapping() returned them to the
          // pre-parse layout), so the inline status line below is invisible
          // to them. A failure must never be quieter than a success.
          const wasBackgrounded = typeof saveProgressHiddenByUser !== "undefined" && saveProgressHiddenByUser;
          hideProgress();
          const message = productSafeError(error.message, "Could not save template.");
          setStatus(message, "error");
          if (wasBackgrounded) {
            const brandLabel = mapper.brand ? formatBrandName(mapper.brand) : "This brand";
            showAppNotice(`${brandLabel}: the save running in the background did not finish. ${message}`, "Save did not finish");
            // The server records the failed attempt as a FAILED job, so the
            // history panel is where the user can see it afterwards.
            loadJobHistory();
          }
        }
      } finally {
        clearButtonBusy(saveBtn, previousSaveBtn);
      }
    }

function showBackgroundSaveNotice() {
      const target = el("jobHistoryList");
      if (!target || document.getElementById("jobHistoryRunningRow")) return;
      const row = document.createElement("div");
      row.id = "jobHistoryRunningRow";
      row.style.cssText = "border:1px solid #93c5fd; border-radius:6px; padding:8px 10px; font-size:12px; background:#eff6ff; color:#1e40af;";
      row.innerHTML = `<span class="spinner"></span> Saving in the background — you'll see a summary here and a popup once it's done.`;
      target.insertBefore(row, target.firstChild);
    }
function clearBackgroundSaveNotice() {
      document.getElementById("jobHistoryRunningRow")?.remove();
    }
function showSaveCompletion(message) {
      // saveCompletionDialog is now a static <dialog class="app-help-dialog">
      // in integrations.html (same theme as appHelpDialog/sampleLoadedDialog),
      // with a centered OK button - previously built ad hoc in JS with its
      // own inline styles and a right-aligned button, out of step with
      // every other confirmation popup in the app.
      const dialog = el("saveCompletionDialog");
      if (!dialog) {
        window.alert(message);
        return;
      }
      el("saveCompletionMessage").textContent = message;
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
        if (typeof refreshReviewCount === "function") await refreshReviewCount(true);
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
        if (!response.ok) throw new Error(result.error || "Workspace reset failed.");
        el("masterDeleteConfirmDialog").close();
        status.className = "action-feedback ok";
        status.textContent = "Workspace reset complete.";
        setStatus("Workspace reset complete. You will be signed out so the app can reload cleanly.", "ok");
        showAppNotice("Workspace reset complete. You will be signed out so the app can reload cleanly.", "Reset complete");
        sourceRows = [];
        sourceFields = [];
        sourceParsed = false;
        mappingSelections = {};
        selectedBrand = null;
        appDataLoaded = false;
        localStorage.removeItem("review_error_count_last");
        if (el("reviewCount")) el("reviewCount").textContent = "0";
        logout();
        prepareReferenceData();
      } catch (error) {
        status.className = "action-feedback error";
        status.textContent = productSafeError(error.message, "Workspace reset failed.");
      } finally {
        button.disabled = false;
        clearButtonBusy(confirmButton, previousConfirmButton);
      }
    }

function resetMapping() {
      activeTemplateId = "";
      templateEditMode = false;
      el("mapperView")?.classList.remove("template-edit-mode");
      // Release the business lock taken while editing a saved template,
      // or the mapper stays stuck with an un-selectable brand.
      if (typeof setTemplateEditBrandLock === "function") setTemplateEditBrandLock(false);
      mappingSelections = {};
      autoMappedKeys = new Set();
      optionalMappingKeys = new Set();
      hiddenMappingKeys = new Set();
      customAliases = {};
      sourceRows = [];
      sourceFields = [];
      sourceRecordCount = 0;
      sourceParsed = false;
      pendingUnsavedParse = false;
      mappingWorkspaceActivated = false;
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
      // Restart is a fresh pre-parse workspace, even when the user clicked it
      // from Reporting, Review, or a previously restored mapping session.
      sessionStorage.setItem("activeTab", "mapperView");
      const restartUrl = new URL(window.location.href);
      restartUrl.searchParams.set("view", "mapperView");
      window.location.assign(restartUrl.toString());
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
        // Detail (ID / listing count / created_at) lives on hover, never in
        // the option text - an explicit ask, since it made the list unreadable.
        const optionsHtml = '<option value="">Select an active brand</option>' + brandsWithDisplayIds.map(b => `<option value="${escapeHtml(b.business_id)}" title="${escapeHtml(businessOptionLabel(b))}">${escapeHtml(businessOptionLabelShort(b))}</option>`).join('');
        box.innerHTML = `
          <label style="display: block; font-weight: 700; margin-bottom: 4px; color: var(--navy);" for="activeBusinessesDropdown">
            Active Brands (${brands.length})
          </label>
          <select id="activeBusinessesDropdown" style="width: 100%; padding: 6px 8px; border-radius: 4px; border: 1px solid var(--line); background: #ffffff;">
            ${optionsHtml}
          </select>
        `;
        el("activeBusinessesDropdown").addEventListener("change", (event) => {
          if (!event.target.value) return;
          el("brandSelect").value = event.target.value;
          el("brandSelect").dispatchEvent(new Event("change"));
          box.style.display = "none";
        });
      } catch (err) {
        box.innerHTML = `<div style="color: var(--error);">${escapeHtml(err.message)}</div>`;
      }
    }
