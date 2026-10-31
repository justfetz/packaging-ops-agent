# One dataset per medallion layer plus one for eval results. dbt owns the
# tables inside them; Terraform owns the datasets so their location, labels,
# and IAM survive a project rebuild.
resource "google_bigquery_dataset" "this" {
  for_each = var.datasets

  project     = var.project_id
  dataset_id  = each.key
  description = each.value
  location    = var.location

  # In dev a destroy must succeed even when dbt has filled the datasets.
  delete_contents_on_destroy = var.delete_contents_on_destroy

  labels = merge(var.labels, { layer = each.key })
}
