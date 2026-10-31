output "email" {
  description = "Service account email, for Cloud Run in M2."
  value       = google_service_account.this.email
}
