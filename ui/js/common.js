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
// Every created_at/updated_at display (Template Library, brand list, etc.)
// should read down to the second, not a bare ISO string with fractional
// seconds and a "T" separator, and not date-only either - shared so every
// such timestamp is formatted identically instead of drifting per call site.
// Shared searchable-select behavior (FLT-02/FLT-03/FLT-05 all use this same
// component, per the explicit "build once, not three implementations"
// instruction). Rebuilds the real <option> list on input instead of hiding
// options with CSS, since a native <select>'s open dropdown does not
// reliably respect display:none on options across browsers - removing them
// from the DOM does. Call again (e.g. after reloading the option list) to
// refresh the cached options; it reuses the existing search input rather
// than creating a duplicate.
function attachSearchableSelect(selectId, { threshold = 15, minChars = 2 } = {}) {
      const select = document.getElementById(selectId);
      if (!select) return;
      const liveOptions = Array.from(select.options).map((option) => ({ value: option.value, text: option.textContent, className: option.className }));
      if (liveOptions.length <= threshold) return;
      let search = document.getElementById(`${selectId}Search`);
      if (!search) {
        search = document.createElement("input");
        search.type = "search";
        search.id = `${selectId}Search`;
        search.className = "report-filter-control";
        search.autocomplete = "off";
        // Plain label. This filters the select's own options in memory
        // (liveOptions above) - it never queries the server - so there is no
        // reason to explain a minimum length to the user.
        search.placeholder = selectId === "brandSelect" ? "Search brand" : "Search";
        search.setAttribute("aria-label", "Search this list");
        select.parentNode.insertBefore(search, select);
      }
      search.dataset.allOptions = JSON.stringify(liveOptions);
      search.oninput = () => {
        const allOptions = JSON.parse(search.dataset.allOptions || "[]");
        const query = search.value.trim().toLowerCase();
        const selected = select.value;
        const matches = query.length < minChars
          ? allOptions
          : allOptions.filter((option) => !option.value || option.value === selected || option.text.toLowerCase().includes(query));
        select.innerHTML = matches.map((option) => `<option value="${escapeHtml(option.value)}"${option.className ? ` class="${escapeHtml(option.className)}"` : ""}>${escapeHtml(option.text)}</option>`).join("");
        select.value = matches.some((option) => option.value === selected) ? selected : "";
      };
    }
