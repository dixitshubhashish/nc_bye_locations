// Template Library tab: browse, load, and save saved mapping templates.

let templateBrandNames = {};
let loadTemplateLibraryPromise = null;
let templateLibraryLoaded = false;
const templatePageCache = new Map();
const TEMPLATE_CACHE_TTL_MS = 60 * 1000;
// login-hotfix.js and integrations.html's own bootstrap script can each
// independently call switchView("templateLibraryView") on the same page
// load (the hotfix script loads async, so ordering isn't guaranteed).
// Without this guard, two concurrent loadTemplateFilters().then(
// loadTemplateLibrary) chains race on #templateResults - whichever
// resolves last wins, and if that one hits an error or a slower response,
// it can stomp the other call's already-rendered table with "Loading..."
// or an error, leaving the table never actually shown.
function loadTemplateLibrary() {
      if (loadTemplateLibraryPromise) return loadTemplateLibraryPromise;
      loadTemplateLibraryPromise = _loadTemplateLibraryOnce().finally(() => {
        loadTemplateLibraryPromise = null;
      });
      return loadTemplateLibraryPromise;
    }
const TEMPLATE_PRELOAD_SIZE = 50;
const TEMPLATE_PAGE_SIZE = 200;
// Live paging state for the current search/filter.
let templatePaging = null;
// Self-contained spinner (the .spinner CSS class is scoped to .report-status,
// so it wouldn't render inside the template results panel). Reuses the
// spinCircle keyframe that the Review search button already relies on.
function _templateSpinner() {
      return `<span style="display:inline-block; width:12px; height:12px; border:2px solid var(--line); border-top-color: var(--accent); border-radius:50%; animation: spinCircle 0.8s linear infinite; vertical-align:middle; margin-right:6px;"></span>`;
    }

function _templateRowHtml(template) {
      const label = templatePaging?.sourceTypeIdToLabel?.[template.source_type_id] || sourceTypeLabel(template.source_type_id);
      return `<tr><td data-sort-value="${escapeHtml(template.name)}">${escapeHtml(template.name)}</td><td data-sort-value="${escapeHtml(templateBrandNames[template.business_id] || template.business_id)}">${escapeHtml(templateBrandNames[template.business_id] || template.business_id)}</td><td data-sort-value="${escapeHtml(label)}">${escapeHtml(label)}</td><td data-sort-value="${escapeHtml(template.created_at)}">${escapeHtml(template.created_at)}</td><td data-sort-value="${escapeHtml(template.updated_at)}">${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`;
    }

