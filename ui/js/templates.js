// Template Library tab: browse, load, and save saved mapping templates.

let templateBusinessNames = {};
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
const TEMPLATE_FIRST_BATCH = 15;
const TEMPLATE_APPEND_CHUNK = 25;
// Self-contained spinner (the .spinner CSS class is scoped to .report-status,
// so it wouldn't render inside the template results panel). Reuses the
// spinCircle keyframe that the Review search button already relies on.
function _templateSpinner() {
      return `<span style="display:inline-block; width:12px; height:12px; border:2px solid var(--line); border-top-color: var(--accent); border-radius:50%; animation: spinCircle 0.8s linear infinite; vertical-align:middle; margin-right:6px;"></span>`;
    }

function _templateRowHtml(template, sourceTypeIdToLabel) {
      return `<tr><td>${escapeHtml(template.name)}</td><td>${escapeHtml(templateBusinessNames[template.business_id] || template.business_id)}</td><td>${escapeHtml(sourceTypeIdToLabel[template.source_type_id] || sourceTypeLabel(template.source_type_id))}</td><td>${escapeHtml(template.created_at)}</td><td>${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`;
    }

async function _loadTemplateLibraryOnce() {
      const target = el("templateResults");
      const searchBtn = el("templateSearchBtn");
      const originalBtnHtml = searchBtn ? searchBtn.innerHTML : "Search";
      const search = el("templateSearch").value.trim();
      const businessId = el("templateBusinessFilter").value;
      const sourceTypeId = el("templateSourceFilter").value;
      if (searchBtn) setButtonBusy(searchBtn, "Searching...");
      target.className = "status";
      target.innerHTML = `${_templateSpinner()}Loading templates...`;
      try {
        const response = await fetch(`/api/templates?search=${encodeURIComponent(search)}&business_id=${encodeURIComponent(businessId)}&source_type_id=${encodeURIComponent(sourceTypeId)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load templates.");
        const templates = result.templates || [];
        if (!templates.length) {
          target.className = "status";
          target.textContent = "No templates found.";
          return;
        }
        const sourceTypeIdToLabel = Object.fromEntries(sourceTypes.map((source) => [source.source_type_id, sourceTypeLabel(source.name)]));
        const byId = Object.fromEntries(templates.map((t) => [t.workflow_template_id, t]));
        target.className = "";
        // Render the first batch immediately so the list appears without
        // waiting on the whole set, then append the rest in chunks (with a
        // small "loading more" note) so a large library doesn't block the UI.
        const firstBatch = templates.slice(0, TEMPLATE_FIRST_BATCH);
        target.innerHTML = `<table><thead><tr><th>Template</th><th>Business</th><th>Source Type</th><th>Created</th><th>Updated</th><th>Action</th></tr></thead><tbody id="templateResultsBody">${firstBatch.map((t) => _templateRowHtml(t, sourceTypeIdToLabel)).join("")}</tbody></table>${templates.length > TEMPLATE_FIRST_BATCH ? `<div id="templateResultsMore" class="status" style="padding:8px 0;">${_templateSpinner()}Loading ${templates.length - TEMPLATE_FIRST_BATCH} more...</div>` : ""}`;

        const bindLoad = (root) => root.querySelectorAll("button[data-load-template]:not([data-bound])").forEach((button) => {
          button.setAttribute("data-bound", "1");
          button.addEventListener("click", () => loadTemplateIntoEditor(byId[button.dataset.loadTemplate]));
        });
        bindLoad(target);

        let index = firstBatch.length;
        const body = el("templateResultsBody");
        await new Promise((resolve) => {
          const appendChunk = () => {
            if (!body || index >= templates.length) {
              const more = el("templateResultsMore");
              if (more) more.remove();
              resolve();
              return;
            }
            const chunk = templates.slice(index, index + TEMPLATE_APPEND_CHUNK);
            body.insertAdjacentHTML("beforeend", chunk.map((t) => _templateRowHtml(t, sourceTypeIdToLabel)).join(""));
            index += chunk.length;
            bindLoad(body.parentElement);
            const more = el("templateResultsMore");
            if (more) more.innerHTML = index < templates.length ? `${_templateSpinner()}Loading ${templates.length - index} more...` : "";
            requestAnimationFrame(appendChunk);
          };
          requestAnimationFrame(appendChunk);
        });
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
        if (!businessResponse.ok) throw new Error(businessResult.error || "Could not load businesses.");
        businesses = businessResult.brands || [];
      } catch (error) {
        businesses = [];
      }
      templateBusinessNames = Object.fromEntries(businesses.map((business) => [business.business_id, business.name]));
      el("templateBusinessFilter").innerHTML = '<option value="">All businesses</option><option class="create-new-option" value="__create_new__">+ Create New Business</option>' + businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(business.name)}</option>`).join("");
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
      setStatus(`Loaded ${template.name}. Edit the field mapping, then Save to update the template.`, "ok");
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
