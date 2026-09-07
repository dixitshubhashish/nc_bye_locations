// Shared/common utilities used across all tabs: DOM helpers, formatting,
// loading overlays, status messaging, login/session bootstrap.

let appDataLoaded = false;
let appReady = false;
let readinessCheckInFlight = null;
const loginReadinessTimeoutMs = 2500;

let sourceTypes = [];

// Canonical human-readable labels for internal source_type keys, matching
// the #sourceType select in the Mappings tab - reused wherever a source
// type needs to be displayed (e.g. the Template Library table/filter)
// instead of showing the raw code name.
const SOURCE_TYPE_LABELS = {
  csv: "CSV",
  excel: "EXCEL (.XLSX)",
  api_get_json: "GET API JSON",
  json: "JSON",
  python_editor: "PYTHON EDITOR",
  xml: "XML",
};
function sourceTypeLabel(sourceTypeKey) {
      return SOURCE_TYPE_LABELS[sourceTypeKey] || String(sourceTypeKey || "Unknown");
    }

const loginSessionStorageKey = "competitive_whitespace_login_session";
const mappingSessionStorageKey = "competitive_whitespace_mapping_session";
const serverLaunchStorageKey = "competitive_whitespace_server_launch";
const el = (id) => document.getElementById(id);

// Keep expired sessions and missing app routes from leaving the shell in a
// partially rendered state. Login/session probes must be allowed to report
// their own errors without redirecting recursively.
if (!window.__authResponseGuardInstalled) {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const requestUrl = String(args[0]?.url || args[0] || "");
    const isAuthProbe = requestUrl.includes("/api/login") || requestUrl.includes("/api/session");
    if ([401, 403, 404].includes(response.status) && !isAuthProbe && !window.location.pathname.endsWith("/login")) {
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
      window.location.replace("/login");
    }
    return response;
  };
  window.__authResponseGuardInstalled = true;
}
function newSessionId() {
      return window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }
function productSafeError(message, fallback = "Something went wrong. Please try again.") {
      const text = String(message || "");
      const sensitiveTerms = ["big" + "query", "data" + "set", "project" + "_id", "data" + "set_id", "credentials", "service" + " account", "google", "s" + "ql", "ware" + "house", "bron" + "ze", "sil" + "ver", "table", "module named"];
      if (sensitiveTerms.some((term) => text.toLowerCase().includes(term))) {
        return fallback;
      }
      return text || fallback;
    }

function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString() : "0";
    }
