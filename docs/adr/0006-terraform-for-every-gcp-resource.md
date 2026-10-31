# 0006. Terraform for every GCP resource, dev and prod as separate roots

Date: 2026-10-31 · Status: Accepted

## Context

The project needs a GCP footprint that can be rebuilt from nothing: dev is torn down when idle to save money, prod does not exist yet, and the plan's cost controls (a budget ceiling, scale-to-zero, byte caps) only hold if they are part of the definition rather than console clicks. Issue #3 created the project by hand and found that the budget it set up was invisible from a session, which is exactly the kind of drift the repo-as-memory rule is meant to prevent.

Constraints: one tool per layer, no long-lived keys in the repo, `terraform plan` must run from a Claude Code session with only a short-lived token, and prod changes need the owner's go-ahead.

## Decision

Every GCP resource is declared in Terraform under `infra/terraform/`, with shared modules and two root configurations, `envs/dev` and `envs/prod`, each with its own GCS state bucket and its own tfvars. Resources that exist outside a project but belong to it, such as the billing budget, are declared in the same root. The one exception is the state bucket itself, created once per environment by `make bootstrap` with `gcloud`, because Terraform cannot create the bucket that holds its own state.

## Consequences

- A rebuilt dev project is `make bootstrap ENV=dev` and `make apply ENV=dev`. The budget, the agent's narrow IAM, and the dataset layout come back with it.
- Two roots mean no workspace switching and no shared state between environments; a mistake in dev cannot touch prod state. The cost is that `main.tf` is duplicated, so a change to one root must be copied to the other in the same PR. A shared environment module would remove the duplication once the roots start to diverge.
- CI checks `terraform fmt` and `validate` on both roots with no cloud access. `plan` against real state stays a session or local task until issue #5 gives CI an identity through Workload Identity Federation.
- Backend blocks cannot read variables, so the state bucket name lives in `backend.tfvars` and the Makefile passes it with `-backend-config`.
- At client scale the same shape holds, with a root per environment and per project, state buckets locked down to the deployer identity, and `plan` output posted to the PR for review before `apply`.

## References

- Root modules, one per environment: https://docs.cloud.google.com/docs/terraform/best-practices/root-modules
- Storing state in Cloud Storage: https://docs.cloud.google.com/docs/terraform/resource-management/store-state
- Budgets are billing-account resources with their own roles: https://docs.cloud.google.com/billing/docs/how-to/billing-access
