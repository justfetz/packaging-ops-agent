output "dataset_ids" {
  description = "Dataset IDs keyed by the name they were requested under."
  value       = { for k, d in google_bigquery_dataset.this : k => d.dataset_id }
}