function formatBrandName(value) {
      return String(value ?? "").trim().replace(/_/g, " ").replace(/[^A-Za-z0-9\s#'\-.]/g, "").replace(/\s+/g, " ").replace(/[A-Za-z][^\s-]*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
    }
function renderSimpleTable(targetId, columns, rows) {
      const target = el(targetId);
      const visibleRows = rows.length ? rows : [Object.fromEntries(columns.map((column) => {
        const label = String(column.label || column.key || "").toLowerCase();
        const value = /count|number|store|location|state|city|zip|population|income|age|share|covered/.test(label) ? 0 : "";
        return [column.key, value];
      }))];
      if (!rows.length) {
        target.innerHTML = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${visibleRows.map((row) => `<tr>${columns.map((column) => {
          if (column.key === "pct") return '<td>0%</td>';
          const value = column.format ? column.format(row[column.key], row) : row[column.key];
          return `<td>${column.html ? value : escapeHtml(value)}</td>`;
        }).join("")}</tr>`).join("")}</tbody></table>`;
        return;
      }
      target.innerHTML = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${visibleRows.map((row) => `<tr>${columns.map((column) => {
        const value = column.format ? column.format(row[column.key], row) : row[column.key];
        return `<td>${column.html ? value : escapeHtml(value)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>`;
    }

function flattenObject(value, prefix = "", output = {}) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        Object.entries(value).forEach(([key, child]) => {
          const path = prefix ? `${prefix}.${key}` : key;
          flattenObject(child, path, output);
        });
      } else {
        output[prefix] = value;
      }
      return output;
    }
function getByPath(row, path) {
      if (!path) return "";
      return path.split(".").reduce((current, part) => {
        if (current && typeof current === "object" && part in current) return current[part];
        return "";
      }, row);
    }
function setStatus(message, type = "", options = {}) {
      const target = el("status");
      if (!target) return;
      target.className = `status ${type}`.trim();
      target.textContent = message;
      if (["warn", "warning", "error"].includes(String(type).toLowerCase())) {
        const close = document.createElement("button");
        close.type = "button";
        close.className = "status-close";
        close.setAttribute("aria-label", "Dismiss message");
        close.textContent = "×";
        close.addEventListener("click", () => {
          target.className = "status hidden";
          target.textContent = "";
        });
        target.appendChild(close);
        if (options.retry) {
          const retry = document.createElement("button");
          retry.type = "button";
          retry.className = "status-retry";
          retry.textContent = "Reload source";
          retry.addEventListener("click", () => {
            if (typeof window.parseSource === "function") window.parseSource();
          });
          target.insertBefore(retry, close);
        }
      }
    }

function addStatusClose(target) {
      if (!target || target.querySelector(".status-close")) return;
      const close = document.createElement("button");
      close.type = "button";
      close.className = "status-close";
      close.setAttribute("aria-label", "Dismiss message");
      close.textContent = "×";
      close.addEventListener("click", () => {
        target.className = "status hidden";
        target.textContent = "";
      });
      target.appendChild(close);
    }

function showLoadingOverlay(message, onCancel) {
      if (activeAbortController) {
        try { activeAbortController.abort(); } catch (_) {}
      }
      activeAbortController = new AbortController();
      el("loadingOverlayMessage").textContent = message || "Working...";
      el("loadingOverlaySub").textContent = "Processing records.";
      el("loadingOverlay").classList.remove("hidden");
      el("loadingCancelBtn").classList.toggle("hidden", typeof onCancel !== "function");
      el("loadingCancelBtn").onclick = () => {
        if (typeof onCancel !== "function") return;
        if (activeAbortController) {
          activeAbortController.abort();
          activeAbortController = null;
        }
        hideLoadingOverlay();
        if (typeof onCancel === "function") onCancel();
        setStatus("Cancelled. No changes.", "warn");
      };
    }
function updateLoadingOverlay(message, detail = "") {
      el("loadingOverlayMessage").textContent = message || "Working...";
      el("loadingOverlaySub").textContent = detail || "Processing records.";
    }
function hideLoadingOverlay() {
      el("loadingOverlay").classList.add("hidden");
      el("loadingCancelBtn").classList.remove("hidden");
      activeAbortController = null;
    }
function setProgress(percent, message) {
      const boundedPercent = Math.max(0, Math.min(100, percent));
      el("saveProgress").classList.remove("hidden");
      el("saveProgress").setAttribute("aria-busy", "true");
      el("progressFill").style.width = `${boundedPercent}%`;
      el("progressValue").textContent = `${boundedPercent}%`;
      el("progressMessage").textContent = message;
      showLoadingOverlay(`${message} (${boundedPercent}%)`);
    }
function hideProgress() {
      el("saveProgress").classList.add("hidden");
      el("saveProgress").setAttribute("aria-busy", "false");
      hideLoadingOverlay();
    }
function busyMarkup(label = "Loading") {
      const cleanLabel = String(label).replace(/\.\.\.+$/, "").trim();
      return `<span class="busy-label">${escapeHtml(cleanLabel)} <span class="inline-spinner"></span></span>`;
    }
function setButtonBusy(button, label = "Loading") {
      if (!button) return "";
      const previous = button.innerHTML;
      button.disabled = true;
      button.innerHTML = busyMarkup(label);
      return previous;
    }
function clearButtonBusy(button, previousHtml) {
      if (!button) return;
      button.disabled = false;
      if (previousHtml !== undefined) button.innerHTML = previousHtml;
    }

function switchView(viewId) {
      if (!viewId) viewId = "mapperView";
      try {
        sessionStorage.setItem("activeTab", viewId);
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set("view", viewId);
        const nextUrl = `${window.location.pathname}?${urlParams.toString()}`;
        history.replaceState(null, "", nextUrl);
      } catch (e) {}
      document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === viewId));
      ["mapperView", "reportingView", "reviewView", "templateLibraryView"].forEach((id) => el(id).classList.toggle("hidden", id !== viewId));
      el("appShell").querySelector("header").classList.toggle("reporting-active", viewId === "reportingView");
      if (el("restartMappingBtn")) el("restartMappingBtn").classList.toggle("hidden", viewId !== "mapperView");
      if (el("resetMappingBtn")) el("resetMappingBtn").classList.toggle("hidden", viewId !== "mapperView");
      if (viewId === "reportingView" && !reportLoaded) loadReporting();
      if (viewId === "templateLibraryView" && !templateLibraryLoaded) loadTemplateFilters().then(loadTemplateLibrary);
      if (viewId === "reviewView") {
        loadRejectedRecords();
        refreshReviewCount();
        if (typeof loadErrorBrandBreakdown === "function") loadErrorBrandBreakdown();
      }
    }

async function testReadiness() {
      const button = el("testReadinessBtn");
      const previousButton = setButtonBusy(button, "Testing Readiness");
      try {
        await refreshHeaderReadiness(true);
      } finally {
        clearButtonBusy(button, previousButton);
      }
    }
async function fetchReadinessPing() {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), loginReadinessTimeoutMs);
      try {
        return await fetch("/api/ping", { signal: controller.signal });
      } finally {
        clearTimeout(timeout);
      }
    }
