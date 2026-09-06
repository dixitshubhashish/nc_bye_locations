/**
 * UI Facade Re-export for Error Review Controller.
 * 
 * Re-exports from subpackage `ui/review/review.js`.
 * Environment-aware path resolution supporting both direct and aliased access.
 */
if (!document.querySelector('script[src*="review/review.js"]')) {
  const script = document.createElement("script");
  script.src = window.location.pathname.includes("/facades/") ? "../review/review.js" : "review/review.js";
  document.head.appendChild(script);
}
