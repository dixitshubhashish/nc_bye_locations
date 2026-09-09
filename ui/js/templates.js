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
// it can stomp the other call's already-rendered table with "Loading"
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
      return `<tr><td data-sort-value="${escapeHtml(template.name)}">${escapeHtml(template.name)}</td><td data-sort-value="${escapeHtml(templateBrandNames[template.business_id] || template.business_id)}">${escapeHtml(templateBrandNames[template.business_id] || template.business_id)}</td><td data-sort-value="${escapeHtml(label)}">${escapeHtml(label)}</td><td data-sort-value="${escapeHtml(template.created_at)}">${escapeHtml(formatTimestamp(template.created_at))}</td><td data-sort-value="${escapeHtml(template.updated_at)}">${escapeHtml(formatTimestamp(template.updated_at))}</td><td><button type="button" data-load-template="${escapeHtml(template.workflow_template_id)}">Review</button></td></tr>`;
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
      const now = Date.now();
      for (const [key, entry] of templatePageCache) {
        if (now - entry.createdAt >= TEMPLATE_CACHE_TTL_MS) templatePageCache.delete(key);
      }
      templatePageCache.set(cacheKey, { createdAt: now, templates });
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
          // loadTemplateIntoEditor() is synchronous, but nothing ever
          // restored this button afterward - it was left permanently
          // stuck reading "Reviewing" (disabled) even after navigating back
          // to this tab later. Restore it once done - re-opening the same
          // template again is harmless and lets the user re-check the
          // mapping - instead of leaving it in a busy state forever.
          const previousHtml = setButtonBusy(button, "Reviewing");
          loadTemplateIntoEditor(templatePaging.byId[button.dataset.loadTemplate]);
          clearButtonBusy(button, previousHtml);
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
      target.innerHTML = `${_templateSpinner()}Loading templates`;
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
// Lock/unlock the business pickers while a saved template is being edited.
function setTemplateEditBrandLock(locked, businessId = "", brandLabel = "") {
      ["brandSelect", "parserBusinessSelect", "preParseBrandSelect"].forEach((id) => {
        const node = el(id);
        if (!node) return;
        node.disabled = Boolean(locked);
        node.title = locked ? "This template belongs to this brand and cannot be re-pointed here." : "";
        // A locked picker must SHOW the brand, not the "Select an existing
        // brand" placeholder. The option can be genuinely absent (this select
        // hides duplicate brands, and the template may point at a hidden
        // copy), so add it rather than leave the field looking unset.
        if (locked && businessId) {
          let option = node.querySelector(`option[value="${CSS.escape(businessId)}"]`);
          if (!option) {
            option = document.createElement("option");
            option.value = businessId;
            option.textContent = brandLabel || businessId;
            node.appendChild(option);
          }
          node.value = businessId;
        }
      });
      el("editExistingBrandLink")?.classList.toggle("hidden", Boolean(locked));
    }

function loadTemplateIntoEditor(template) {
      const components = template.components?.mapper || template.components || {};
      const brands = JSON.parse(el("brandSelect").dataset.brands || "[]");
      selectedBrand = brands.find((brand) => brand.business_id === template.business_id) || { business_id: template.business_id, name: components.brand || "", source_type_id: template.source_type_id };
      activeTemplateId = template.workflow_template_id;
      // syncPreParseWorkspace() (mapper.js) relocates #newBrandFields between
      // panels when toggling pre-parse vs. mapping mode, but only ever
      // toggles the surrounding panel's hidden state - if the brand-create
      // form was left open (unhidden) from an earlier edit on this same
      // page load, it rides along still-visible and pops up here even
      // though nothing on this path ever asked to open it. A template
      // never needs that form, so force it closed unconditionally.
      brandEditMode = false;
      presetCreateMode = false;
      el("newBrandFields")?.classList.add("hidden");
      // Editing a saved template - no source to pick/upload/parse here, so
      // hide the source-parser half of the left rail (see
      // #mapperView.template-edit-mode .source-parser-only). Cleared again
      // wherever templateEditMode goes back to false.
      el("mapperView")?.classList.add("template-edit-mode");
      // The template's brand must be VISIBLE in the locked select, not the
      // "Select an existing brand" placeholder. Its option can legitimately
      // be absent - the dropdown hides duplicate brands, and the template may
      // point at one of the hidden copies - so inject it when missing rather
      // than leaving the field looking empty for a template that definitely
      // has a brand.
      const brandSelect = el("brandSelect");
      if (brandSelect) {
        let brandOption = brandSelect.querySelector(`option[value="${CSS.escape(template.business_id)}"]`);
        if (!brandOption) {
          brandOption = document.createElement("option");
          brandOption.value = template.business_id;
          brandOption.textContent = formatBrandName(
            selectedBrand?.name || components.brand || template.business_id);
          brandSelect.appendChild(brandOption);
        }
        brandSelect.value = template.business_id;
      }
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
      // Opening a saved template to look at it is NOT unsaved work. This flag
      // survives from any earlier parse in the same session, so navigating
      // away after merely viewing a template raised "Save before you leave?"
      // over a template the user had not touched. It is set again below only
      // when a mapping is actually changed.
      pendingUnsavedParse = false;
      optionalMappingKeys = new Set(Object.keys(mappingSelections).filter((key) => !primaryMappingKeys.has(key)));
      hiddenMappingKeys = new Set();
      autoMappedKeys = new Set();
      renderMappings();
      renderTemplateEditSourcePreview();
      // A saved template is bound to its business_id in the backend (a
      // template cannot exist without one), so the brand is a fact of THIS
      // template, not a choice - changing it here would silently re-point
      // the template at a different business. Locked while editing; released
      // by exitTemplateEditMode().
      setTemplateEditBrandLock(true, template.business_id,
        formatBrandName(selectedBrand?.name || components.brand || template.business_id));
      switchView("mapperView");
      // The raw template name is an internal slug ("spice_route_csv_csv_sample")
      // - it means nothing to the reader and the mapping is on screen anyway.
      setStatus("Edit the field mapping, then click Save Template to update.", "ok");
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
      const chips = `<div style="display:flex; flex-wrap:wrap; gap:6px;">${sourceFields.map((field) => `<span style="display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; border:1px solid var(--line); background:${mapped.has(field) ? "#e6f4f1" : "#f5f5f5"}; color:${mapped.has(field) ? "#0f6d63" : "#555"};">${escapeHtml(field)}${mapped.has(field) ? " ✓" : ""}</span>`).join("")}</div>`;
      target.innerHTML = `<div id="templateSampleRecords" style="margin-bottom:12px;"><div class="status">${busyMarkup("Loading saved records for this template")}</div></div>
        <div style="font-size:12px; color: var(--muted); margin-bottom:8px;">${sourceFields.length} stored source column${sourceFields.length === 1 ? "" : "s"} in this template</div>${chips}`;
      loadTemplateSampleRecords();
    }
