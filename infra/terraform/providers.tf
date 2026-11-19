terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81"
    }
  }

  # Remote state in an Azure storage account (created once by hand, see infra/bootstrap.md).
  # Left empty on purpose: the pipeline passes resource_group_name, storage_account_name,
  # container_name and key with -backend-config, so no account names live in the code.
  # The state file holds the SQL admin password in plain text, which is why it must never
  # be local or committed (.gitignore blocks *.tfstate).
  backend "azurerm" {}
}

provider "azurerm" {
  features {}

  # The service principal is Contributor on the resource group only, so it cannot register
  # resource providers on the subscription; the ones used here are already registered.
  resource_provider_registrations = "none"

  # Credentials come from ARM_CLIENT_ID, ARM_CLIENT_SECRET, ARM_TENANT_ID and
  # ARM_SUBSCRIPTION_ID, set by the pipeline from GitHub secrets.
}
