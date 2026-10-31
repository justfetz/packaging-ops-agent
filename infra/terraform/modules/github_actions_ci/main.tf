# Lets GitHub Actions call Google Cloud with no stored key. A workflow asks
# GitHub for a short-lived OIDC token, Security Token Service checks that token
# against the pool provider below, and the workflow then impersonates the CI
# service account for the length of one job.
#
# Trust is pinned to one repository by numeric ID, not by name. GitHub lets a
# deleted owner or repository name be re-registered; the IDs are never reused.

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
  description               = "Federated identities for GitHub Actions workflows in ${var.github_repository}."
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.provider_id
  display_name                       = "GitHub OIDC"
  description                        = "Trusts tokens from token.actions.githubusercontent.com for one repository."

  # Every claim named in attribute_condition, or used in a principalSet, must
  # be mapped here. ref is mapped so a later apply job can be limited to main.
  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository"          = "assertion.repository"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.ref"                 = "assertion.ref"
  }

  # GitHub uses one issuer for every account, so the condition is what keeps
  # another repository's token out of this pool.
  attribute_condition = <<-EOT
    assertion.repository_owner_id == "${var.github_repository_owner_id}" &&
    assertion.repository_id == "${var.github_repository_id}"
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# The identity CI runs as. Read-only today: enough for `terraform plan`
# against this environment and nothing that could change it.
resource "google_service_account" "ci" {
  project      = var.project_id
  account_id   = var.account_id
  display_name = "GitHub Actions CI"
  description  = "Impersonated by GitHub Actions through Workload Identity Federation. Plans only."
}

# Only tokens from this repository (matched by ID, after the provider's
# condition has already passed) may impersonate the CI service account.
resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

# A plan refreshes every resource in the root, so CI needs to read all of
# them. roles/viewer is the read-only half of the project and grants nothing
# that mutates.
resource "google_project_iam_member" "viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = google_service_account.ci.member
}

# State lives in a bucket outside Terraform's control. Granting the read
# explicitly, rather than relying on roles/viewer covering objects, keeps the
# dependency visible. CI plans with -lock=false, so it never writes here.
resource "google_storage_bucket_iam_member" "state_reader" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = google_service_account.ci.member
}

# The budget is a billing-account resource, so roles/viewer on the project
# does not cover it. Billing Account Viewer is the smallest predefined role
# that carries billing.budgets.get; it reads cost data and changes nothing.
# Whoever applies this needs billing.accounts.setIamPolicy, which Billing
# Account Administrator has and Costs Manager does not, so the first apply is
# the owner's, not a session's.
resource "google_billing_account_iam_member" "budget_reader" {
  billing_account_id = var.billing_account_id
  role               = "roles/billing.viewer"
  member             = google_service_account.ci.member
}
