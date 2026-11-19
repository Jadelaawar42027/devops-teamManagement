# One Ubuntu 24.04 VM that runs the whole app with Docker Compose (deploy/docker-compose.prod.yml).
# It has no public IP of its own: HTTP arrives through the load balancer rule, SSH through
# the load balancer's NAT rule, and outbound traffic leaves through its outbound rule.

resource "azurerm_network_interface" "vm" {
  name                = "${var.prefix}-vm-nic"
  resource_group_name = local.resource_group_name
  location            = var.location
  tags                = var.tags

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vm.id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "app" {
  name                  = "${var.prefix}-vm"
  resource_group_name   = local.resource_group_name
  location              = var.location
  size                  = var.vm_size
  admin_username        = var.vm_admin_username
  network_interface_ids = [azurerm_network_interface.vm.id]
  tags                  = var.tags

  # key only: password login over SSH is impossible
  disable_password_authentication = true
  admin_ssh_key {
    username   = var.vm_admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    name                 = "${var.prefix}-vm-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  # First boot only: installs Docker and the compose plugin and creates /opt/app.
  # Changing cloud-init.yaml replaces the VM, which is safe because the VM holds no data:
  # the databases are in Azure SQL and the next deploy ships the app files again.
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    admin_username = var.vm_admin_username
  }))

  # serial console and boot screenshots in the portal, stored in a managed storage account
  boot_diagnostics {}
}
