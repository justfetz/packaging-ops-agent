# Credentials come from Application Default Credentials, or from the
# GOOGLE_OAUTH_ACCESS_TOKEN environment variable, which the Makefile sets from
# the short-lived token a Claude Code session already has. No key file.
provider "google" {
  project = var.project_id
  region  = var.region
}
