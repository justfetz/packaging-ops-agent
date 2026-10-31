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

output "ci_workload_identity_provider" {
  description = "workload_identity_provider input for google-github-actions/auth in .github/actions/gcp-auth."
  value       = module.github_actions_ci.workload_identity_provider
}

output "ci_service_account_email" {
  description = "service_account input for google-github-actions/auth."
  value       = module.github_actions_ci.service_account_email
}