function setHeaderReadiness(message, type = "") {
      const target = el("headerReadinessStatus");
      if (!target) return;
      target.className = `header-readiness ${type}`.trim();
      target.textContent = message;
    }
function setReadinessButtonDisabled(disabled) {
      const button = el("testReadinessBtn");
      if (!button) return;
      button.disabled = Boolean(disabled);
      button.title = disabled ? "ZIP reference data is already loaded." : "";
    }
function updateLoginButtonReferenceState() {
      const loginButton = el("loginBtn");
      if (!loginButton) return;
      loginButton.className = `reference-login-button ${appReady ? "ready" : "warn"}`;
      loginButton.disabled = false;
    }
async function refreshHeaderReadiness(force = false) {
      if (readinessCheckInFlight && !force) return readinessCheckInFlight;
      setHeaderReadiness("Checking ZIPs...", "warn");
      setReadinessButtonDisabled(true);
      readinessCheckInFlight = (async () => {
        try {
          const response = await fetch("/api/prepare");
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "ZIP setup needs attention.");
          appReady = true;
          updateLoginButtonReferenceState();
          setHeaderReadiness("ZIPs loaded", "ok");
          setReadinessButtonDisabled(true);
          return result;
        } catch (error) {
          appReady = false;
          updateLoginButtonReferenceState();
          setHeaderReadiness("ZIPs need attention", "error");
          setReadinessButtonDisabled(false);
          return null;
        } finally {
          readinessCheckInFlight = null;
        }
      })();
      return readinessCheckInFlight;
    }
async function runReadinessCheck(target) {
      if (!target) {
        await refreshHeaderReadiness(true);
        return;
      }
      target.className = "status";
      target.textContent = "Checking readiness...";
      try {
        const response = await fetchReadinessPing();
        const result = await response.json();
        if (!response.ok) throw new Error("Setup is still finishing.");
        appReady = true;
        updateLoginButtonReferenceState();
        target.className = "status ok";
        target.textContent = "Storage ready.";
      } catch (error) {
        appReady = false;
        updateLoginButtonReferenceState();
        target.className = "status error";
        target.textContent = "Setup is still finishing.";
        addStatusClose(target);
      }
    }

async function login() {
      const status = el("loginStatus");
      status.className = "status hidden";
      try {
        const response = await fetch("/api/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ username: el("loginUser").value.trim(), password: el("loginPassword").value })
        });
        const result = await response.json();
        if (!response.ok || !result.authenticated) throw new Error(result.error || "Invalid username or password.");
        if (el("rememberLogin").checked) localStorage.setItem("mapper_login_remembered", "true");
        else localStorage.removeItem("mapper_login_remembered");
        sessionStorage.setItem(loginSessionStorageKey, "true");
        sessionStorage.setItem(mappingSessionStorageKey, newSessionId());
        sessionStorage.removeItem(draftStorageKey);

        const urlParams = new URLSearchParams(window.location.search);
        const nextUrl = urlParams.size > 0 ? `/app?${urlParams.toString()}` : "/app";
        window.location.replace(nextUrl);
      } catch (error) {
        status.className = "status error";
        status.textContent = productSafeError(error.message, "Invalid username or password.");
      }
    }
async function loadAppData() {
      if (appDataLoaded) return;
      appDataLoaded = true;
      await Promise.allSettled([loadFieldRegistry(), loadBrands(), loadTemplateFilters()]);
      // Template records are intentionally fetched only after authentication
      // and app initialization, so the library tab opens instantly later.
      if (typeof loadTemplateLibrary === "function") await loadTemplateLibrary();
}

