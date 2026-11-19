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
  description = "The class's shared resource group, rg-sdd-3a or rg-sdd-3b (TODO: confirm). Only read, never created."
  type        = string
}

# --- the two services ---

variable "image_registry" {
  description = "Registry and namespace of the service images."
  type        = string
  default     = "ghcr.io/jadelaawar42027"
}

variable "image_tag" {
  description = "Tag of both images to run: the commit SHA, set by the pipeline."
  type        = string
}

variable "registry_username" {
  description = "Only for private GHCR packages: the GitHub user that owns the read token. Empty when the packages are public."
  type        = string
  default     = ""
}

variable "registry_password" {
  description = "Only for private GHCR packages: a token with read:packages. Empty when the packages are public."
  type        = string
  default     = ""
  sensitive   = true
}

variable "seed_demo" {
  description = "1 loads demo data into empty databases on start."
  type        = string
  default     = "1"
}

variable "kpi_db_password" {
  description = "Password of the contained database user kpi_svc. From a GitHub secret; stored as a Container App secret."
  type        = string
  sensitive   = true
}

variable "routing_db_password" {
  description = "Password of the contained database user routing_svc. From a GitHub secret; stored as a Container App secret."
  type        = string
  sensitive   = true
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
