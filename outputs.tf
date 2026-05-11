output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "datalake_account" {
  value = azurerm_storage_account.datalake.name
}

output "function_app_name" {
  value = azurerm_linux_function_app.transform.name
}

output "adf_name" {
  value = azurerm_data_factory.main.name
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database" {
  value = azurerm_mssql_database.contacts.name
}

output "event_hub_namespace" {
  value = azurerm_eventhub_namespace.main.name
}

output "app_insights_key" {
  value     = azurerm_application_insights.main.instrumentation_key
  sensitive = true
}

output "deploy_command" {
  value = "func azure functionapp publish ${azurerm_linux_function_app.transform.name}"
}