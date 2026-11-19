# A public Azure DNS zone with app.<zone> pointing at the load balancer.
# The zone is not delegated: nobody registered devops.ie's child zone to Azure's name
# servers, so public resolvers do not find it. It still answers when asked directly:
#   nslookup app.jelaawar-ieu2023.devops.ie <one of the dns_name_servers outputs>
# The working public name is the cloudapp.azure.com one from the public IP (lb.tf).

resource "azurerm_dns_zone" "main" {
  name                = var.dns_zone_name
  resource_group_name = local.resource_group_name
  tags                = var.tags
}

resource "azurerm_dns_a_record" "app" {
  name                = "app"
  zone_name           = azurerm_dns_zone.main.name
  resource_group_name = local.resource_group_name
  ttl                 = 300
  records             = [azurerm_public_ip.lb.ip_address]
  tags                = var.tags
}