// The template editor used to show only column NAMES ("no live data rows"),
// which is not enough to judge whether a mapping is right. The rows this
// template already produced are in `listings` keyed by template_id (+
// business_id), so show real examples instead of asking for a re-parse.
async function loadTemplateSampleRecords() {
      const host = el("templateSampleRecords");
      if (!host || !activeTemplateId) return;
      try {
        const query = new URLSearchParams({ template_id: activeTemplateId, limit: "10" });
        if (selectedBrand?.business_id) query.set("business_id", selectedBrand.business_id);
        const response = await fetch(`/api/templates/sample-records?${query}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load sample records.");
        const records = result.records || [];
        if (!records.length) {
          host.innerHTML = `<div class="status">No records saved under this template yet. Parse a source file to bring in records.</div>`;
          return;
        }
        // Only columns that actually carry a value in this sample - a table
        // of empty columns is worse than a narrower, honest one.
        const allKeys = Array.from(new Set(records.flatMap((row) => Object.keys(row))));
        const columns = allKeys.filter((key) => records.some((row) => row[key] !== null && row[key] !== undefined && row[key] !== ""));
        // Source columns with no mapped home yet. These are the ones the user
        // came here to map, so they lead the table and are marked - showing
        // only the already-mapped columns made the preview useless for the
        // one job the template editor exists to do.
        const unmapped = new Set(result.unmapped_columns || []);
        columns.sort((a, b) => (unmapped.has(b) ? 1 : 0) - (unmapped.has(a) ? 1 : 0));
        // Say which rows these are. When the template's own id matched
        // nothing we fall back to the brand's rows, and claiming the template
        // produced them would be untrue.
        const provenance = result.matched_by === "business"
          ? `Showing ${records.length} record${records.length === 1 ? "" : "s"} saved for this brand - use them to check the mapping.`
          : `Showing ${records.length} record${records.length === 1 ? "" : "s"} already saved under this template.`;
        host.innerHTML = `
          <div style="font-size:12px; color: var(--muted); margin-bottom:6px;">${provenance}</div>
          ${unmapped.size ? `<div style="font-size:12px; margin-bottom:6px; color:#8a5a00;">${unmapped.size} column${unmapped.size === 1 ? "" : "s"} in this data ${unmapped.size === 1 ? "is" : "are"} not mapped yet - marked below, and available in the mapping list on the left.</div>` : ""}
          <div style="overflow-x:auto;"><table><thead><tr>${columns.map((c) => `<th${unmapped.has(c) ? ' style="background:#fff8e6; color:#8a5a00;" title="Not mapped yet"' : ""}>${escapeHtml(formatFieldLabel ? formatFieldLabel(c) : c)}${unmapped.has(c) ? " *" : ""}</th>`).join("")}</tr></thead>
          <tbody>${records.map((row) => `<tr>${columns.map((c) => `<td>${escapeHtml(row[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      } catch (error) {
        host.innerHTML = `<div class="status">${escapeHtml(productSafeError(error.message, "Could not load saved records for this template."))}</div>`;
      }
    }
async function saveEditedTemplate() {
      const response = await fetch("/api/templates/save", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ workflow_template_id: activeTemplateId, components: { mapper: getMapper() } }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not update template.");
      setStatus("Template saved.", "ok");
    }
