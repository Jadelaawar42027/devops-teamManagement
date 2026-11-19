variable "prefix" {
  description = "Prefix of every resource name: the IE username with the dot replaced by a hyphen."
  type        = string
  default     = "jelaawar-ieu2023"
}

variable "location" {
  description = "Azure region for every resource."
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "Resource group that holds everything (the class one, e.g. rg-sdd-3a)."
  type        = string
}

variable "create_resource_group" {
  description = "true creates the resource group; false (the class setup) uses an existing one, which the service principal cannot create anyway."
  type        = bool
  default     = false
}

# --- network and VM ---

variable "vnet_cidr" {
  description = "Address space of the virtual network."
  type        = string
  default     = "10.20.0.0/16"
}

variable "subnet_cidr" {
  description = "Address range of the VM subnet."
  type        = string
  default     = "10.20.1.0/24"
}

variable "admin_cidr" {
  description = "The only source range allowed to reach SSH (through the load balancer's NAT rule on port 50022), e.g. your public IP as 203.0.113.7/32."
  type        = string

  validation {
    condition     = can(cidrhost(var.admin_cidr, 0)) && var.admin_cidr != "0.0.0.0/0"
    error_message = "admin_cidr must be a CIDR range and must not be 0.0.0.0/0."
  }
}

variable "vm_size" {
  description = "VM size. Standard_B2s: 2 vCPU, 4 GB RAM, enough for two gunicorn services and two nginx containers."
  type        = string
  default     = "Standard_B2s"
}

variable "vm_admin_username" {
  description = "Linux admin user on the VM."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "SSH public key (OpenSSH format) for the admin user. Password login is disabled."
  type        = string
}

# --- load balancer and DNS ---

variable "domain_name_label" {
  description = "DNS label of the public IP: gives <label>.<location>.cloudapp.azure.com."
  type        = string
  default     = "jelaawar-ieu2023"
}

variable "ssh_nat_port" {
  description = "Port on the load balancer that is forwarded to SSH (22) on the VM."
  type        = number
  default     = 50022
}

variable "lb_probe_path" {
  description = "HTTP path the load balancer probes on port 80. Answered by nginx itself, so the probe never wakes the databases (see deploy/nginx.conf)."
  type        = string
  default     = "/lb-probe"
}

variable "dns_zone_name" {
  description = "Azure DNS zone. Not delegated (no owned domain): resolve it against the zone's own name servers."
  type        = string
  default     = "jelaawar-ieu2023.devops.ie"
}

# --- SQL ---

variable "sql_admin_login" {
  description = "Admin login of the logical SQL server. Used only by the pipeline to create the per-service users, never by the apps."
  type        = string
  default     = "jelaawar_sqladmin"
}

variable "sql_admin_password" {
  description = "Admin password of the logical SQL server. Passed as TF_VAR_sql_admin_password from a GitHub secret; never in a file."
  type        = string
  sensitive   = true
}

variable "sql_sku_name" {
  description = "Serverless General Purpose Gen5 with at most 1 vCore."
  type        = string
  default     = "GP_S_Gen5_1"
}

variable "sql_min_capacity" {
  description = "Minimum vCores while the database is running (serverless)."
  type        = number
  default     = 0.5
}

variable "sql_auto_pause_delay_minutes" {
  description = "Minutes without activity before a serverless database pauses and stops billing compute. 15 is the shortest Azure allows (the brief asks for the shortest)."
  type        = number
  default     = 15

  validation {
    condition     = var.sql_auto_pause_delay_minutes >= 15
    error_message = "Azure's shortest auto-pause delay is 15 minutes."
  }
}

variable "sql_max_size_gb" {
  description = "Maximum size of each database."
  type        = number
  default     = 2
}

variable "tags" {
  description = "Tags on every resource that supports them."
  type        = map(string)
  default = {
    owner   = "jelaawar.ieu2023"
    project = "devops-teamManagement"
    managed = "terraform"
  }
}
