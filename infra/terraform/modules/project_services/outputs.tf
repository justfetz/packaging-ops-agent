output "enabled_services" {
  description = "The API service names that are enabled, for downstream depends_on."
  value       = [for s in google_project_service.this : s.service]
}
