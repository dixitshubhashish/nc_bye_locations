/**
 * System Administration & Storage Subpackage Module.
 * 
 * Encapsulates system health probes, readiness checks, storage connection testing,
 * dataset table clearing, and medallion ETL pipeline sync controls.
 * Communicates directly with backend endpoints (`/api/ping`, `/api/storage/test`, `/api/clear`, `/api/prepare`)
 * routed to `whitespace_tool.system`.
 */

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

