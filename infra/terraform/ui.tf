# The static UI: one Azure Static Web App per student (assignment §1a, §7.1), <prefix>-ui.
# Free tier: no monthly cost. Its URL is the public URL of the system (§7.2).
# Terraform creates the empty app; the pipeline uploads ui/ into it with the app's
# deployment token, after generating config.js with the two Container Apps' URLs.

resource "azurerm_static_web_app" "ui" {
  name                = "${var.prefix}-ui"
  resource_group_name = local.resource_group_name
  # Static Web Apps exist in a few regions only; West Europe is one of them
  location = var.location
  sku_tier = "Free"
  sku_size = "Free"
  tags     = var.tags
}