async function _fetchTemplatesPage(offset, limit) {
      const p = templatePaging;
      const cacheKey = JSON.stringify([p.search, p.businessId, p.sourceTypeId, offset, limit]);
      const cached = templatePageCache.get(cacheKey);
      if (cached && Date.now() - cached.createdAt < TEMPLATE_CACHE_TTL_MS) return cached.templates;
      const response = await fetch(`/api/templates?search=${encodeURIComponent(p.search)}&business_id=${encodeURIComponent(p.businessId)}&source_type_id=${encodeURIComponent(p.sourceTypeId)}&limit=${limit}&offset=${offset}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load templates.");
      const templates = result.templates || [];
      templatePageCache.set(cacheKey, { createdAt: Date.now(), templates });
      return templates;
    }

function _renderTemplateRows(templates) {
      const body = el("templateResultsBody");
      if (!body) return;
      body.innerHTML = templates.map((t) => {
        templatePaging.byId[t.workflow_template_id] = t;
        return _templateRowHtml(t);
      }).join("");
      enableSortableTable(body.closest("table"));
      body.querySelectorAll("button[data-load-template]:not([data-bound])").forEach((button) => {
        button.setAttribute("data-bound", "1");
        button.addEventListener("click", () => {
          setButtonBusy(button, "Loading");
          loadTemplateIntoEditor(templatePaging.byId[button.dataset.loadTemplate]);
        });
      });
    }

async function _loadTemplatePage(offset, limit, direction) {
      const p = templatePaging;
      if (!p || p.loading) return;
      p.loading = true;
      const controls = el("templatePagination");
      const nextButton = el("templateNextBtn");
      const previousButton = el("templatePreviousBtn");
      if (nextButton) nextButton.disabled = true;
      if (previousButton) previousButton.disabled = true;
      try {
        const page = await _fetchTemplatesPage(offset, limit);
        p.pageOffset = offset;
        p.pageRows = page;
        _renderTemplateRows(page);
        if (controls) controls.classList.remove("hidden");
        if (el("templatePageStatus")) el("templatePageStatus").textContent = `Showing ${offset + 1}-${offset + page.length}`;
        if (previousButton) previousButton.disabled = offset === 0;
        if (nextButton) nextButton.disabled = page.length < limit;
      } catch (error) {
        if (el("templatePageStatus")) el("templatePageStatus").textContent = productSafeError(error.message, "Could not load templates.");
      } finally {
        p.loading = false;
        if (direction === "next" && nextButton && !p.loading) nextButton.disabled = false;
      }
    }

async function _loadTemplateLibraryOnce() {
      const target = el("templateResults");
      const searchBtn = el("templateSearchBtn");
      const originalBtnHtml = searchBtn ? searchBtn.innerHTML : "Search";
      if (searchBtn) setButtonBusy(searchBtn, "Searching");
      target.className = "status";
      target.innerHTML = `${_templateSpinner()}Loading templates...`;
      // Fresh paging state for this search/filter.
      templatePaging = {
        search: el("templateSearch").value.trim(),
        businessId: el("templateBusinessFilter").value,
        sourceTypeId: el("templateSourceFilter").value,
        offset: 0,
        pageOffset: 0,
        pageRows: [],
        loading: false,
        byId: {},
        sourceTypeIdToLabel: Object.fromEntries(sourceTypes.map((source) => [source.source_type_id, sourceTypeLabel(source.name)])),
      };
      try {
        // Preload only a small first window after login; later pages are
        // fetched explicitly in 200-row chunks.
        const firstPage = await _fetchTemplatesPage(0, TEMPLATE_PRELOAD_SIZE);
        if (!firstPage.length) {
          target.className = "status";
          target.textContent = "No templates found.";
          templateLibraryLoaded = true;
          return;
        }
        target.className = "";
        target.innerHTML = `<table><thead><tr><th data-sort-key="template">Template</th><th data-sort-key="brand">Brand</th><th data-sort-key="source">Source Type</th><th data-sort-key="created">Created</th><th data-sort-key="updated">Updated</th><th>Action</th></tr></thead><tbody id="templateResultsBody"></tbody></table><div id="templatePagination" class="template-pagination"><button id="templatePreviousBtn" class="secondary" type="button" disabled>Previous</button><span id="templatePageStatus">Showing 1-${firstPage.length}</span><button id="templateNextBtn" type="button" ${firstPage.length < TEMPLATE_PRELOAD_SIZE ? "disabled" : ""}>Next 200</button></div>`;
        templatePaging.pageRows = firstPage;
        _renderTemplateRows(firstPage);
        templateLibraryLoaded = true;
        el("templatePreviousBtn").addEventListener("click", () => _loadTemplatePage(Math.max(0, templatePaging.pageOffset - TEMPLATE_PAGE_SIZE), TEMPLATE_PAGE_SIZE, "previous"));
        el("templateNextBtn").addEventListener("click", () => _loadTemplatePage(templatePaging.pageOffset === 0 ? TEMPLATE_PRELOAD_SIZE : templatePaging.pageOffset + TEMPLATE_PAGE_SIZE, TEMPLATE_PAGE_SIZE, "next"));
      } catch (error) {
        target.className = "status error";
        target.textContent = productSafeError(error.message, "Could not load templates.");
      } finally {
        if (searchBtn) {
          clearButtonBusy(searchBtn, originalBtnHtml);
        }
      }
    }
let loadTemplateFiltersPromise = null;
function loadTemplateFilters() {
      if (loadTemplateFiltersPromise) return loadTemplateFiltersPromise;
      loadTemplateFiltersPromise = _loadTemplateFiltersOnce().finally(() => {
        loadTemplateFiltersPromise = null;
      });
      return loadTemplateFiltersPromise;
    }
async function _loadTemplateFiltersOnce() {
      const [businessResult, sourceResult] = await Promise.allSettled([
        fetch("/api/brands?search=").then(async (response) => {
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "Could not load brands.");
          return result;
        }),
        fetch("/api/source-types").then(async (response) => {
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "Could not load source types.");
          return result;
        }),
      ]);
      const businesses = businessResult.status === "fulfilled" ? (businessResult.value.brands || []) : [];
      templateBrandNames = Object.fromEntries(businesses.map((business) => [business.business_id, formatBrandName(business.name)]));
      el("templateBusinessFilter").innerHTML = '<option value="">All brands</option><option class="create-new-option" value="__create_new__">+ Create New Brand</option>' + businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(formatBrandName(business.name))}</option>`).join("");
      sourceTypes = sourceResult.status === "fulfilled" ? (sourceResult.value.source_types || []) : [];
      el("templateSourceFilter").innerHTML = '<option value="">All source types</option>' + sourceTypes.map((source) => `<option value="${escapeHtml(source.source_type_id)}">${escapeHtml(sourceTypeLabel(source.name))}</option>`).join("");
      populateSourceTypeSelects();
    }
