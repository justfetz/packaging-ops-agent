variable "project_id" {
  description = "Project that owns the service account."
  type        = string
}

variable "account_id" {
  description = "Service account ID, the part before the @. Must be 6 to 30 characters."
  type        = string
  default     = "agent-runtime"
}

variable "readable_dataset_id" {
  description = "The single BigQuery dataset the agent may read."
  type        = string
}
