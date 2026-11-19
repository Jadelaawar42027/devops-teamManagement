output "resource_group_name" {
  value = local.resource_group_name
}

output "container_apps_environment" {
  value = azurerm_container_app_environment.main.name
}

output "kpi_url" {
  description = "Public HTTPS base URL of the KPI service."
  value       = "https://${azurerm_container_app.service["kpi"].ingress[0].fqdn}"
}

output "routing_url" {
  description = "Public HTTPS base URL of the routing service."
  value       = "https://${azurerm_container_app.service["routing"].ingress[0].fqdn}"
}

output "static_web_app_name" {
  value = azurerm_static_web_app.ui.name
}

output "ui_url" {
  description = "The public URL of the system: the Static Web App's."
  value       = "https://${azurerm_static_web_app.ui.default_host_name}"
}

output "static_web_app_api_key" {
  description = "Deployment token of the Static Web App. Copy it into the GitHub secret AZURE_STATIC_WEB_APPS_API_TOKEN."
  value       = azurerm_static_web_app.ui.api_key
  sensitive   = true
}

output "sql_server_name" {
  value = azurerm_mssql_server.main.name
}

output "sql_admin_login" {
  description = "Not secret: the password is."
  value       = azurerm_mssql_server.main.administrator_login
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "kpi_database_name" {
  value = azurerm_mssql_database.service["kpi"].name
}

output "routing_database_name" {
  value = azurerm_mssql_database.service["routing"].name
}
