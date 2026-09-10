(() => {
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
    // Paint the Review Error Listings tab badge as soon as the app shell is
    // shown, via whichever login path got us here. On a fresh sign-in force a
    // live re-count so the number reflects the current warehouse; on an
    // in-session restore the cheap cached (SQLite) read is enough.
    try {
      if (typeof window.refreshReviewCount === "function") window.refreshReviewCount(!isInitialRestore);
    } catch (error) {
      console.error("Post-login review-count initialization failed:", error);
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
    button.textContent = "Signing in";
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
      clearNonCacheSessionState();
      setLoginStatus("Signed in successfully.", "ok");
      showAuthenticatedApp();
    } catch (error) {
      setLoginStatus(error?.message || "Could not sign in. Please try again.", "error");
    } finally {
      button.disabled = false;
      button.textContent = oldText || "Login";
    }
  }

  // Per-browser UI state (last-seen counts, which tab was open, snoozed
  // items) - not the server-side reporting/dropdown query cache (SQLite
  // query_cache), which this deliberately leaves alone. The login page is
  // the one place guaranteed to run whether the previous session ended via
  // the Logout button (which already clears this itself) or abnormally (a
  // closed tab, an expired cookie) - clearing it here too, on the login
  // page's own load, means a stale snooze list or wrong initial tab can
  // never leak into whoever logs in next on this browser. Explicit user
  // ask, 2026-09-10.
  function clearNonCacheSessionState() {
    localStorage.removeItem("review_error_count_last");
    localStorage.removeItem("whitespace.duplicateBrands.snoozed.v1");
    sessionStorage.removeItem("activeTab");
    sessionStorage.removeItem("reportingInnerTab");
    sessionStorage.removeItem("reviewInnerTab");
  }

  function install() {
    injectLogoGuard();
    clearNonCacheSessionState();

    const button = document.getElementById("loginBtn");
    const username = document.getElementById("loginUser");
    const password = document.getElementById("loginPassword");
    if (!button || !username || !password) return;

    // Capture phase intentionally supersedes the regressed inline login listener
    // without changing the large integrations.html file.
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

  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", install, { once: true });
  } else {
    install();
  }
})();
