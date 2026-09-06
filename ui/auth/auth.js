/**
 * Authentication UI Subpackage Module.
 * 
 * Manages user session initialization, credentials verification, login modal handlers,
 * and communicates directly with the backend endpoint `/api/login` (routed to `whitespace_tool.auth`).
 */
const LOGIN_SESSION_KEY = "competitive_whitespace_login_session";
const MAPPING_SESSION_KEY = "competitive_whitespace_mapping_session";
const DRAFT_KEY = "competitive_whitespace_mapping_draft";
const REMEMBER_KEY = "mapper_login_remembered";

function newSessionId() {
  return window.crypto?.randomUUID
    ? window.crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function injectLogoGuard() {
  if (document.getElementById("loginLogoRegressionGuard")) return;
  const style = document.createElement("style");
  style.id = "loginLogoRegressionGuard";
  style.textContent = `
    .login-brand .brand-icon-crop {
      width: auto !important;
      max-width: 100% !important;
      height: auto !important;
      min-height: 52px;
      overflow: visible !important;
    }
    .login-brand .brand-logo-image {
      display: block !important;
      width: auto !important;
      height: auto !important;
      max-width: min(240px, 100%) !important;
      max-height: 64px !important;
      object-fit: contain !important;
      object-position: center !important;
    }
    header .brand-logo-image,
    .app-footer .brand-logo-image {
      width: auto !important;
      height: auto !important;
      max-width: 210px !important;
      max-height: 32px !important;
      object-fit: contain !important;
    }
  `;
  document.head.appendChild(style);
}

function setLoginStatus(message, type = "error") {
  const status = document.getElementById("loginStatus");
  if (!status) return;
  status.className = `status ${type}`;
  status.textContent = message;
}

function showAuthenticatedApp(isInitialRestore = false) {
  const loginScreen = document.getElementById("loginScreen");
  const appShell = document.getElementById("appShell");
  loginScreen?.classList.add("hidden");
  appShell?.classList.remove("hidden");

  try {
    if (typeof window.switchView === "function") {
      if (isInitialRestore) {
        const urlParams = new URLSearchParams(window.location.search);
        const activeTab = urlParams.get("view") || sessionStorage.getItem("activeTab") || "mapperView";
        window.switchView(activeTab);
      } else {
        window.switchView("mapperView");
      }
    }
  } catch (error) {
    console.error("Post-login navigation initialization failed:", error);
  }

  try {
    if (typeof window.loadAppData === "function") window.loadAppData();
  } catch (error) {
    console.error("Post-login data initialization failed:", error);
  }
  try {
    if (typeof window.refreshHeaderReadiness === "function") window.refreshHeaderReadiness();
  } catch (error) {
    console.error("Post-login readiness initialization failed:", error);
  }
}

async function safeLogin() {
  const button = document.getElementById("loginBtn");
  const usernameInput = document.getElementById("loginUser");
  const passwordInput = document.getElementById("loginPassword");
  const rememberInput = document.getElementById("rememberLogin");
  if (!button || !usernameInput || !passwordInput) return;

  const username = usernameInput.value.trim() || "admin";
  const password = passwordInput.value;

  button.disabled = true;
  const oldText = button.textContent;
  button.textContent = "Signing in…";
  const status = document.getElementById("loginStatus");
  if (status) status.className = "status hidden";

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const raw = await response.text();
    let result = {};
    try {
      result = raw ? JSON.parse(raw) : {};
    } catch (_) {
      result = {};
    }

    if (!response.ok || !result.authenticated) {
      throw new Error(result.error || (response.status >= 500
        ? "Login service is temporarily unavailable. Please try again."
        : "Invalid username or password."));
    }

    if (rememberInput?.checked) localStorage.setItem(REMEMBER_KEY, "true");
    else localStorage.removeItem(REMEMBER_KEY);

    sessionStorage.setItem(LOGIN_SESSION_KEY, "true");
    sessionStorage.setItem(MAPPING_SESSION_KEY, newSessionId());
    sessionStorage.removeItem(DRAFT_KEY);
    setLoginStatus("Signed in successfully.", "ok");
    showAuthenticatedApp();
  } catch (error) {
    setLoginStatus(error?.message || "Could not sign in. Please try again.", "error");
  } finally {
    button.disabled = false;
    button.textContent = oldText || "Login";
  }
}

function login() {
  return safeLogin();
}

function logout() {
  localStorage.removeItem("mapper_login_remembered");
  sessionStorage.removeItem("competitive_whitespace_login_session");
  sessionStorage.removeItem("competitive_whitespace_mapping_session");
  sessionStorage.removeItem("competitive_whitespace_mapping_draft");
  const pass = document.getElementById("loginPassword");
  const status = document.getElementById("loginStatus");
  const shell = document.getElementById("appShell");
  const screen = document.getElementById("loginScreen");
  if (pass) pass.value = "";
  if (status) status.className = "status hidden";
  if (shell) shell.classList.add("hidden");
  if (screen) screen.classList.remove("hidden");
}

function resetLoginSessionFromLaunch() {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("logout") === "true") {
    sessionStorage.removeItem(LOGIN_SESSION_KEY);
    sessionStorage.removeItem(MAPPING_SESSION_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
  }
}

function restoreRememberedLogin() {
  const remember = localStorage.getItem(REMEMBER_KEY) === "true";
  const rememberInput = document.getElementById("rememberLogin");
  if (rememberInput) rememberInput.checked = remember;
  if (sessionStorage.getItem(LOGIN_SESSION_KEY) === "true") {
    showAuthenticatedApp(true);
  }
}

function prepareReferenceData() {
  if (typeof window.loadBrands === "function") window.loadBrands();
  if (typeof window.loadTemplateLibrary === "function") window.loadTemplateLibrary();
}

async function loadAppData() {
  if (typeof window.loadBrands === "function") await window.loadBrands();
  if (typeof window.loadFieldRegistry === "function") await window.loadFieldRegistry();
  if (typeof window.loadTemplateLibrary === "function") await window.loadTemplateLibrary();
  if (typeof window.refreshReviewCount === "function") await window.refreshReviewCount();
}

function install() {
  injectLogoGuard();

  const button = document.getElementById("loginBtn");
  const username = document.getElementById("loginUser");
  const password = document.getElementById("loginPassword");
  if (!button || !username || !password) return;

  button.removeEventListener("click", safeLogin);
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
    safeLogin();
  }, true);

  [username, password].forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      safeLogin();
    }, true);
  });

  if (sessionStorage.getItem(LOGIN_SESSION_KEY) === "true") {
    showAuthenticatedApp(true);
  }
}

// Global Exports
window.login = login;
window.safeLogin = safeLogin;
window.logout = logout;
window.showAuthenticatedApp = showAuthenticatedApp;
window.resetLoginSessionFromLaunch = resetLoginSessionFromLaunch;
window.restoreRememberedLogin = restoreRememberedLogin;
window.prepareReferenceData = prepareReferenceData;
window.loadAppData = loadAppData;
window.initAuthEvents = install;

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", install, { once: true });
} else {
  install();
}
