/**
 * @file reporting.wiring.js
 * @summary DOM event wiring and one-time initialization for the Reporting tab.
 *
 * @description
 * Attaches click/change/keydown handlers to reporting controls with defensive DOM checks
 * and runs reporting setup initializers safely after partial HTML injection.
 */
(() => {
  function initReportingWiring() {
    // --- Report refresh -------------------------------------------------------
    el("refreshReportBtn")?.addEventListener("click", () => {
      if (typeof reportLoaded !== "undefined") reportLoaded = false;
      if (typeof loadReporting === "function") loadReporting();
    });

    // --- Sample dataset -------------------------------------------------------
    el("loadSampleDatasetBtn")?.addEventListener("click", () => {
      if (typeof loadSampleDataset === "function") loadSampleDataset(false);
    });
    el("reloadSampleDatasetLink")?.addEventListener("click", () => {
      if (typeof loadSampleDataset === "function") loadSampleDataset(true);
    });

    // --- Filter apply / reset -------------------------------------------------
    el("applyReportFiltersBtn")?.addEventListener("click", () => {
      if (typeof reportLoaded !== "undefined") reportLoaded = false;
      if (typeof loadReporting === "function") loadReporting();
    });

    el("resetReportFiltersBtn")?.addEventListener("click", () => {
      if (el("reportStateFilter")) el("reportStateFilter").value = "";
      if (el("reportCountyFilter")) el("reportCountyFilter").value = "";
      if (el("reportCityFilter")) el("reportCityFilter").value = "";
      if (el("reportZipFilter")) el("reportZipFilter").value = "";
      if (typeof reportLoaded !== "undefined") reportLoaded = false;
      if (typeof loadReporting === "function") loadReporting();
    });

    // --- Cascading geography filters -----------------------------------------
    el("reportStateFilter")?.addEventListener("change", async () => {
      if (el("reportCountyFilter")) el("reportCountyFilter").value = "";
      if (el("reportCityFilter")) el("reportCityFilter").value = "";
      if (el("reportZipFilter")) el("reportZipFilter").value = "";
      if (typeof loadGeoOptions === "function") await loadGeoOptions();
      if (typeof reportLoaded !== "undefined") reportLoaded = false;
      if (typeof loadReporting === "function") loadReporting();
    });

    el("reportCountyFilter")?.addEventListener("change", async () => {
      if (el("reportCityFilter")) el("reportCityFilter").value = "";
      if (el("reportZipFilter")) el("reportZipFilter").value = "";
      if (typeof loadGeoOptions === "function") await loadGeoOptions();
      if (typeof reportLoaded !== "undefined") reportLoaded = false;
      if (typeof loadReporting === "function") loadReporting();
    });

    ["reportCityFilter", "reportZipFilter"].forEach((id) => {
      el(id)?.addEventListener("change", () => {
        if (typeof reportLoaded !== "undefined") reportLoaded = false;
        if (typeof loadReporting === "function") loadReporting();
      });
      el(id)?.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          if (typeof reportLoaded !== "undefined") reportLoaded = false;
          if (typeof loadReporting === "function") loadReporting();
        }
      });
    });

    // --- One-time reporting initializers ------------------------------------
    if (typeof setupZipTypeahead === "function") setupZipTypeahead();
    if (typeof setupBrandDropdownListeners === "function") setupBrandDropdownListeners();
    if (typeof refreshSampleDatasetStatus === "function") refreshSampleDatasetStatus();
    if (typeof loadGeoOptions === "function") loadGeoOptions();
  }

  window.initReportingWiring = initReportingWiring;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initReportingWiring);
  } else {
    initReportingWiring();
  }
})();
