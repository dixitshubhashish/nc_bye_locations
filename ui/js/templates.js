// Template Library tab: browse, load, and save saved mapping templates.

async function loadTemplateLibrary() {
      const target = el("templateResults");
      const search = el("templateSearch").value.trim();
      const businessId = el("templateBusinessFilter").value;
      const sourceTypeId = el("templateSourceFilter").value;
      target.className = "status";
      target.textContent = "Loading...";
      try {
        const response = await fetch(`/api/templates?search=${encodeURIComponent(search)}&business_id=${encodeURIComponent(businessId)}&source_type_id=${encodeURIComponent(sourceTypeId)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load templates.");
        if (!result.templates.length) {
          target.textContent = "No templates found.";
          return;
        }
        target.className = "";
        target.innerHTML = `<table><thead><tr><th>Template</th><th>Business</th><th>Created</th><th>Updated</th><th>Action</th></tr></thead><tbody>${result.templates.map((template) => `<tr><td>${escapeHtml(template.name)}</td><td>${escapeHtml(template.business_id)}</td><td>${escapeHtml(template.created_at)}</td><td>${escapeHtml(template.updated_at)}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Load</button></td></tr>`).join("")}</tbody></table>`;
        target.querySelectorAll("button[data-load-template]").forEach((button) => button.addEventListener("click", () => loadTemplateIntoEditor(result.templates.find((template) => template.workflow_template_id === button.dataset.loadTemplate))));
      } catch (error) {
        target.className = "status error";
        target.textContent = productSafeError(error.message, "Could not load templates.");
      }
    }
async function loadTemplateFilters() {
      let businesses = [];
      try {
        const businessResponse = await fetch("/api/brands?search=");
        const businessResult = await businessResponse.json();
        if (!businessResponse.ok) throw new Error(businessResult.error || "Could not load businesses.");
        businesses = businessResult.brands || [];
      } catch (error) {
        businesses = [];
      }
      el("templateBusinessFilter").innerHTML = '<option value="">All businesses</option><option class="create-new-option" value="__create_new__">+ Create New Business</option>' + businesses.map((business) => `<option value="${escapeHtml(business.business_id)}">${escapeHtml(business.name)}</option>`).join("");
      try {
        const sourceResponse = await fetch("/api/source-types");
        const sourceResult = await sourceResponse.json();
        if (!sourceResponse.ok) throw new Error(sourceResult.error || "Could not load source types.");
        sourceTypes = sourceResult.source_types || [];
      } catch (error) {
        sourceTypes = [];
      }
      el("templateSourceFilter").innerHTML = '<option value="">All source types</option>' + sourceTypes.map((source) => `<option value="${escapeHtml(source.source_type_id)}">${escapeHtml(source.name)}</option>`).join("");
      populateSourceTypeSelects();
    }
function loadTemplateIntoEditor(template) {
      const components = template.components?.mapper || template.components || {};
      const brands = JSON.parse(el("brandSelect").dataset.brands || "[]");
      selectedBrand = brands.find((brand) => brand.business_id === template.business_id) || { business_id: template.business_id, name: components.brand || "", source_type_id: template.source_type_id };
      activeTemplateId = template.workflow_template_id;
      const brandOption = document.querySelector(`#brandSelect option[value="${CSS.escape(template.business_id)}"]`);
      if (brandOption) el("brandSelect").value = template.business_id;
      applyBusinessSourceType(selectedBrand);
      el("sourceName").value = components.source_name || template.name || "";
      mappingSelections = { ...(components.fields || {}) };
      optionalMappingKeys = new Set(Object.keys(mappingSelections).filter((key) => !primaryMappingKeys.has(key)));
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set();
      renderMappings();
      switchView("mapperView");
      setStatus(`Loaded ${template.name}. Edit the fields, then save the updated template.`, "ok");
    }
async function saveEditedTemplate() {
      const response = await fetch("/api/templates/save", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ workflow_template_id: activeTemplateId, components: { mapper: getMapper() } }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not update template.");
      setStatus("Template saved.", "ok");
    }