function enableSortableTable(table) {
  if (!table) return;
  table.querySelectorAll("th[data-sort-key]").forEach((header) => {
    if (header.dataset.sortBound === "true") return;
    header.dataset.sortBound = "true";
    header.classList.add("sortable-header");
    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-sort", "none");
    const indicator = document.createElement("span");
    indicator.className = "sort-indicator";
    indicator.textContent = "↕";
    header.appendChild(indicator);
    const sort = () => {
      const ascending = header.dataset.sortDirection !== "asc";
      table.querySelectorAll("th[data-sort-key]").forEach((item) => {
        item.dataset.sortDirection = "";
        item.setAttribute("aria-sort", "none");
        const icon = item.querySelector(".sort-indicator");
        if (icon) icon.textContent = "↕";
      });
      header.dataset.sortDirection = ascending ? "asc" : "desc";
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      indicator.textContent = ascending ? "↑" : "↓";
      const rows = [...table.querySelectorAll("tbody tr")];
      const column = header.cellIndex;
      rows.sort((left, right) => {
        const a = left.cells[column]?.dataset.sortValue ?? left.cells[column]?.textContent.trim() ?? "";
        const b = right.cells[column]?.dataset.sortValue ?? right.cells[column]?.textContent.trim() ?? "";
        const numeric = header.dataset.sortType === "number";
        const comparison = numeric ? Number(a) - Number(b) : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
        return (ascending ? 1 : -1) * comparison;
      });
      const body = table.querySelector("tbody");
      rows.forEach((row) => body.appendChild(row));
    };
    header.addEventListener("click", sort);
    header.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); }
    });
  });
}
function restoreRememberedLogin() {
      const remembered = localStorage.getItem("mapper_login_remembered") === "true";
      el("rememberLogin").checked = remembered;
    }
async function resetLoginSessionFromLaunch() {
      try {
        const response = await fetch("/api/session", { cache: "no-store" });
        const result = await response.json();
        if (!response.ok || !result.server_launch_id) throw new Error("Session check failed.");
        const previousLaunchId = sessionStorage.getItem(serverLaunchStorageKey);
        const currentLaunchId = String(result.server_launch_id);
        if (previousLaunchId && previousLaunchId !== currentLaunchId) {
          sessionStorage.removeItem(loginSessionStorageKey);
          sessionStorage.removeItem(mappingSessionStorageKey);
          sessionStorage.removeItem(draftStorageKey);
          sessionStorage.setItem(serverLaunchStorageKey, currentLaunchId);
          const currentSearch = window.location.search || "";
          window.location.replace("/login" + currentSearch);
          return;
        }
        sessionStorage.setItem(serverLaunchStorageKey, currentLaunchId);
      } catch (error) {
        sessionStorage.removeItem(loginSessionStorageKey);
        sessionStorage.removeItem(mappingSessionStorageKey);
        sessionStorage.removeItem(draftStorageKey);
        const currentSearch = window.location.search || "";
        window.location.replace("/login" + currentSearch);
        return;
      }
      if (sessionStorage.getItem(loginSessionStorageKey) !== "true") {
        const currentSearch = window.location.search || "";
        window.location.replace("/login" + currentSearch);
        return;
      }
      el("loginScreen")?.classList.add("hidden");
      el("appShell")?.classList.remove("hidden");
    }
async function prepareReferenceData() {
      const loginButton = el("loginBtn");
      const status = el("loginReadinessStatus");
      loginButton.className = "reference-login-button warn";
      loginButton.disabled = false;
      if (status) {
        status.className = "status";
        status.textContent = "Preparing ZIP reference data...";
      }
      try {
        const response = await fetch("/api/prepare");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "ZIP reference data could not be prepared.");
        appReady = true;
        updateLoginButtonReferenceState();
        if (status) {
          status.className = "status ok";
          status.textContent = "ZIP reference data ready.";
        }
        return result;
      } catch (error) {
        appReady = false;
        updateLoginButtonReferenceState();
        if (status) {
          status.className = "status error";
          status.textContent = productSafeError(error.message, "ZIP reference data needs attention.");
        }
        return null;
      }
    }

function logout() {
      localStorage.removeItem("mapper_login_remembered");
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
      sessionStorage.removeItem(draftStorageKey);
      window.location.replace("/login");
    }
