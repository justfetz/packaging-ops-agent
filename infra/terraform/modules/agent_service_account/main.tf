# The identity the agent runs as. It can run query jobs in the project and
# read exactly one dataset, Gold. It cannot see Bronze or Silver, cannot write
# anywhere, and has no key: Cloud Run attaches it at runtime.
resource "google_service_account" "this" {
  project      = var.project_id
  account_id   = var.account_id
  display_name = "Agent (read-only)"
  description  = "Runtime identity for the analytics agent. Reads the Gold dataset only."
}

# Running a query is a project-level permission (bigquery.jobs.create). It
# grants no access to data on its own.
resource "google_project_iam_member" "job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = google_service_account.this.member
}

# Data access is granted on the one dataset, not the project.
resource "google_bigquery_dataset_iam_member" "gold_viewer" {
  project    = var.project_id
  dataset_id = var.readable_dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = google_service_account.this.member
}
