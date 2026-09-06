/**
 * Template Library UI Subpackage Module.
 * 
 * Manages template search, brand/source filter criteria, template loading into editor,
 * and saving updated template versions.
 * Communicates directly with backend endpoints (`/api/predefined-templates`, `/api/templates`, `/api/templates/save`)
 * routed to `whitespace_tool.templates`.
 */

let templateBusinessNames = {};
let templateBrandNames = {};
let loadTemplateLibraryPromise = null;
const TEMPLATE_PAGE_SIZE = 50;
let templatePaging = { offset: 0, loading: false, done: false, search: "", businessId: "", sourceTypeId: "", byId: {} };
let templateLazyObserver = null;

function _templateSpinner() {
  return `<span style="display:inline-block; width:12px; height:12px; border:2px solid var(--line); border-top-color: var(--accent); border-radius:50%; animation: spinCircle 0.8s linear infinite; vertical-align:middle; margin-right:6px;"></span>`;
}

function _templateRowHtml(template) {
  const label = templatePaging?.sourceTypeIdToLabel?.[template.source_type_id] || sourceTypeLabel(template.source_type_id);
  return `<tr><td>${escapeHtml(template.name)}</td><td>${escapeHtml(templateBrandNames[template.business_id] || templateBusinessNames[template.business_id] || template.business_id)}</td><td>${escapeHtml(label)}</td><td>${escapeHtml(template.created_at)}</td><td>${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`;
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
      if (typeof setButtonBusy === "function") setButtonBusy(button, "Loading");
      loadTemplateIntoEditor(templatePaging.byId[button.dataset.loadTemplate]);
    });
  });
}

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

function renderTemplateEditSourcePreview() {
  const target = el("sourcePreview");
  if (!target) return;
  if (typeof sourceFields === "undefined" || !sourceFields.length) {
    target.innerHTML = `<div class="status">This template has no stored source columns. Parse a source file to remap it.</div>`;
    return;
  }
  const mapped = new Set(Object.values(mappingSelections || {}).filter(Boolean));
  target.innerHTML = `<div style="font-size:12px; color: var(--muted); margin-bottom:8px;">Editing a saved template — showing its ${sourceFields.length} stored source column${sourceFields.length === 1 ? "" : "s"} (no live data rows). Parse a source file to bring in real records.</div>
    <div style="display:flex; flex-wrap:wrap; gap:6px;">${sourceFields.map((field) => `<span style="display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; border:1px solid var(--line); background:${mapped.has(field) ? "#e6f4f1" : "#f5f5f5"}; color:${mapped.has(field) ? "#0f6d63" : "#555"};">${escapeHtml(field)}${mapped.has(field) ? " ✓" : ""}</span>`).join("")}</div>`;
}

function loadTemplateLibrary() {
  if (loadTemplateLibraryPromise) return loadTemplateLibraryPromise;
  loadTemplateLibraryPromise = _loadTemplateLibraryOnce().finally(() => {
    loadTemplateLibraryPromise = null;
  });
  return loadTemplateLibraryPromise;
}

