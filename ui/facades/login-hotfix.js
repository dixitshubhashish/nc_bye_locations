/**
 * UI Facade Re-export for Authentication Hotfix.
 * 
 * Re-exports from subpackage `ui/auth/auth.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!document.querySelector('script[src*="auth/auth.js"]')) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../auth/auth.js" : "auth/auth.js";
  script.async = true;
  document.head.appendChild(script);
}
