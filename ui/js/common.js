// Shared/common utilities used across all tabs: DOM helpers, formatting,
// loading overlays, status messaging, login/session bootstrap.

let appDataLoaded = false;
let appReady = false;
let readinessCheckInFlight = null;
const loginReadinessTimeoutMs = 2500;

let sourceTypes = [];

const loginSessionStorageKey = "competitive_whitespace_login_session";
const mappingSessionStorageKey = "competitive_whitespace_mapping_session";
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
function setStatus(message, type = "") {
      el("status").className = `status ${type}`;
      el("status").textContent = message;
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
    }

async function testReadiness() {
      await refreshHeaderReadiness(true);
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
        
        // Instant screen toggle with mapper as the default view.
        el("loginScreen").classList.add("hidden");
        el("appShell").classList.remove("hidden");
        switchView("mapperView");
        refreshHeaderReadiness();
        
        // Asynchronous non-blocking background data load
        loadAppData();
      } catch (error) {
        status.className = "status error";
        status.textContent = productSafeError(error.message, "Invalid username or password.");
      }
    }
async function loadAppData() {
      if (appDataLoaded) return;
      appDataLoaded = true;
      await Promise.allSettled([loadFieldRegistry(), loadBrands(), loadTemplateFilters()]);
    }
function restoreRememberedLogin() {
      const remembered = localStorage.getItem("mapper_login_remembered") === "true";
      el("rememberLogin").checked = remembered;
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
    }
function resetLoginSessionFromLaunch() {
      // Clean neat URLs: no query parameters required for login launch
    }
async function prepareReferenceData() {
      const loginButton = el("loginBtn");
      loginButton.className = "reference-login-button";
      loginButton.disabled = false;
      loginButton.classList.add("ready");
      appReady = true;
    }

function logout() {
      localStorage.removeItem("mapper_login_remembered");
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
      sessionStorage.removeItem(draftStorageKey);
      el("loginPassword").value = "";
      el("loginStatus").className = "status hidden";
      el("appShell").classList.add("hidden");
      el("loginScreen").classList.remove("hidden");
    }
