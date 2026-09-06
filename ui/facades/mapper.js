/**
 * UI Facade Re-export for Mapping Controller.
 * 
 * Re-exports from subpackage `ui/mapping/mapping.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!document.querySelector('script[src*="mapping/mapping.js"]')) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../mapping/mapping.js" : "mapping/mapping.js";
  document.head.appendChild(script);
}
