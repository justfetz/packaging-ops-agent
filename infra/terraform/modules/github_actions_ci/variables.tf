variable "project_id" {
  description = "Project that owns the pool, the provider, and the CI service account."
  type        = string
}

variable "project_number" {
  description = "Numeric project number, used in principalSet identifiers."
  type        = string
}

variable "github_repository" {
  description = "Repository allowed to authenticate, as owner/name. Recorded as a pool attribute for audit; the trust condition uses the numeric IDs below."
  type        = string
}

variable "github_repository_id" {
  description = "Numeric GitHub repository ID. Names can be reclaimed after a delete; IDs cannot, so the trust condition keys on this."
  type        = string
}

variable "github_repository_owner_id" {
  description = "Numeric GitHub ID of the repository owner (user or organization)."
  type        = string
}

variable "pool_id" {
  description = "Workload Identity Pool ID, 4 to 32 lowercase characters. A deleted pool keeps its ID reserved for 30 days."
  type        = string
  default     = "github-actions"
}

variable "provider_id" {
  description = "Workload Identity Pool Provider ID."
  type        = string
  default     = "github-oidc"
}

variable "account_id" {
  description = "CI service account ID, the part before the @. Must be 6 to 30 characters."
  type        = string
  default     = "github-ci"
}

variable "state_bucket" {
  description = "Terraform state bucket the CI identity may read, so `terraform plan` can load state."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account that holds this environment's budget. The CI identity needs to read the budget to plan it."
  type        = string
}
