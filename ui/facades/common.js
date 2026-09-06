/**
 * UI Facade Re-export for Shared Common Utilities.
 * 
 * Re-exports from subpackage `ui/common/common.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!document.querySelector('script[src*="common/common.js"]')) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../common/common.js" : "common/common.js";
  document.head.appendChild(script);
}
