// The browser only ever talks to the nginx proxy it was loaded from, so these paths are the
// same locally and on Azure: no per-environment URLs and no CORS.
window.APP_CONFIG = {
  KPI_URL: "/api/kpi",
  ROUTING_URL: "/api/routing",
};
