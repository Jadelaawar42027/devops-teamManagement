output "resource_group_name" {
  value = local.resource_group_name
}

output "public_ip" {
  description = "Static public IP of the load balancer."
  value       = azurerm_public_ip.lb.ip_address
}

output "fqdn" {
  description = "Public DNS name of the load balancer (works without any domain)."
  value       = azurerm_public_ip.lb.fqdn
}

output "app_url" {
  value = "http://${azurerm_public_ip.lb.fqdn}"
}

output "dns_zone_name" {
  value = azurerm_dns_zone.main.name
}

output "dns_name_servers" {
  description = "Azure name servers of the zone. Ask one directly: nslookup app.<zone> <name server>."
  value       = azurerm_dns_zone.main.name_servers
}

output "dns_app_record" {
  value = "${azurerm_dns_a_record.app.name}.${azurerm_dns_zone.main.name}"
}

output "vm_name" {
  value = azurerm_linux_virtual_machine.app.name
}

output "ssh_command" {
  description = "SSH through the load balancer's NAT rule (only from admin_cidr)."
  value       = "ssh -p ${var.ssh_nat_port} ${var.vm_admin_username}@${azurerm_public_ip.lb.fqdn}"
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
