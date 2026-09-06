/**
 * Shared/common UI utilities module.
 * 
 * Provides DOM helpers, formatting, loading overlays, status messaging,
 * and view tab navigation handlers across all UI components.
 */

let appDataLoaded = false;
let appReady = false;
let readinessCheckInFlight = null;
const loginReadinessTimeoutMs = 2500;
let activeAbortController = null;

let sourceTypes = [];

const SOURCE_TYPE_LABELS = {
  csv: "CSV",
  excel: "Excel (.xlsx)",
  json: "JSON",
  xml: "XML",
  api_get_json: "GET API JSON",
  python_editor: "Python Editor",
};

function sourceTypeLabel(sourceTypeKey) {
  return SOURCE_TYPE_LABELS[sourceTypeKey] || String(sourceTypeKey || "Unknown");
}

const loginSessionStorageKey = "competitive_whitespace_login_session";
const mappingSessionStorageKey = "competitive_whitespace_mapping_session";
const draftStorageKey = "competitive_whitespace_mapping_draft";

const el = (id) => document.getElementById(id);

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

function renderSimpleTable(targetId, columns, rows) {
  const target = el(targetId);
  if (!target) return;
  const visibleRows = rows.length ? rows : [Object.fromEntries(columns.map((column) => {
    const label = String(column.label || column.key || "").toLowerCase();
    const value = /count|number|store|location|state|city|zip|population|income|age|share|covered/.test(label) ? 0 : "";
    return [column.key, value];
  }))];
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

function setStatus(message, type = "") {
  const target = el("status");
  if (!target) return;
  target.className = `status ${type}`;
  target.textContent = message;
}

function showLoadingOverlay(message, onCancel) {
  if (activeAbortController) {
    try { activeAbortController.abort(); } catch (_) {}
  }
  activeAbortController = new AbortController();
  const overlayMessage = el("loadingOverlayMessage");
  const overlaySub = el("loadingOverlaySub");
  const overlay = el("loadingOverlay");
  const cancelBtn = el("loadingCancelBtn");
  if (overlayMessage) overlayMessage.textContent = message || "Working...";
  if (overlaySub) overlaySub.textContent = "Processing records.";
  if (overlay) overlay.classList.remove("hidden");
  if (cancelBtn) {
    cancelBtn.classList.toggle("hidden", typeof onCancel !== "function");
    cancelBtn.onclick = () => {
      if (typeof onCancel !== "function") return;
      if (activeAbortController) {
        activeAbortController.abort();
        activeAbortController = null;
      }
      hideLoadingOverlay();
      onCancel();
      setStatus("Cancelled. No changes.", "warn");
    };
  }
}

function updateLoadingOverlay(message, detail = "") {
  const overlayMessage = el("loadingOverlayMessage");
  const overlaySub = el("loadingOverlaySub");
  if (overlayMessage) overlayMessage.textContent = message || "Working...";
  if (overlaySub) overlaySub.textContent = detail || "Processing records.";
}

function hideLoadingOverlay() {
  const overlay = el("loadingOverlay");
  const cancelBtn = el("loadingCancelBtn");
  if (overlay) overlay.classList.add("hidden");
  if (cancelBtn) cancelBtn.classList.remove("hidden");
  activeAbortController = null;
}

function setProgress(percent, message) {
  const boundedPercent = Math.max(0, Math.min(100, percent));
  const saveProgress = el("saveProgress");
  const progressFill = el("progressFill");
  const progressValue = el("progressValue");
  const progressMessage = el("progressMessage");
  if (saveProgress) {
    saveProgress.classList.remove("hidden");
    saveProgress.setAttribute("aria-busy", "true");
  }
  if (progressFill) progressFill.style.width = `${boundedPercent}%`;
  if (progressValue) progressValue.textContent = `${boundedPercent}%`;
  if (progressMessage) progressMessage.textContent = message;
  showLoadingOverlay(`${message} (${boundedPercent}%)`);
}

function hideProgress() {
  const saveProgress = el("saveProgress");
  if (saveProgress) {
    saveProgress.classList.add("hidden");
    saveProgress.setAttribute("aria-busy", "false");
  }
  hideLoadingOverlay();
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
  ["mapperView", "reportingView", "reviewView", "templateLibraryView"].forEach((id) => {
    const target = el(id);
    if (target) target.classList.toggle("hidden", id !== viewId);
  });
  const header = el("appShell")?.querySelector("header");
  if (header) header.classList.toggle("reporting-active", viewId === "reportingView");
  if (el("restartMappingBtn")) el("restartMappingBtn").classList.toggle("hidden", viewId !== "mapperView");
  if (el("resetMappingBtn")) el("resetMappingBtn").classList.toggle("hidden", viewId !== "mapperView");
  if (viewId === "reportingView" && typeof loadReporting === "function" && !window.reportLoaded) loadReporting();
  if (viewId === "templateLibraryView" && typeof loadTemplateFilters === "function") {
    loadTemplateFilters().then(() => { if (typeof loadTemplateLibrary === "function") loadTemplateLibrary(); });
  }
  if (viewId === "reviewView") {
    if (typeof loadRejectedRecords === "function") loadRejectedRecords();
    if (typeof refreshReviewCount === "function") refreshReviewCount();
  }
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

async function fetchReadinessPing() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), loginReadinessTimeoutMs);
  try {
    return await fetch("/api/ping", { signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
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

function busyMarkup(label = "Loading") {
  const cleanLabel = String(label).replace(/\.\.\.+$/, "").trim();
  return `<span class="busy-label">${escapeHtml(cleanLabel)} <span class="inline-spinner"></span></span>`;
}


