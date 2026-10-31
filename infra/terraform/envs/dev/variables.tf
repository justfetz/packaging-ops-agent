variable "project_id" {
  description = "GCP project ID for this environment."
  type        = string
}

variable "environment" {
  description = "Short environment name used in labels and resource names: dev or prod."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod."
  }
}

variable "region" {
  description = "Region for every regional resource."
  type        = string
  default     = "us-central1"
}

variable "bigquery_location" {
  description = "Location for BigQuery datasets."
  type        = string
  default     = "US"
}

variable "billing_account_id" {
  description = "Billing account that the budget is created on."
  type        = string
}

variable "budget_amount_usd" {
  description = "Monthly budget ceiling in whole US dollars."
  type        = number
  default     = 25
}

variable "budget_threshold_percents" {
  description = "Fractions of the budget at which to send alerts."
  type        = list(number)
  default     = [0.5, 0.9, 1.0]
}

variable "destroyable" {
  description = "Allow destroy to remove buckets and datasets that still hold data. True in dev only."
  type        = bool
  default     = false
}