function loadTemplateIntoEditor(template) {
      const components = template.components?.mapper || template.components || {};
      const brands = JSON.parse(el("brandSelect").dataset.brands || "[]");
      selectedBrand = brands.find((brand) => brand.business_id === template.business_id) || { business_id: template.business_id, name: components.brand || "", source_type_id: template.source_type_id };
      activeTemplateId = template.workflow_template_id;
      const brandOption = document.querySelector(`#brandSelect option[value="${CSS.escape(template.business_id)}"]`);
      if (brandOption) el("brandSelect").value = template.business_id;
      applyBusinessSourceType(selectedBrand, { preserveSourceType: false });
      el("sourceName").value = components.source_name || template.name || "";
      mappingSelections = { ...(components.fields || {}) };
      // Rebuild the editable source-field universe from what the template
      // stored (full column list), falling back to just the mapped paths for
      // older templates saved before source_fields was persisted. This is
      // what makes every mapping dropdown offer real options to switch to,
      // rather than only the single value already selected.
      const storedSourceFields = Array.isArray(components.source_fields) ? components.source_fields : [];
      const mappedValues = Object.values(mappingSelections).filter(Boolean);
      sourceFields = Array.from(new Set([...storedSourceFields, ...mappedValues]));
      sourceFields.sort((a, b) => (fieldOrderIndex.get(a) ?? 999) - (fieldOrderIndex.get(b) ?? 999));
      sourceRows = [];
      resolvedRecordPath = "";
      // Editing a stored template, not a freshly parsed file: enables the
      // grid + Save to work off sourceFields with no live rows.
      templateEditMode = true;
      sourceParsed = false;
      optionalMappingKeys = new Set(Object.keys(mappingSelections).filter((key) => !primaryMappingKeys.has(key)));
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set();
      renderMappings();
      renderTemplateEditSourcePreview();
      switchView("mapperView");
      setStatus(`Loaded ${template.name}. Edit the field mapping, then click Save Template to update.`, "ok");
    }
// With no live rows to preview, show the stored source columns so the editor
// isn't a blank panel (the "source mapper view shows nothing" case) and it's
// clear which columns are available to map.
function renderTemplateEditSourcePreview() {
      const target = el("sourcePreview");
      if (!target) return;
      if (!sourceFields.length) {
        target.innerHTML = `<div class="status">This template has no stored source columns. Parse a source file to remap it.</div>`;
        return;
      }
      const mapped = new Set(Object.values(mappingSelections).filter(Boolean));
      target.innerHTML = `<div style="font-size:12px; color: var(--muted); margin-bottom:8px;">Editing a saved template — showing its ${sourceFields.length} stored source column${sourceFields.length === 1 ? "" : "s"} (no live data rows). Parse a source file to bring in real records.</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${sourceFields.map((field) => `<span style="display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; border:1px solid var(--line); background:${mapped.has(field) ? "#e6f4f1" : "#f5f5f5"}; color:${mapped.has(field) ? "#0f6d63" : "#555"};">${escapeHtml(field)}${mapped.has(field) ? " ✓" : ""}</span>`).join("")}</div>`;
    }
async function saveEditedTemplate() {
      const response = await fetch("/api/templates/save", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ workflow_template_id: activeTemplateId, components: { mapper: getMapper() } }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not update template.");
      setStatus("Template saved.", "ok");
    }
