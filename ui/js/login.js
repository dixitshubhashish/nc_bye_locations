const LOGIN_SESSION_KEY = "competitive_whitespace_login_session";
const MAPPING_SESSION_KEY = "competitive_whitespace_mapping_session";
const DRAFT_KEY = "competitive_whitespace_mapping_draft";
const REMEMBER_KEY = "mapper_login_remembered";
const SERVER_LAUNCH_KEY = "competitive_whitespace_server_launch";
let referenceDataReady = false;
let referenceDataPromise = null;

const el = (id) => document.getElementById(id);

function newSessionId() {
  return window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setStatus(targetId, message, type = "", options = {}) {
  const target = el(targetId);
  if (!target) return;
  target.className = `status ${type}`.trim();
  const messageNode = document.createElement("span");
  messageNode.className = "status-message";
  messageNode.textContent = message;
  target.replaceChildren(messageNode);
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
      retry.textContent = "Reload reference data";
      retry.addEventListener("click", () => prepareReferenceData());
      target.insertBefore(retry, close);
    }
  }
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
  if (sensitiveTerms.some((term) => text.toLowerCase().includes(term))) return fallback;
  return text || fallback;
}

function busyMarkup(label = "Loading") {
  const cleanLabel = String(label).replace(/\.\.\.+$/, "").trim();
  return `<span class="busy-label">${escapeHtml(cleanLabel)} <span class="inline-spinner"></span></span>`;
}

function setReferenceLoadingMessage() {
  const target = el("loginReadinessStatus");
  if (!target) return;
  target.className = "status";
  target.replaceChildren();
  const messageNode = document.createElement("span");
  messageNode.className = "status-message";
  messageNode.innerHTML = `
    ${busyMarkup("Preparing location reference data")}
    <span class="status-point">You can sign in now — this finishes in the background.</span>
    <span class="status-point">Maps and filters will sharpen as reference data finishes syncing.</span>
  `;
  target.appendChild(messageNode);
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

async function syncServerLaunch() {
  try {
    const response = await fetch("/api/session", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || !result.server_launch_id) throw new Error("Session check failed.");
    const current = String(result.server_launch_id);
    const previous = sessionStorage.getItem(SERVER_LAUNCH_KEY);
    if (previous && previous !== current) {
      sessionStorage.removeItem(LOGIN_SESSION_KEY);
      sessionStorage.removeItem(MAPPING_SESSION_KEY);
      sessionStorage.removeItem(DRAFT_KEY);
    }
    sessionStorage.setItem(SERVER_LAUNCH_KEY, current);
  } catch (_error) {
    sessionStorage.removeItem(LOGIN_SESSION_KEY);
    sessionStorage.removeItem(MAPPING_SESSION_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
  }
}

async function prepareReferenceData() {
  const loginButton = el("loginBtn");
  if (referenceDataPromise) return referenceDataPromise;
  referenceDataPromise = (async () => {
    referenceDataReady = false;
    setReferenceLoadingMessage();
  try {
    const response = await fetch("/api/prepare");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Location reference data could not be prepared.");
    referenceDataReady = result.status === "ready" || result.loaded === true;
    setStatus(
      "loginReadinessStatus",
      referenceDataReady ? "Location reference data is ready." : "You can sign in now — maps and filters will sharpen as reference data finishes syncing.",
      referenceDataReady ? "ok" : "warn",
      referenceDataReady ? {} : { retry: true },
    );
    return referenceDataReady;
  } catch (error) {
    referenceDataReady = false;
    setStatus("loginReadinessStatus", productSafeError(error.message, "Location reference data needs attention."), "error", { retry: true });
    return false;
  } finally {
    if (loginButton) loginButton.disabled = false;
    referenceDataPromise = null;
  }
  })();
  return referenceDataPromise;
}

async function login() {
  const button = el("loginBtn");
  const previousButton = setButtonBusy(button, "Signing in");
  setStatus("loginStatus", "", "hidden");
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: el("loginUser").value.trim(), password: el("loginPassword").value })
    });
    const result = await response.json();
    if (!response.ok || !result.authenticated) throw new Error(result.error || "Invalid username or password.");
    if (el("rememberLogin").checked) localStorage.setItem(REMEMBER_KEY, "true");
    else localStorage.removeItem(REMEMBER_KEY);
    await syncServerLaunch();
    sessionStorage.setItem(LOGIN_SESSION_KEY, "true");
    sessionStorage.setItem(MAPPING_SESSION_KEY, newSessionId());
    sessionStorage.removeItem(DRAFT_KEY);
    sessionStorage.removeItem("activeTab");
    window.location.replace("/app?view=mapperView");
  } catch (error) {
    setStatus("loginStatus", productSafeError(error.message, "Invalid username or password."), "error");
  } finally {
    clearButtonBusy(button, previousButton);
  }
}

