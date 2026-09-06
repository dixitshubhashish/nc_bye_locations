/**
 * Modular UI Subpackage Component Loader.
 * 
 * Asynchronously fetches HTML partials from domain subpackages (`common`, `auth`,
 * `mapping`, `review`, `templates`, `reporting`, `system`) and injects them into
 * the root SPA document (`index.html`), then initializes app event bindings.
 */

async function loadUiModules() {
  const modules = [
    { containerId: "commonModuleContainer", url: "common/common.html" },
    { containerId: "headerContainer", url: "common/header.html" },
    { containerId: "footerContainer", url: "common/footer.html" },
    { containerId: "authModuleContainer", url: "auth/auth.html" },
    { containerId: "mappingModuleContainer", url: "mapping/mapping.html" },
    { containerId: "reportingModuleContainer", url: "reporting/reporting.html" },
    { containerId: "reviewModuleContainer", url: "review/review.html" },
    { containerId: "templatesModuleContainer", url: "templates/templates.html" },
    { containerId: "systemModuleContainer", url: "system/system.html" },
  ];

  try {
    await Promise.all(
      modules.map(async (mod) => {
        const response = await fetch(mod.url);
        if (!response.ok) {
          throw new Error(`Failed to load module partial: ${mod.url} (status ${response.status})`);
        }
        const html = await response.text();
        const container = document.getElementById(mod.containerId);
        if (container) {
          container.innerHTML = html;
        }
      })
    );

    // Initialize application events and state after all HTML partials enter DOM
    initAppEvents();
  } catch (error) {
    console.error("UI Module Initialization Error:", error);
  }
}

