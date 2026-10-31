# The landing zone for raw CSV and JSON from the data generator and for source
# documents. Versioned so a bad generator run can be rolled back, uniform
# bucket-level access so IAM is the only access model, and public access
# prevention because nothing in this bucket is meant to be served directly.
resource "google_storage_bucket" "this" {
  name     = var.name
  project  = var.project_id
  location = var.location

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy

  versioning {
    enabled = true
  }

  # Keep the version history bounded so versioning cannot quietly grow the bill.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = var.noncurrent_versions_to_keep
    }
  }

  labels = var.labels
}
