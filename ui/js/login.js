const LOGIN_SESSION_KEY = "competitive_whitespace_login_session";
const MAPPING_SESSION_KEY = "competitive_whitespace_mapping_session";
const DRAFT_KEY = "competitive_whitespace_mapping_draft";
const REMEMBER_KEY = "mapper_login_remembered";
const SERVER_LAUNCH_KEY = "competitive_whitespace_server_launch";

const el = (id) => document.getElementById(id);

function newSessionId() {
  return window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setStatus(targetId, message, type = "") {
  const target = el(targetId);
  if (!target) return;
  target.className = `status ${type}`.trim();
  target.textContent = message;
}

function productSafeError(message, fallback = "Something went wrong. Please try again.") {
  const text = String(message || "");
  const sensitiveTerms = ["big" + "query", "data" + "set", "project" + "_id", "data" + "set_id", "credentials", "service" + " account", "google", "s" + "ql", "ware" + "house", "bron" + "ze", "sil" + "ver", "table", "module named"];
  if (sensitiveTerms.some((term) => text.toLowerCase().includes(term))) return fallback;
  return text || fallback;
}

function busyMarkup(label = "Loading...") {
  return `<span class="busy-label"><span class="inline-spinner"></span>${label}</span>`;
}

function setButtonBusy(button, label = "Loading...") {
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
  setStatus("loginReadinessStatus", "Preparing ZIP reference data...", "");
  try {
    const response = await fetch("/api/prepare");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "ZIP reference data could not be prepared.");
    setStatus("loginReadinessStatus", "ZIP reference data ready.", "ok");
    return true;
  } catch (error) {
    setStatus("loginReadinessStatus", productSafeError(error.message, "ZIP reference data needs attention."), "error");
    return false;
  }
}

async function login() {
  const button = el("loginBtn");
  const previousButton = setButtonBusy(button, "Signing in...");
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
    sessionStorage.setItem(LOGIN_SESSION_KEY, "true");
    sessionStorage.setItem(MAPPING_SESSION_KEY, newSessionId());
    sessionStorage.removeItem(DRAFT_KEY);
    window.location.replace("/app");
  } catch (error) {
    setStatus("loginStatus", productSafeError(error.message, "Invalid username or password."), "error");
  } finally {
    clearButtonBusy(button, previousButton);
  }
}

async function init() {
  document.querySelectorAll("[data-logo-src]").forEach((image) => {
    image.src = window.APP_CONSTANTS[image.dataset.logoSrc] || window.APP_CONSTANTS.birdeyeLogoUrl;
  });
  el("rememberLogin").checked = localStorage.getItem(REMEMBER_KEY) === "true";
  await syncServerLaunch();
  if (sessionStorage.getItem(LOGIN_SESSION_KEY) === "true") {
    window.location.replace("/app");
    return;
  }
  prepareReferenceData();
  el("loginBtn").addEventListener("click", login);
  el("loginPassword").addEventListener("keydown", (event) => {
    if (event.key === "Enter") login();
  });
}

init();
