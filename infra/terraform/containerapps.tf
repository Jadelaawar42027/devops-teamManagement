# Both services on Azure Container Apps, Consumption plan: billed per second while a
# replica runs, and scaled to zero replicas when no request has arrived for a few minutes.
#
# The environment is the boundary the two apps share (the brief's system.yaml names it
# <prefix>-env). On the Consumption plan it has no cost of its own: only running replicas bill.
# No Log Analytics workspace: it bills per GB of logs. Console logs can still be streamed
# live with `az containerapp logs show --follow`.

resource "azurerm_container_app_environment" "main" {
  name                = "${var.prefix}-env"
  resource_group_name = local.resource_group_name
  location            = var.location
  tags                = var.tags
}

locals {
  # what differs between the two services
  services = {
    kpi = {
      database    = azurerm_mssql_database.service["kpi"].name
      db_user     = "kpi_svc"
      db_password = var.kpi_db_password
      peer        = "routing"
      peer_url    = "ROUTING_URL"
      peer_wait   = "ROUTING_TIMEOUT_S"
    }
    routing = {
      database    = azurerm_mssql_database.service["routing"].name
      db_user     = "routing_svc"
      db_password = var.routing_db_password
      peer        = "kpi"
      peer_url    = "KPI_URL"
      peer_wait   = "KPI_TIMEOUT_S"
    }
  }

  # A container app's public name is <app name>.<environment's default domain>. Building it
  # from the environment (not from the other app) lets each app know the other's URL
  # without the two apps depending on each other, which Terraform could not resolve.
  app_fqdn = {
    for name in keys(local.services) : name => "${var.prefix}-${name}.${azurerm_container_app_environment.main.default_domain}"
  }

  use_registry_credentials = var.registry_password != ""
}

resource "azurerm_container_app" "service" {
  for_each = local.services

  name                         = "${var.prefix}-${each.key}"
  resource_group_name          = local.resource_group_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single" # one revision at a time: a deploy replaces the old one
  tags                         = var.tags

  # Secrets are stored encrypted by Container Apps and handed to the container as an env
  # var; they never appear as plain values in the app's configuration.
  secret {
    name = "database-url"
    # urlencode: characters like @ : / in the password cannot break the URL
    value = "mssql://${each.value.db_user}:${urlencode(each.value.db_password)}@${azurerm_mssql_server.main.fully_qualified_domain_name}:1433/${each.value.database}"
  }

  # Only for private GHCR packages; public packages need no credentials.
  dynamic "secret" {
    for_each = local.use_registry_credentials ? [1] : []
    content {
      name  = "registry-password"
      value = var.registry_password
    }
  }

  dynamic "registry" {
    for_each = local.use_registry_credentials ? [1] : []
    content {
      server               = "ghcr.io"
      username             = var.registry_username
      password_secret_name = "registry-password"
    }
  }

  ingress {
    external_enabled           = true # the browser calls both services directly
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = false # HTTPS only; Azure provides the certificate

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # 0: no replica, and no cost, while idle. 1: never two replicas, so the migrations
    # that run at startup can never run twice at the same time.
    min_replicas = 0
    max_replicas = 1

    container {
      name   = each.key
      image  = "${var.image_registry}/${each.key}:${var.image_tag}"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "PORT"
        value = "8000"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = each.value.peer_url
        value = "https://${local.app_fqdn[each.value.peer]}"
      }
      env {
        name  = each.value.peer_wait
        value = "2"
      }
      env {
        name  = "CORS_ORIGINS"
        value = local.ui_origin
      }
      env {
        name  = "SEED_DEMO"
        value = var.seed_demo
      }
      env {
        name  = "GIT_SHA"
        value = var.image_tag
      }
      # a paused database takes up to about a minute to resume; 10 attempts with backoff
      # wait about 90 seconds before giving up
      env {
        name  = "DB_CONNECT_RETRIES"
        value = "10"
      }
    }
  }
}