function initAppEvents() {
  el("parseBtn")?.addEventListener("click", parseSource);
  el("testReadinessBtn")?.addEventListener("click", testReadiness);
  el("showExistingBrandsBtn")?.addEventListener("click", toggleShowExistingBrands);
  el("clearDemoDataBtn")?.addEventListener("click", clearSavedData);
  el("runPythonConnectorBtn")?.addEventListener("click", parseSource);
  el("expandPythonConnectorBtn")?.addEventListener("click", openConnectorEditor);
  el("minimizePythonConnectorBtn")?.addEventListener("click", minimizeConnectorEditor);
  el("loginBtn")?.addEventListener("click", login);
  el("loginPassword")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") login();
  });
  el("addQueryParamBtn")?.addEventListener("click", () => addPairRow("queryParams", "zip", "10001"));
  el("addHeaderBtn")?.addEventListener("click", () => addPairRow("customHeaders", "x-client-id", "value"));
  el("authType")?.addEventListener("change", updateAuthVisibility);
  el("saveBtn")?.addEventListener("click", saveMapper);
  el("resetMappingBtn")?.addEventListener("click", resetMapping);
  el("restartMappingBtn")?.addEventListener("click", restartMapping);
  el("clearDataBtn")?.addEventListener("click", clearSavedData);
  el("reportingDataRefreshBtn")?.addEventListener("click", refreshReportingData);
  el("logoutBtn")?.addEventListener("click", logout);
  el("confirmClearBtn")?.addEventListener("click", async () => {
    el("dangerDialog")?.close();
    await performClearSavedData();
  });
  el("cancelClearBtn")?.addEventListener("click", () => el("dangerDialog")?.close());
  el("masterDeleteCredentialNextBtn")?.addEventListener("click", () => { if (typeof proceedMasterDeleteConfirmation === "function") proceedMasterDeleteConfirmation(); });
  el("confirmMasterDeleteBtn")?.addEventListener("click", () => { if (typeof performMasterDeleteData === "function") performMasterDeleteData(); });
  el("cancelMasterDeleteBtn")?.addEventListener("click", () => el("masterDeleteConfirmDialog")?.close());
  el("cancelMasterDeleteCredentialsBtn")?.addEventListener("click", () => el("masterDeleteCredentialsDialog")?.close());
  el("reviewSearchBtn")?.addEventListener("click", loadRejectedRecords);
  el("templateSearchBtn")?.addEventListener("click", loadTemplateLibrary);
  el("templateSearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadTemplateLibrary();
  });
  el("addCustomFieldBtn")?.addEventListener("click", addCustomField);
  el("dropCustomFieldBtn")?.addEventListener("click", dropCustomField);
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  el("addOptionalFieldBtn")?.addEventListener("click", () => {
    const key = el("optionalFieldSelect").value;
    if (!key) return;
    if (primaryMappingKeys.has(key)) hiddenMappingKeys.delete(key);
    else optionalMappingKeys.add(key);
    renderMappings();
    updateOutput();
  });
  el("copyBtn")?.addEventListener("click", async () => {
    const feedback = el("copyFeedback");
    try {
      await navigator.clipboard.writeText(el("mapperOutput").value);
      feedback.className = "action-feedback ok";
      feedback.textContent = "Template copied.";
    } catch (error) {
      feedback.className = "action-feedback error";
      feedback.textContent = "Could not copy template.";
    }
  });
  el("resetBtn")?.addEventListener("click", () => location.reload());
  el("brandSelect")?.addEventListener("change", (event) => {
    resetTemplateSelection();
    if (event.target.value === "__create_new__") {
      selectedBrand = null;
      el("sourceType").disabled = false;
      resetSourceInputsForNewMode(el("sourceType").value);
      setNewBusinessSourceType(el("sourceType").value);
      el("templateBusinessFilter").value = "";
      el("templateSourceFilter").value = "";
      el("newBrandFields").classList.remove("hidden");
      updateOutput();
      updateDropCustomFieldPicker();
      return;
    }
    const brands = JSON.parse(event.target.dataset.brands || "[]");
    selectedBrand = brands.find((brand) => brand.business_id === event.target.value) || null;
    el("newBrandFields").classList.add("hidden");
    if (selectedBrand) applyBusinessSourceType(selectedBrand);
    else {
      el("sourceType").disabled = false;
      el("templateBusinessFilter").value = "";
      el("templateSourceFilter").value = "";
    }
    refreshReviewCount();
    refreshTemplatesForBusiness();
    updateOutput();
    updateDropCustomFieldPicker();
  });
  el("createBrandBtn")?.addEventListener("click", () => createNewBrand());
  el("newBrandName")?.addEventListener("input", updateOutput);
  el("sourceName")?.addEventListener("input", updateOutput);
  el("fileInput")?.addEventListener("change", () => {
    sourceParsed = false;
    setStatus("Source changed. Ready to review fields.", "");
    loadExcelSheets();
  });
  el("sheetName")?.addEventListener("change", () => {
    el("recordPath").value = el("sheetName").value;
  });
  el("sourceType")?.addEventListener("change", () => {
    const nextSourceType = el("sourceType").value;
    if (el("sourceType").value !== "csv") {
      const newCsvOption = document.querySelector("input[name='csvFunction'][value='new']");
      if (newCsvOption) newCsvOption.checked = true;
      csvFunctionMode = "new";
    } else {
      const newCsvOption = document.querySelector("input[name='csvFunction'][value='new']");
      if (newCsvOption) newCsvOption.checked = true;
      csvFunctionMode = "new";
    }
    if (el("sourceType").value !== "json") {
      const newJsonOption = document.querySelector("input[name='jsonFunction'][value='new']");
      if (newJsonOption) newJsonOption.checked = true;
      jsonFunctionMode = "new";
    } else {
      const newJsonOption = document.querySelector("input[name='jsonFunction'][value='new']");
      if (newJsonOption) newJsonOption.checked = true;
      jsonFunctionMode = "new";
    }
    if (el("sourceType").value !== "api_get_json") {
      const newApiOption = document.querySelector("input[name='apiFunction'][value='new']");
      if (newApiOption) newApiOption.checked = true;
      apiFunctionMode = "new";
    } else {
      const newApiOption = document.querySelector("input[name='apiFunction'][value='new']");
      if (newApiOption) newApiOption.checked = true;
      apiFunctionMode = "new";
    }
    if (el("sourceType").value !== "python_editor") {
      const newPythonOption = document.querySelector("input[name='pythonFunction'][value='new']");
      if (newPythonOption) newPythonOption.checked = true;
      setDominosLocked(false);
    }
    resetSourceInputsForNewMode(nextSourceType);
    setStatus("Source changed. Ready to review fields.", "");
    el("fileInput").value = "";
    updateSourceVisibility();
    if (!selectedBrand) {
      el("templateSourceFilter").value = currentSourceTypeId();
      resetTemplateSelection();
      loadTemplateLibrary();
    }
  });
  el("newBrandSourceType")?.addEventListener("change", () => {
    const option = el("newBrandSourceType").selectedOptions[0];
    const format = option?.dataset.format || sourceTypeNameToFormat(option?.textContent || "");
    if (format) {
      el("sourceType").value = format;
      resetSourceInputsForNewMode(format);
      el("templateSourceFilter").value = el("newBrandSourceType").value;
      updateSourceVisibility();
      refreshTemplatesForBusiness();
    }
  });
  el("sourceInputMode")?.addEventListener("change", () => {
    if (el("sourceInputMode").value === "url" && isNewSourceMode()) {
      setSourceUrlLocked(false);
      el("sourceUrl").value = "";
      el("sourceUrl").placeholder = sourceUrlPlaceholders[el("sourceType").value] || "https://example.com/locations.json";
    }
    updateSourceVisibility();
  });
  document.querySelectorAll("input[name='csvFunction']").forEach((input) => {
    input.addEventListener("change", () => updateCsvFunctionSelection(input.value));
  });
  document.querySelectorAll("input[name='jsonFunction']").forEach((input) => {
    input.addEventListener("change", () => updateJsonFunctionSelection(input.value));
  });
  document.querySelectorAll("input[name='pythonFunction']").forEach((input) => {
    input.addEventListener("change", () => updatePythonFunctionSelection(input.value));
  });
  document.querySelectorAll("input[name='apiFunction']").forEach((input) => {
    input.addEventListener("change", () => updateApiFunctionSelection(input.value));
  });
  el("templateBusinessFilter")?.addEventListener("change", () => {
    if (el("templateBusinessFilter").value === "__create_new__") {
      el("brandSelect").value = "__create_new__";
      el("brandSelect").dispatchEvent(new Event("change"));
      return;
    }
    loadTemplateLibrary();
  });
  el("templateSourceFilter")?.addEventListener("change", loadTemplateLibrary);
  el("jsonRecordPath")?.addEventListener("change", () => {
    el("recordPath").value = el("jsonRecordPath").value;
    parseSource();
  });
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      button.classList.add("active");
      ["sourcePreview", "entityPreview"].forEach((id) => el(id)?.classList.toggle("hidden", id !== button.dataset.tab));
    });
  });
  addPairRow("queryParams", "limit", "500");
  addPairRow("customHeaders", "Accept", "application/json");
  initializeConnectorEditor();

  const fallbackBirdeyeDarkSvg = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60"><rect width="240" height="60" fill="none"/><g transform="translate(10, 10)"><path d="M 6 22 C 6 8 18 3 24 3 C 30 3 42 8 42 22 C 42 36 30 41 24 41 C 18 41 6 36 6 22 Z" fill="#0b70f0"/><ellipse cx="24" cy="22" rx="10" ry="10" fill="#ffffff"/><circle cx="24" cy="22" r="5" fill="#1d2b4f"/><path d="M 2 22 C 14 36 34 36 46 22 C 34 8 14 8 2 22 Z" fill="none" stroke="#0b70f0" stroke-width="3" stroke-linecap="round"/><text x="56" y="31" font-family="system-ui, -apple-system, sans-serif" font-weight="800" font-size="28" fill="#1d2b4f">Birdeye</text></g></svg>`);
  const fallbackBirdeyeLightSvg = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60"><rect width="240" height="60" fill="none"/><g transform="translate(10, 10)"><path d="M 6 22 C 6 8 18 3 24 3 C 30 3 42 8 42 22 C 42 36 30 41 24 41 C 18 41 6 36 6 22 Z" fill="#ffffff"/><ellipse cx="24" cy="22" rx="10" ry="10" fill="#0b70f0"/><circle cx="24" cy="22" r="5" fill="#ffffff"/><path d="M 2 22 C 14 36 34 36 46 22 C 34 8 14 8 2 22 Z" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round"/><text x="56" y="31" font-family="system-ui, -apple-system, sans-serif" font-weight="800" font-size="28" fill="#ffffff">Birdeye</text></g></svg>`);
  document.querySelectorAll("[data-logo-src]").forEach((image) => {
    const isLightTarget = image.dataset.logoSrc === "birdeyeLogoLightUrl";
    const defaultFallback = isLightTarget ? fallbackBirdeyeLightSvg : fallbackBirdeyeDarkSvg;
    const srcUrl = window.APP_CONSTANTS ? (window.APP_CONSTANTS[image.dataset.logoSrc] || window.APP_CONSTANTS.birdeyeLogoUrl) : null;
    image.onerror = () => {
      image.onerror = null;
      image.src = defaultFallback;
    };
    image.src = srcUrl || defaultFallback;
  });
  const jsonLink = document.querySelector("[data-json-viewer-link]");
  if (jsonLink && window.APP_CONSTANTS) {
    jsonLink.href = window.APP_CONSTANTS.jsonViewerUrl;
    jsonLink.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(el("mapperOutput")?.value || "{}");
        if (typeof setStatus === "function") setStatus("Template copied.", "ok");
      } catch (error) {
        if (typeof setStatus === "function") setStatus("Viewer opened.", "warn");
      }
    });
  }
  const disclaimerEl = document.querySelector("#brandDisclaimer");
  if (disclaimerEl && window.APP_CONSTANTS) {
    disclaimerEl.textContent = window.APP_CONSTANTS.trademarkDisclaimer;
  }
  if (typeof window.initAuthEvents === "function") window.initAuthEvents();
  if (typeof updateSourceVisibility === "function") updateSourceVisibility();
  if (typeof resetLoginSessionFromLaunch === "function") resetLoginSessionFromLaunch();
  if (typeof restoreRememberedLogin === "function") restoreRememberedLogin();
  setTimeout(() => {
    if (typeof prepareReferenceData === "function") prepareReferenceData();
  }, 10);
  if (sessionStorage.getItem("competitive_whitespace_login_session") === "true") {
    if (typeof loadAppData === "function") loadAppData();
  }
  const urlParams = new URLSearchParams(window.location.search);
  const activeTab = urlParams.get("view") || sessionStorage.getItem("activeTab") || "mapperView";
  if (typeof switchView === "function") switchView(activeTab || "mapperView");
}

document.addEventListener("DOMContentLoaded", loadUiModules);

