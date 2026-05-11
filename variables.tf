variable "location" {
  default = "centralus"
}

variable "environment" {
  default = "dev"
}

variable "sql_admin_username" {
  default = "flowbridgeadmin"
}

variable "sql_admin_password" {
  sensitive = true
}

variable "aad_admin_object_id" {
  description = "Your Azure AD Object ID"
}

variable "alert_email" {
  default = "you@example.com"
}

variable "hubspot_api_key" {
  sensitive = true
  default   = ""
}

variable "xero_client_id" {
  sensitive = true
  default   = ""
}

variable "xero_client_secret" {
  sensitive = true
  default   = ""
}