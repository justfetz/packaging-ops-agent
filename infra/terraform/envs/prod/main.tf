locals {
  labels = {
    app         = "packaging-ops-agent"
    environment = var.environment
    managed_by  = "terraform"
  }

  # Every API the MVP touches, plus the ones Terraform itself calls.
  services = [
    "aiplatform.googleapis.com",           # Gemini and embeddings via Vertex AI
    "artifactregistry.googleapis.com",     # container images
    "bigquery.googleapis.com",             # warehouse
    "billingbudgets.googleapis.com",       # the budget below
    "cloudbilling.googleapis.com",         # billing lookups
    "cloudresourcemanager.googleapis.com", # project lookups, used by the provider
    "iam.googleapis.com",                  # service accounts
    "iamcredentials.googleapis.com",       # service account impersonation for Workload Identity Federation
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",           # Cloud Run
    "secretmanager.googleapis.com", # secrets
    "serviceusage.googleapis.com",  # enabling the rest
    "storage.googleapis.com",       # landing bucket
    "sts.googleapis.com",           # token exchange for Workload Identity Federation
  ]


  datasets = {
    bronze = "Raw files loaded as-is from the landing bucket."
    silver = "Cleaned, typed, deduplicated tables."
    gold   = "Business-level facts and dimensions. The only dataset the agent can read."
    evals  = "Eval runs and scores, written by the eval runner."
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

module "project_services" {
  source     = "../../modules/project_services"
  project_id = var.project_id
  services   = local.services
}

module "landing_bucket" {
  source        = "../../modules/landing_bucket"
  project_id    = var.project_id
  name          = "${var.project_id}-landing"
  location      = var.region
  force_destroy = var.destroyable
  labels        = local.labels

  depends_on = [module.project_services]
}

module "warehouse" {
  source                     = "../../modules/bigquery_datasets"
  project_id                 = var.project_id
  datasets                   = local.datasets
  location                   = var.bigquery_location
  delete_contents_on_destroy = var.destroyable
  labels                     = local.labels

  depends_on = [module.project_services]
}

module "agent_service_account" {
  source              = "../../modules/agent_service_account"
  project_id          = var.project_id
  readable_dataset_id = module.warehouse.dataset_ids["gold"]

  depends_on = [module.project_services]
}

module "budget" {
  source             = "../../modules/budget"
  billing_account_id = var.billing_account_id
  project_number     = data.google_project.this.number
  display_name       = "${var.project_id} monthly ceiling"
  amount_usd         = var.budget_amount_usd
  threshold_percents = var.budget_threshold_percents

  depends_on = [module.project_services]
}

module "github_actions_ci" {
  source                     = "../../modules/github_actions_ci"
  project_id                 = var.project_id
  project_number             = data.google_project.this.number
  github_repository          = var.github_repository
  github_repository_id       = var.github_repository_id
  github_repository_owner_id = var.github_repository_owner_id

  depends_on = [module.project_services]
}
