# Standard public load balancer: the only way into (and out of) the VM.
#   rule      TCP 80 -> VM:80 (nginx), only while the probe passes
#   NAT rule  TCP 50022 -> VM:22 (SSH), further limited to admin_cidr by the NSG
#   outbound  the VM's internet traffic leaves with the LB's public IP

resource "azurerm_public_ip" "lb" {
  name                = "${var.prefix}-lb-ip"
  resource_group_name = local.resource_group_name
  location            = var.location
  allocation_method   = "Static"   # the address survives restarts, so DNS and the SQL firewall stay valid
  sku                 = "Standard" # must match the Standard load balancer
  # gives the real public name <label>.<location>.cloudapp.azure.com
  domain_name_label = var.domain_name_label
  tags              = var.tags
}

resource "azurerm_lb" "main" {
  name                = "${var.prefix}-lb"
  resource_group_name = local.resource_group_name
  location            = var.location
  sku                 = "Standard"
  tags                = var.tags

  frontend_ip_configuration {
    name                 = "public"
    public_ip_address_id = azurerm_public_ip.lb.id
  }
}

resource "azurerm_lb_backend_address_pool" "vms" {
  name            = "${var.prefix}-vms"
  loadbalancer_id = azurerm_lb.main.id
}

resource "azurerm_network_interface_backend_address_pool_association" "vm" {
  network_interface_id    = azurerm_network_interface.vm.id
  ip_configuration_name   = "internal"
  backend_address_pool_id = azurerm_lb_backend_address_pool.vms.id
}

# The probe asks nginx for /lb-probe, which nginx answers itself. It must not be /health:
# that one reaches both databases, and a probe every 15 seconds would keep the serverless
# databases from ever auto-pausing, so they would bill compute around the clock.
resource "azurerm_lb_probe" "http" {
  name                = "http-probe"
  loadbalancer_id     = azurerm_lb.main.id
  protocol            = "Http"
  port                = 80
  request_path        = var.lb_probe_path
  interval_in_seconds = 15
  number_of_probes    = 2
}

resource "azurerm_lb_rule" "http" {
  name                           = "http"
  loadbalancer_id                = azurerm_lb.main.id
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.vms.id]
  probe_id                       = azurerm_lb_probe.http.id
  # outbound traffic is handled by the explicit outbound rule below instead
  disable_outbound_snat = true
}

resource "azurerm_lb_nat_rule" "ssh" {
  name                           = "ssh"
  resource_group_name            = local.resource_group_name
  loadbalancer_id                = azurerm_lb.main.id
  protocol                       = "Tcp"
  frontend_port                  = var.ssh_nat_port
  backend_port                   = 22
  frontend_ip_configuration_name = "public"
}

resource "azurerm_network_interface_nat_rule_association" "ssh" {
  network_interface_id  = azurerm_network_interface.vm.id
  ip_configuration_name = "internal"
  nat_rule_id           = azurerm_lb_nat_rule.ssh.id
}

# A VM behind a Standard load balancer with no public IP of its own has no internet access
# unless the load balancer gives it some. Needed for apt, docker pull from GHCR and Azure SQL.
resource "azurerm_lb_outbound_rule" "internet" {
  name                    = "outbound"
  loadbalancer_id         = azurerm_lb.main.id
  protocol                = "All"
  backend_address_pool_id = azurerm_lb_backend_address_pool.vms.id

  frontend_ip_configuration {
    name = "public"
  }
}
