# One logical SQL server with one serverless database per service.
# The admin login is only used by the pipeline, to create a contained user inside each
# database (kpi_svc, routing_svc). Each app connects as its own user, which exists only in
# its own database, so neither service can read the other's tables.

resource "azurerm_mssql_server" "main" {
  name                          = "${var.prefix}-sql"
  resource_group_name           = local.resource_group_name
  location                      = var.location
  version                       = "12.0"
  administrator_login           = var.sql_admin_login
  administrator_login_password  = var.sql_admin_password
  minimum_tls_version           = "1.2"
  public_network_access_enabled = true # reachable only through the firewall rules below
  tags                          = var.tags
}

locals {
  databases = {
    kpi     = "${var.prefix}-kpi-db"
    routing = "${var.prefix}-routing-db"
  }
}

resource "azurerm_mssql_database" "service" {
  for_each = local.databases

  name      = each.value
  server_id = azurerm_mssql_server.main.id
  # serverless: billed per second of vCore use, compute free while paused
  sku_name                    = var.sql_sku_name
  min_capacity                = var.sql_min_capacity
  auto_pause_delay_in_minutes = var.sql_auto_pause_delay_minutes
  max_size_gb                 = var.sql_max_size_gb
  storage_account_type        = "Local" # locally redundant backups, the cheapest
  zone_redundant              = false
  tags                        = var.tags
}

# 0.0.0.0 to 0.0.0.0 is Azure's special rule for "allow Azure services".
resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# The VM's outbound traffic leaves with the load balancer's IP (outbound rule in lb.tf).
resource "azurerm_mssql_firewall_rule" "load_balancer" {
  name             = "${var.prefix}-lb"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = azurerm_public_ip.lb.ip_address
  end_ip_address   = azurerm_public_ip.lb.ip_address
}
