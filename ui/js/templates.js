// Template Library tab: browse, load, and save saved mapping templates.

let templateBrandNames = {};
let loadTemplateLibraryPromise = null;
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
const TEMPLATE_FIRST_PAGE = 100;   // quick initial paint
const TEMPLATE_PAGE_SIZE = 500;    // subsequent lazy pages, fetched from the backend by offset
// Live paging state for the current search/filter. Rebuilt on every fresh
// load; the IntersectionObserver reads it to fetch the next backend page.
let templatePaging = null;
let templateLazyObserver = null;
// Self-contained spinner (the .spinner CSS class is scoped to .report-status,
// so it wouldn't render inside the template results panel). Reuses the
// spinCircle keyframe that the Review search button already relies on.
function _templateSpinner() {
      return `<span style="display:inline-block; width:12px; height:12px; border:2px solid var(--line); border-top-color: var(--accent); border-radius:50%; animation: spinCircle 0.8s linear infinite; vertical-align:middle; margin-right:6px;"></span>`;
    }

function _templateRowHtml(template) {
      const label = templatePaging?.sourceTypeIdToLabel?.[template.source_type_id] || sourceTypeLabel(template.source_type_id);
      return `<tr><td>${escapeHtml(template.name)}</td><td>${escapeHtml(templateBrandNames[template.business_id] || template.business_id)}</td><td>${escapeHtml(label)}</td><td>${escapeHtml(template.created_at)}</td><td>${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`;
    }

async function _fetchTemplatesPage(offset, limit) {
      const p = templatePaging;
      const response = await fetch(`/api/templates?search=${encodeURIComponent(p.search)}&business_id=${encodeURIComponent(p.businessId)}&source_type_id=${encodeURIComponent(p.sourceTypeId)}&limit=${limit}&offset=${offset}`);
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not load templates.");
      return result.templates || [];
    }

function _appendTemplateRows(templates) {
      const body = el("templateResultsBody");
      if (!body) return;
      templates.forEach((t) => { templatePaging.byId[t.workflow_template_id] = t; });
      body.insertAdjacentHTML("beforeend", templates.map((t) => _templateRowHtml(t)).join(""));
      body.querySelectorAll("button[data-load-template]:not([data-bound])").forEach((button) => {
        button.setAttribute("data-bound", "1");
        button.addEventListener("click", () => {
          setButtonBusy(button, "Loading");
          loadTemplateIntoEditor(templatePaging.byId[button.dataset.loadTemplate]);
        });
      });
    }

// Fetch and append the next backend page (500 rows) when the sentinel scrolls
// into view. Guards against overlapping fetches and stops once a short page
// signals the end.
async function _loadNextTemplatePage() {
      const p = templatePaging;
      if (!p || p.done || p.loading) return;
      p.loading = true;
      const more = el("templateResultsMore");
      if (more) more.innerHTML = `${_templateSpinner()}Loading more...`;
      try {
        const page = await _fetchTemplatesPage(p.offset, TEMPLATE_PAGE_SIZE);
        _appendTemplateRows(page);
        p.offset += page.length;
        if (page.length < TEMPLATE_PAGE_SIZE) {
          p.done = true;
          if (templateLazyObserver) templateLazyObserver.disconnect();
          if (more) more.remove();
        } else if (more) {
          more.innerHTML = `${_templateSpinner()}Scroll for more (${p.offset} loaded)`;
        }
      } catch (error) {
        if (more) more.textContent = productSafeError(error.message, "Could not load more templates.");
      } finally {
        p.loading = false;
      }
    }

function _setupTemplateLazyObserver() {
      if (templateLazyObserver) templateLazyObserver.disconnect();
      const sentinel = el("templateResultsMore");
      if (!sentinel || templatePaging.done) return;
      templateLazyObserver = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) _loadNextTemplatePage();
      }, { rootMargin: "200px" });
      templateLazyObserver.observe(sentinel);
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
        done: false,
        loading: false,
        byId: {},
        sourceTypeIdToLabel: Object.fromEntries(sourceTypes.map((source) => [source.source_type_id, sourceTypeLabel(source.name)])),
      };
      if (templateLazyObserver) { templateLazyObserver.disconnect(); templateLazyObserver = null; }
      try {
        // First page: 100 rows, rendered immediately for a fast table.
        const firstPage = await _fetchTemplatesPage(0, TEMPLATE_FIRST_PAGE);
        if (!firstPage.length) {
          target.className = "status";
          target.textContent = "No templates found.";
          templatePaging.done = true;
          return;
        }
        target.className = "";
        target.innerHTML = `<table><thead><tr><th>Template</th><th>Brand</th><th>Source Type</th><th>Created</th><th>Updated</th><th>Action</th></tr></thead><tbody id="templateResultsBody"></tbody></table><div id="templateResultsMore" class="status" style="padding:8px 0;"></div>`;
        _appendTemplateRows(firstPage);
        templatePaging.offset = firstPage.length;
        // A short first page means there is nothing more to lazy-load.
        templatePaging.done = firstPage.length < TEMPLATE_FIRST_PAGE;
        const more = el("templateResultsMore");
        if (templatePaging.done) {
          if (more) more.remove();
        } else {
          if (more) more.innerHTML = `${_templateSpinner()}Scroll for more (${templatePaging.offset} loaded)`;
          _setupTemplateLazyObserver();
        }
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
      let businesses = [];
      try {
        const businessResponse = await fetch("/api/brands?search=");
        const businessResult = await businessResponse.json();
        if (!businessResponse.ok) throw new Error(businessResult.error || "Could not load brands.");
        businesses = businessResult.brands || [];
      } catch (error) {
        businesses = [];
      }
      templateBrandNames = Object.fromEntries(businesses.map((business) => [business.business_id, business.name]));
      el("templateBusinessFilter").innerHTML = '<option value="">All brands</option><option class="create-new-option" value="__create_new__">+ Create New Brand</option>' + businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(business.name)}</option>`).join("");
      try {
        const sourceResponse = await fetch("/api/source-types");
        const sourceResult = await sourceResponse.json();
        if (!sourceResponse.ok) throw new Error(sourceResult.error || "Could not load source types.");
        sourceTypes = sourceResult.source_types || [];
      } catch (error) {
        sourceTypes = [];
      }
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
