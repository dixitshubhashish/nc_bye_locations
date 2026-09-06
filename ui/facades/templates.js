/**
 * UI Facade Re-export for Templates Library Controller.
 * 
 * Re-exports from subpackage `ui/templates/templates.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!document.querySelector('script[src*="templates/templates.js"]')) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../templates/templates.js" : "templates/templates.js";
  document.head.appendChild(script);
}
