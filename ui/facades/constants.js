/**
 * UI Facade Re-export for App Constants.
 * 
 * Re-exports from subpackage `ui/common/constants.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!window.APP_CONSTANTS) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../common/constants.js" : "common/constants.js";
  document.head.appendChild(script);
}
