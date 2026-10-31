output "workload_identity_provider" {
  description = "Full provider resource name. The value for google-github-actions/auth's workload_identity_provider input."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "service_account_email" {
  description = "The value for google-github-actions/auth's service_account input."
  value       = google_service_account.ci.email
}
