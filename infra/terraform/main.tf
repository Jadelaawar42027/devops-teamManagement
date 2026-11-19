# The class's shared resource group (rg-sdd-3a or rg-sdd-3b) already exists (assignment §7):
# "do not create resource groups". So it is only read, through a data source.
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

locals {
  resource_group_name = data.azurerm_resource_group.main.name

  # The UI's origin, the only one allowed to call the services from a browser (CORS).
  ui_origin = "https://${azurerm_static_web_app.ui.default_host_name}"
}