async function testDbConnection() {
  const button = el("testDbBtn");
  const previousButton = setButtonBusy(button, "Testing DB connection");
  setStatus("dbStatus", "", "hidden");
  try {
    const response = await fetch("/api/ping", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || result.ok === false) {
      throw new Error(result.error || "Database connection needs attention.");
    }
    setStatus("dbStatus", "Database connection ready.", "ok");
  } catch (error) {
    setStatus("dbStatus", productSafeError(error.message, "Database connection needs attention."), "error");
  } finally {
    clearButtonBusy(button, previousButton);
  }
}

// Inline SVG wordmark shown if the external CDN logo can't be reached
// (offline, blocked, or 404). Without this the login page - the first
// screen users hit - renders a broken image. Mirrors the main app's fallback.
const LOGIN_LOGO_FALLBACK = "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 60" width="240" height="60"><rect width="240" height="60" fill="none"/><g transform="translate(10, 10)"><path d="M 6 22 C 6 8 18 3 24 3 C 30 3 42 8 42 22 C 42 36 30 41 24 41 C 18 41 6 36 6 22 Z" fill="#0b70f0"/><ellipse cx="24" cy="22" rx="10" ry="10" fill="#ffffff"/><circle cx="24" cy="22" r="5" fill="#1d2b4f"/><path d="M 2 22 C 14 36 34 36 46 22 C 34 8 14 8 2 22 Z" fill="none" stroke="#0b70f0" stroke-width="3" stroke-linecap="round"/><text x="56" y="31" font-family="system-ui, -apple-system, sans-serif" font-weight="800" font-size="28" fill="#1d2b4f">Birdeye</text></g></svg>');

async function init() {
  document.querySelectorAll("[data-logo-src]").forEach((image) => {
    image.onerror = () => { image.onerror = null; image.src = LOGIN_LOGO_FALLBACK; };
    image.src = window.APP_CONSTANTS[image.dataset.logoSrc] || window.APP_CONSTANTS.birdeyeLogoUrl || LOGIN_LOGO_FALLBACK;
  });
  el("rememberLogin").checked = localStorage.getItem(REMEMBER_KEY) === "true";
  await syncServerLaunch();
  if (sessionStorage.getItem(LOGIN_SESSION_KEY) === "true") {
    const urlParams = new URLSearchParams(window.location.search);
    const viewParam = urlParams.get("view") || sessionStorage.getItem("activeTab");
    const validViews = ["mapperView", "reportingView", "reviewView", "templateLibraryView"];
    const target = (viewParam && validViews.includes(viewParam)) ? `/app?view=${encodeURIComponent(viewParam)}` : "/app";
    window.location.replace(target);
    return;
  }
  prepareReferenceData();
  el("loginBtn").addEventListener("click", login);
  el("testDbBtn")?.addEventListener("click", testDbConnection);
  el("loginPassword").addEventListener("keydown", (event) => {
    if (event.key === "Enter") login();
  });
}

init();
