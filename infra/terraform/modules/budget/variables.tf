variable "billing_account_id" {
  description = "Billing account ID in the form XXXXXX-XXXXXX-XXXXXX."
  type        = string
}

variable "project_number" {
  description = "Numeric project number the budget is scoped to."
  type        = string
}

variable "display_name" {
  description = "Budget name shown in the console."
  type        = string
}

variable "amount_usd" {
  description = "Monthly budget amount in whole US dollars."
  type        = number
}

variable "threshold_percents" {
  description = "Fractions of the amount at which to alert, such as 0.5 for 50%."
  type        = list(number)
  default     = [0.5, 0.9, 1.0]
}