async function _loadTemplateLibraryOnce() {
  const target = el("templateResults");
  if (!target) return;
  const search = el("templateSearch") ? el("templateSearch").value.trim() : "";
  const businessId = el("templateBusinessFilter") ? el("templateBusinessFilter").value : "";
  const sourceTypeId = el("templateSourceFilter") ? el("templateSourceFilter").value : "";
  target.className = "status";
  target.textContent = "Loading...";
  try {
    const response = await fetch(`/api/templates?search=${encodeURIComponent(search)}&business_id=${encodeURIComponent(businessId)}&source_type_id=${encodeURIComponent(sourceTypeId)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load templates.");
    if (!result.templates || !result.templates.length) {
      target.textContent = "No templates found.";
      return;
    }
    const sourceTypeIdToLabel = Object.fromEntries(sourceTypes.map((source) => [source.source_type_id, sourceTypeLabel(source.name)]));
    target.className = "";
    target.innerHTML = `<table><thead><tr><th>Template</th><th>Business</th><th>Source Type</th><th>Created</th><th>Updated</th><th>Action</th></tr></thead><tbody id="templateResultsBody">${result.templates.map((template) => `<tr><td>${escapeHtml(template.name)}</td><td>${escapeHtml(templateBusinessNames[template.business_id] || template.business_id)}</td><td>${escapeHtml(sourceTypeIdToLabel[template.source_type_id] || sourceTypeLabel(template.source_type_id))}</td><td>${escapeHtml(template.created_at)}</td><td>${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`).join("")}</tbody></table>`;
    target.querySelectorAll("button[data-load-template]").forEach((button) => button.addEventListener("click", () => loadTemplateIntoEditor(result.templates.find((template) => template.workflow_template_id === button.dataset.loadTemplate))));
  } catch (error) {
    target.className = "status error";
    target.textContent = productSafeError(error.message, "Could not load templates.");
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
    if (!businessResponse.ok) throw new Error(businessResult.error || "Could not load businesses.");
    businesses = businessResult.brands || [];
  } catch (error) {
    businesses = [];
  }
  templateBusinessNames = Object.fromEntries(businesses.map((business) => [business.business_id, business.name]));
  templateBrandNames = templateBusinessNames;
  if (el("templateBusinessFilter")) {
    el("templateBusinessFilter").innerHTML = '<option value="">All businesses</option><option class="create-new-option" value="__create_new__">+ Create New Business</option>' + businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(business.name)}</option>`).join("");
  }
  try {
    const sourceResponse = await fetch("/api/source-types");
    const sourceResult = await sourceResponse.json();
    if (!sourceResponse.ok) throw new Error(sourceResult.error || "Could not load source types.");
    sourceTypes = sourceResult.source_types || [];
  } catch (error) {
    sourceTypes = [];
  }
  if (el("templateSourceFilter")) {
    el("templateSourceFilter").innerHTML = '<option value="">All source types</option>' + sourceTypes.map((source) => `<option value="${escapeHtml(source.source_type_id)}">${escapeHtml(sourceTypeLabel(source.name))}</option>`).join("");
  }
  if (typeof populateSourceTypeSelects === "function") populateSourceTypeSelects();
}

function loadTemplateIntoEditor(template) {
  const components = template.components?.mapper || template.components || {};
  let brands = [];
  try {
    brands = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
  } catch (e) {
    brands = [];
  }
  selectedBrand = brands.find((brand) => brand.business_id === template.business_id) || { business_id: template.business_id, name: components.brand || "", source_type_id: template.source_type_id };
  activeTemplateId = template.workflow_template_id;
  const brandOption = document.querySelector(`#brandSelect option[value="${CSS.escape(template.business_id)}"]`);
  if (brandOption && el("brandSelect")) el("brandSelect").value = template.business_id;
  if (typeof applyBusinessSourceType === "function") applyBusinessSourceType(selectedBrand);
  if (el("sourceName")) el("sourceName").value = components.source_name || template.name || "";
  mappingSelections = { ...(components.fields || {}) };
  optionalMappingKeys = new Set(Object.keys(mappingSelections).filter((key) => typeof primaryMappingKeys !== "undefined" && !primaryMappingKeys.has(key)));
  hiddenMappingKeys = new Set();
  autoMappedKeys = new Set();
  if (typeof renderMappings === "function") renderMappings();
  if (typeof switchView === "function") switchView("mapperView");
  setStatus(`Loaded ${template.name}. Edit the fields, then save the updated template.`, "ok");
}

async function saveEditedTemplate() {
  const response = await fetch("/api/templates/save", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ workflow_template_id: activeTemplateId, components: { mapper: getMapper() } }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not update template.");
  setStatus("Template saved.", "ok");
}


