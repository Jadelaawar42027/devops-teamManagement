# --- resource group ---
# The class resource group is created by the professor and the service principal cannot
# create one, so by default it is only read (data source). create_resource_group = true is
# for a personal subscription.

resource "azurerm_resource_group" "main" {
  count    = var.create_resource_group ? 1 : 0
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

data "azurerm_resource_group" "existing" {
  count = var.create_resource_group ? 0 : 1
  name  = var.resource_group_name
}

locals {
  resource_group_name = var.create_resource_group ? azurerm_resource_group.main[0].name : data.azurerm_resource_group.existing[0].name
}

# --- virtual network ---

resource "azurerm_virtual_network" "main" {
  name                = "${var.prefix}-vnet"
  resource_group_name = local.resource_group_name
  location            = var.location
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "vm" {
  name                 = "${var.prefix}-vm-subnet"
  resource_group_name  = local.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.subnet_cidr]
  # No implicit internet access: the VM reaches the internet (apt, GHCR, Azure SQL) only
  # through the load balancer's outbound rule (lb.tf), so its outgoing IP is the LB's IP,
  # which is the one allowed through the SQL firewall.
  default_outbound_access_enabled = false
}

# --- firewall in front of the subnet ---
# Rules are checked lowest priority number first. Azure's built-in rules after these still
# allow the load balancer's health probe (AllowAzureLoadBalancerInBound) and deny all other
# inbound traffic (DenyAllInBound).

resource "azurerm_network_security_group" "vm" {
  name                = "${var.prefix}-vm-nsg"
  resource_group_name = local.resource_group_name
  location            = var.location
  tags                = var.tags

  security_rule {
    name                       = "allow-http"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = "Internet"
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "80"
  }

  # The NAT rule turns LB port 50022 into port 22 on the VM, and the NSG sees the
  # translated port with the client's real source IP, so this rule limits SSH to admin_cidr.
  security_rule {
    name                       = "allow-ssh-from-admin"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_address_prefix      = var.admin_cidr
    source_port_range          = "*"
    destination_address_prefix = "*"
    destination_port_range     = "22"
  }
}

resource "azurerm_subnet_network_security_group_association" "vm" {
  subnet_id                 = azurerm_subnet.vm.id
  network_security_group_id = azurerm_network_security_group.vm.id
}
