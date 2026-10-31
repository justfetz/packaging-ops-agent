# 0007. GitHub Actions reaches GCP through Workload Identity Federation, as a plan-only identity

Date: 2026-10-31 · Status: Accepted

## Context

CI needs to talk to Google Cloud: first to run `terraform plan` against dev on every pull request so the owner reviews the plan and not just the HCL, later to run evals against BigQuery and Gemini. The plan rules out long-lived keys in CI, and the repo's only other identity with cloud access, the `deployer` service account, is Owner on the project and exists for applies, not for a job that any pull request can trigger.

GitHub Actions can mint an OpenID Connect (OIDC) token per job that states which repository, ref, and workflow it came from. Google's Workload Identity Federation accepts such tokens from a configured issuer, maps their claims to attributes, and lets a matching principal impersonate a service account for the life of the job. Google's own pipeline guidance is explicit that GitHub uses a single issuer for every account, so the provider must carry an attribute condition that pins the trust to one owner or repository, and recommends the numeric ID claims over names because a deleted name can be re-registered by someone else.

## Decision

Terraform declares, per environment, a Workload Identity Pool, an OIDC provider for `token.actions.githubusercontent.com` whose attribute condition requires `repository_owner_id` and `repository_id` to equal this repository's IDs, and a `github-ci` service account that only a principal from this repository (matched on `attribute.repository_id`) may impersonate. The account holds one role, `roles/viewer` on the project, which the first CI run showed is exactly what refreshing every resource in the root needs, state bucket and budget included, and nothing that changes one. A composite action, `.github/actions/gcp-auth`, wraps `google-github-actions/auth` with those two values, and the `terraform-plan` job in CI uses it to plan dev with `-lock=false` and post the result on the pull request. `main` is protected: a pull request and green checks are required, and the owner merges.

## Consequences

- **No credential exists to leak.** The job's token lives for the job. The secret-free property that CLAUDE.md promises for CI is now enforced by the absence of anything to store, not by a rule.
- **CI can look but not touch.** A pull request from this repository can show what an apply would do; it cannot apply, cannot write state, and holds nothing outside the project. Applies stay a session or owner task, which matches the "ask first" rules.
- **Every grant for this account stays at project level.** A resource-level binding, such as `objectViewer` on the state bucket, is a resource Terraform has to refresh, and refreshing it means reading that bucket's IAM policy, which needs `storage.buckets.getIamPolicy`, a permission no read-only role carries. The first CI run failed on exactly that and the binding came out. Project-level bindings refresh through `resourcemanager.projects.getIamPolicy`, which Viewer has.
- **The trust is pinned to IDs.** Renaming the repository or the owner changes nothing; deleting and recreating the repository under the same name breaks CI on purpose. The IDs sit in `terraform.tfvars` next to the project ID.
- **No billing-account role was needed.** The budget is a billing-account resource, and the expectation was that reading it would need `roles/billing.viewer` there, a grant only a Billing Account Administrator can make. The first CI run refreshed the budget with project Viewer alone, so that binding was dropped before it was ever applied, and with it the one manual step this design would have had.
- **Fork pull requests skip the plan.** A fork's job cannot get a token the pool trusts, so the job is skipped (a skipped required check does not block) and the owner reviews such a change without a plan.
- **A pool ID is reserved for 30 days after deletion.** A dev teardown and rebuild inside that window needs a new `pool_id` or an undelete. This is the one resource in dev that is not freely destroyable.
- **Later jobs reuse the same door.** An `apply` on `main` would be a second service account with write roles and a principal set filtered on `attribute.ref == "refs/heads/main"`, which is why `ref` is already mapped. Evals in CI (ADR 0004) reuse `gcp-auth` as is, plus BigQuery and Vertex AI roles on `github-ci`.
- **At client scale** the pool and provider move to a dedicated identity project, as Google recommends, with an organization policy that blocks pool creation elsewhere; the condition adds `ref` or `environment` claims per deployment stage; and the plan comment is replaced by a plan artifact that the apply job consumes unchanged.

## References

Fetched from `docs.cloud.google.com` and checked against the page text:

- Workload Identity Federation with deployment pipelines, GitHub Actions section: attribute mapping, the required attribute condition, and the `*_id` claims recommendation: https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- Workload Identity Federation concepts, including the 127-character limit on `google.subject`: https://docs.cloud.google.com/iam/docs/workload-identity-federation
- Best practices, "use attribute conditions when federating with GitHub" and the dedicated-project recommendation: https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation
- Billing roles, including that project-scoped billing information covers budgets: https://docs.cloud.google.com/billing/docs/how-to/billing-access
- Cloud Storage IAM roles: https://docs.cloud.google.com/storage/docs/access-control/iam-roles

Confirmed through search results that quote the page; `docs.github.com` and `github.com` release pages are not fetchable from a session:

- GitHub OIDC token reference, the `repository_id` and `repository_owner_id` claims and the immutable subject format for repositories created after July 15, 2026: https://docs.github.com/en/actions/reference/security/oidc
- GitHub REST API, update branch protection: https://docs.github.com/en/rest/branches/branch-protection
- `google-github-actions/auth` v3.0.0 (Node 24) and `actions/github-script` v8.0.0, pinned by commit SHA in the workflow: https://github.com/google-github-actions/auth/releases and https://github.com/actions/github-script/releases
