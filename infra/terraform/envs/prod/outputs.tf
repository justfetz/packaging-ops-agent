output "project_id" {
  value = var.project_id
}

output "project_number" {
  value = data.google_project.this.number
}

output "landing_bucket" {
  description = "gs:// URL the data generator writes to."
  value       = module.landing_bucket.url
}

output "datasets" {
  description = "BigQuery dataset IDs by layer."
  value       = module.warehouse.dataset_ids
}

output "agent_service_account_email" {
  description = "Identity Cloud Run will run the agent as."
  value       = module.agent_service_account.email
}

output "budget_name" {
  value = module.budget.name
}
