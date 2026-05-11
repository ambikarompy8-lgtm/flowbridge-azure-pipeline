terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
  # Uncomment to store state in Azure Blob (recommended for teams)
  # backend "azurerm" {
  #   resource_group_name  = "rg-terraform-state"
  #   storage_account_name = "stterraformstate"
  #   container_name       = "tfstate"
  #   key                  = "flowbridge.tfstate"
  # }
}

provider "azurerm" {
  features {
    resource_group { prevent_deletion_if_contains_resources = false }
    key_vault      { purge_soft_delete_on_destroy = true }
  }
}

# ── random suffix (makes resource names globally unique) ─────────────────
resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  suffix = random_id.suffix.hex
  tags = {
    project     = "FlowBridge"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ── resource group ────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = "rg-flowbridge-${var.environment}"
  location = var.location
  tags     = local.tags
}

# ── azure data lake storage gen2 ─────────────────────────────────────────
resource "azurerm_storage_account" "datalake" {
  name                     = "stfb${local.suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # ← enables ADLS Gen2 hierarchical namespace
  tags                     = local.tags

  blob_properties {
    delete_retention_policy { days = 7 }
  }
}

# medallion architecture containers
resource "azurerm_storage_container" "bronze" {
  name                  = "bronze"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "silver" {
  name                  = "silver"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "gold" {
  name                  = "gold"
  storage_account_name  = azurerm_storage_account.datalake.name
  container_access_type = "private"
}

# ── storage for function app internals ───────────────────────────────────
resource "azurerm_storage_account" "functions" {
  name                     = "stfbfn${local.suffix}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.tags
}

# ── log analytics workspace ───────────────────────────────────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-flowbridge-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# ── application insights (function monitoring) ────────────────────────────
resource "azurerm_application_insights" "main" {
  name                = "appi-flowbridge-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# ── azure function app ────────────────────────────────────────────────────
resource "azurerm_service_plan" "functions" {
  name                = "asp-flowbridge-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"  # consumption (serverless) plan
  tags                = local.tags
}

resource "azurerm_linux_function_app" "transform" {
  name                       = "fn-flowbridge-${local.suffix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key
  tags                       = local.tags

  site_config {
    application_stack { python_version = "3.11" }
  }

  app_settings = {
    FUNCTIONS_WORKER_RUNTIME       = "python"
    AzureWebJobsStorage            = azurerm_storage_account.datalake.primary_connection_string
    APPINSIGHTS_INSTRUMENTATIONKEY = azurerm_application_insights.main.instrumentation_key
    EVENT_HUB_CONN_STR             = azurerm_eventhub_namespace_authorization_rule.listen_send.primary_connection_string
    EVENT_HUB_NAME                 = azurerm_eventhub.contacts.name
    HUBSPOT_API_KEY                = var.hubspot_api_key
    XERO_CLIENT_ID                 = var.xero_client_id
    XERO_CLIENT_SECRET             = var.xero_client_secret
  }
}

# ── azure data factory ────────────────────────────────────────────────────
resource "azurerm_data_factory" "main" {
  name                = "adf-flowbridge-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags

  identity { type = "SystemAssigned" }  # managed identity for secure access
}

# grant ADF access to the data lake
resource "azurerm_role_assignment" "adf_storage" {
  scope                = azurerm_storage_account.datalake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_data_factory.main.identity[0].principal_id
}

# ── azure event hubs (real-time streaming) ────────────────────────────────
resource "azurerm_eventhub_namespace" "main" {
  name                = "evhns-flowbridge-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  capacity            = 1
  tags                = local.tags
}

resource "azurerm_eventhub" "contacts" {
  name                = "evh-contacts"
  namespace_name      = azurerm_eventhub_namespace.main.name
  resource_group_name = azurerm_resource_group.main.name
  partition_count     = 2
  message_retention   = 1
}

resource "azurerm_eventhub" "invoices" {
  name                = "evh-invoices"
  namespace_name      = azurerm_eventhub_namespace.main.name
  resource_group_name = azurerm_resource_group.main.name
  partition_count     = 2
  message_retention   = 1
}

resource "azurerm_eventhub_namespace_authorization_rule" "listen_send" {
  name                = "flowbridge-listen-send"
  namespace_name      = azurerm_eventhub_namespace.main.name
  resource_group_name = azurerm_resource_group.main.name
  listen              = true
  send                = true
  manage              = false
}

# ── azure sql server + database ───────────────────────────────────────────
resource "azurerm_mssql_server" "main" {
  name                         = "sql-flowbridge-${local.suffix}"
  resource_group_name          = azurerm_resource_group.main.name
  location                     = azurerm_resource_group.main.location
  version                      = "12.0"
  administrator_login          = var.sql_admin_username
  administrator_login_password = var.sql_admin_password
  tags                         = local.tags

  azuread_administrator {
    login_username = "AzureAD Admin"
    object_id      = var.aad_admin_object_id
  }
}

resource "azurerm_mssql_firewall_rule" "azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_mssql_database" "contacts" {
  name        = "db-contacts"
  server_id   = azurerm_mssql_server.main.id
  sku_name    = "Basic"  # ~$5/month; upgrade to S0+ for production
  max_size_gb = 2
  tags        = local.tags
}

# ── azure monitor alert: pipeline failure ─────────────────────────────────
resource "azurerm_monitor_action_group" "email" {
  name                = "ag-flowbridge-email"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "fb-email"

  email_receiver {
    name          = "admin"
    email_address = var.alert_email
  }
}


