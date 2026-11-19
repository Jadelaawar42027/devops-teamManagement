// Where the two services are. These are the local values (docker compose publishes kpi on
// 8001 and routing on 8002). On Azure the CD pipeline generates this file with the two
// Container Apps' HTTPS URLs before uploading ui/ to the Static Web App.
window.APP_CONFIG = {
  KPI_URL: "http://localhost:8001",
  ROUTING_URL: "http://localhost:8002",
};