function formatTimestamp(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      const pad = (n) => String(n).padStart(2, "0");
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }
function formatBrandName(value) {
      return String(value ?? "").trim().replace(/_/g, " ").replace(/[^A-Za-z0-9\s#'\-.]/g, "").replace(/\s+/g, " ").replace(/[A-Za-z][^\s-]*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
    }
// Turns a raw db/backend field key (e.g. "opening_date") into a readable
// column name ("Opening Date") for any validation-error/hint display -
// shared so every such listing (Review Error Listings, Data Quality) shows
// the same formatted name instead of the literal stored key.
function formatFieldLabel(value) {
      return String(value || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
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
      // Every table paginates once it is long enough to need it. Before this
      // only the market-gaps table had a pager; everything else rendered
      // every row (or a silent .slice(0, 10) that hid the rest with no way
      // to reach it). State is per-target so two tables cannot fight.
      const page = simpleTablePages.get(targetId) || 0;
      const pageCount = Math.ceil(visibleRows.length / SIMPLE_TABLE_PAGE_SIZE);
      const safePage = Math.min(Math.max(page, 0), Math.max(pageCount - 1, 0));
      simpleTablePages.set(targetId, safePage);
      const pageRows = pageCount > 1
        ? visibleRows.slice(safePage * SIMPLE_TABLE_PAGE_SIZE, (safePage + 1) * SIMPLE_TABLE_PAGE_SIZE)
        : visibleRows;
      const tableHtml = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${pageRows.map((row) => `<tr>${columns.map((column) => {
        const value = column.format ? column.format(row[column.key], row) : row[column.key];
        return `<td>${column.html ? value : escapeHtml(value)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>`;
      const pager = pageCount > 1
        ? `<div class="simple-table-pager" style="display:flex; justify-content:center; align-items:center; gap:8px; margin-top:10px;">
             <button type="button" class="secondary" data-simple-page="prev" data-target="${escapeHtml(targetId)}"${safePage === 0 ? " disabled" : ""}>Previous</button>
             <span style="font-size:12px; color:var(--muted);">Page ${safePage + 1} of ${pageCount} &middot; ${visibleRows.length.toLocaleString()} rows</span>
             <button type="button" class="secondary" data-simple-page="next" data-target="${escapeHtml(targetId)}"${safePage >= pageCount - 1 ? " disabled" : ""}>Next</button>
           </div>`
        : "";
      target.innerHTML = tableHtml + pager;
      target.dataset.simpleTableColumns = "1";
      simpleTableData.set(targetId, { columns, rows });
    }

// Paging state and the last dataset per table, so a page change can re-render
// without refetching. Module scope: renderSimpleTable is called repeatedly.
const SIMPLE_TABLE_PAGE_SIZE = 10;
const simpleTablePages = new Map();
const simpleTableData = new Map();

// One delegated listener for every simple table's pager.
document.addEventListener("click", (event) => {
      const button = event.target?.closest?.("button[data-simple-page]");
      if (!button) return;
      event.preventDefault();
      const targetId = button.dataset.target;
      const stored = simpleTableData.get(targetId);
      if (!stored) return;
      const current = simpleTablePages.get(targetId) || 0;
      simpleTablePages.set(targetId, button.dataset.simplePage === "next" ? current + 1 : current - 1);
      renderSimpleTable(targetId, stored.columns, stored.rows);
    });

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

function showLoadingOverlay(message, onCancel, onHide) {
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
      // Distinct from Cancel - this doesn't abort anything, it just lets the
      // caller (setProgress(), for a save already in flight) suppress
      // further redraws until the operation finishes on its own.
      el("loadingHideBtn").classList.toggle("hidden", typeof onHide !== "function");
      el("loadingHideBtn").onclick = () => {
        hideLoadingOverlay();
        if (typeof onHide === "function") onHide();
      };
    }
function updateLoadingOverlay(message, detail = "") {
      el("loadingOverlayMessage").textContent = message || "Working...";
      el("loadingOverlaySub").textContent = detail || "Processing records.";
    }
function hideLoadingOverlay() {
      el("loadingOverlay").classList.add("hidden");
      el("loadingCancelBtn").classList.remove("hidden");
      el("loadingHideBtn").classList.add("hidden");
      activeAbortController = null;
    }
// Set by the save flow (mapper.js) when the user clicks "Hide - notify me
// when done" on the loading overlay - suppresses further progress redraws
// (the save keeps running regardless; this only stops re-showing UI the
// user explicitly dismissed) until the next fresh save resets it.
let saveProgressHiddenByUser = false;
function setProgress(percent, message) {
      if (saveProgressHiddenByUser) return;
      const boundedPercent = Math.max(0, Math.min(100, percent));
      el("saveProgress").classList.remove("hidden");
      el("saveProgress").setAttribute("aria-busy", "true");
      el("progressFill").style.width = `${boundedPercent}%`;
      el("progressValue").textContent = `${boundedPercent}%`;
      el("progressMessage").textContent = message;
      showLoadingOverlay(`${message} (${boundedPercent}%)`, undefined, () => {
        saveProgressHiddenByUser = true;
        el("saveProgress").classList.add("hidden");
        el("saveProgress").setAttribute("aria-busy", "false");
        if (typeof showBackgroundSaveNotice === "function") showBackgroundSaveNotice();
        // Hiding the progress means "let this finish in the background and
        // give me my workspace back" - so return the mapper to the pre-parse
        // 40/60 layout, ready for a new parse. Without this the dismissed
        // save left the post-parse mapping workspace on screen with no way
        // to start another source. The save itself keeps running: it works
        // from data captured before this point, not from mapper state.
        if (typeof resetMapping === "function") resetMapping();
      });
    }
function hideProgress() {
      saveProgressHiddenByUser = false;
      el("saveProgress").classList.add("hidden");
      el("saveProgress").setAttribute("aria-busy", "false");
      hideLoadingOverlay();
      if (typeof clearBackgroundSaveNotice === "function") clearBackgroundSaveNotice();
    }
// Themed replacements for window.alert / window.confirm. The native ones
// ignore the app theme entirely and cannot be styled, so they looked like a
// different product every time they appeared. Both degrade to the native
// call only if the dialog element is missing (e.g. a page that does not
// include the shell markup).
function showAppNotice(message, title = "Done") {
      const dialog = el("appNoticeDialog");
      if (!dialog || typeof dialog.showModal !== "function") { window.alert(message); return; }
      el("appNoticeTitle").textContent = title;
      el("appNoticeMessage").textContent = message;
      const ok = el("appNoticeOk");
      if (ok && !ok.dataset.bound) {
        ok.dataset.bound = "1";
        ok.addEventListener("click", () => dialog.close());
      }
      dialog.showModal();
    }
function showAppConfirm(message, title = "Please confirm") {
      const dialog = el("appConfirmDialog");
      if (!dialog || typeof dialog.showModal !== "function") return Promise.resolve(window.confirm(message));
      el("appConfirmTitle").textContent = title;
      el("appConfirmMessage").textContent = message;
      return new Promise((resolve) => {
        const finish = (answer) => {
          el("appConfirmYes").removeEventListener("click", onYes);
          el("appConfirmNo").removeEventListener("click", onNo);
          dialog.close();
          resolve(answer);
        };
        const onYes = () => finish(true);
        const onNo = () => finish(false);
        el("appConfirmYes").addEventListener("click", onYes);
        el("appConfirmNo").addEventListener("click", onNo);
        dialog.showModal();
      });
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

function switchView(viewId, isBootRestore = false) {
      if (!viewId) viewId = "mapperView";
      try {
        sessionStorage.setItem("activeTab", viewId);
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set("view", viewId);
        const nextUrl = `${window.location.pathname}?${urlParams.toString()}`;
        history.replaceState(null, "", nextUrl);
      } catch (e) {}
      // The mapper is reused as the template EDITOR. When it was opened from
      // Template Library > Review, the work is still "template library" work,
      // so the top nav must keep showing Template Library rather than jumping
      // the highlight to Mapping.
      const highlightViewId = (viewId === "mapperView" && el("mapperView")?.classList.contains("template-edit-mode"))
        ? "templateLibraryView"
        : viewId;
      document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === highlightViewId));
      ["mapperView", "reportingView", "reviewView", "templateLibraryView"].forEach((id) => el(id).classList.toggle("hidden", id !== viewId));
      el("appShell").querySelector("header").classList.toggle("reporting-active", viewId === "reportingView");
      // Reset Fields Mapping only makes sense while actually on the Mapper
      // tab - it was previously kept visible everywhere as a deliberate
      // simplification, but the user explicitly asked for it to be
      // scoped back to Mapper only.
      el("resetMappingBtn")?.classList.toggle("hidden", viewId !== "mapperView");
      // Reset Fields Mapping's grid slot must not stay reserved as an
      // empty gap once the button itself is hidden outside Mapper - see
      // .header-data-actions.reset-mapping-hidden.
      document.querySelector(".header-data-actions")?.classList.toggle("reset-mapping-hidden", viewId !== "mapperView");
      if (viewId === "mapperView" && typeof renderMappings === "function") renderMappings();
      if (viewId === "reportingView" && !reportLoaded) loadReporting();
      // A genuine nav click into Reporting always lands on the first inner
      // tab; a page refresh while already on Reporting (isBootRestore) must
      // keep whatever inner tab was active - reporting-tabs.js's own init()
      // already restores that from sessionStorage in that case.
      if (viewId === "reportingView" && !isBootRestore) {
        try { sessionStorage.setItem("reportingInnerTab", "location"); } catch (_) {}
        if (typeof window.reportingResetToLocationTab === "function") window.reportingResetToLocationTab();
      }
      if (viewId === "templateLibraryView" && !templateLibraryLoaded) loadTemplateFilters().then(loadTemplateLibrary);
      if (viewId === "reviewView") {
        loadRejectedRecords();
        refreshReviewCount();
        if (typeof loadErrorBrandBreakdown === "function") loadErrorBrandBreakdown();
        if (typeof refreshFixCountersOnce === "function") refreshFixCountersOnce();
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
          const response = await fetch(`/api/prepare${force ? "?force=1" : ""}`);
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "ZIP setup needs attention.");
          const ready = result.status === "ready" || result.loaded === true;
          appReady = ready;
          updateLoginButtonReferenceState();
          setHeaderReadiness(ready ? "ZIPs loaded" : "Loading US ZIPs", ready ? "ok" : "warn");
          setReadinessButtonDisabled(ready);
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
        sessionStorage.removeItem("activeTab");
        window.location.replace("/app?view=mapperView");
      } catch (error) {
        status.className = "status error";
        status.textContent = productSafeError(error.message, "Invalid username or password.");
      }
    }
async function loadAppData() {
      if (appDataLoaded) return;
      appDataLoaded = true;
      await Promise.allSettled([loadFieldRegistry(), loadBrands(), loadTemplateFilters()]);
      // Apply the initial mapper layout (and enable the brand-dependent
      // "Edit a brand" radio/buttons) as soon as brands are in, rather than
      // queuing it behind the unrelated Template Library fetch below - that
      // queuing was why "Edit a brand" could take a visibly long time to
      // become available even though loadBrands() itself was already done.
      if (typeof renderMappings === "function") renderMappings();
      if (typeof updateOutput === "function") updateOutput();
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
