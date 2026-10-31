# infra/terraform/

Terraform for every GCP resource. Shared modules under `modules/`, and one root per environment under `envs/dev` and `envs/prod`. Each root has its own state bucket (`backend.tfvars`) and its own values (`terraform.tfvars`). Decision record: [ADR 0006](../../docs/adr/0006-terraform-for-every-gcp-resource.md).

Filled in M0.3 (issue #4); the CI identity came in M0.4 (issue #5, [ADR 0007](../../docs/adr/0007-workload-identity-federation-for-ci.md)). Rules: `terraform plan` runs freely; `terraform apply` to prod needs the owner's go-ahead and `CONFIRM=prod`; dev can be destroyed and rebuilt at any time; no long-lived keys in the repo.

## Layout

```
.terraform-version          Pinned Terraform version. CI installs exactly this
modules/
  project_services/         google_project_service for every API the MVP uses
  landing_bucket/           Versioned, uniform-access GCS bucket for raw data and documents
  bigquery_datasets/        bronze, silver, gold, evals datasets
  agent_service_account/    Runtime identity: bigquery.jobUser on the project, dataViewer on gold only
  budget/                   google_billing_budget scoped to the project, thresholds at 50, 90, 100 %
  github_actions_ci/        Workload Identity Pool and GitHub OIDC provider, plus the plan-only CI service account
envs/dev/, envs/prod/
  versions.tf               Terraform and provider constraints
  backend.tf                GCS backend, configured from backend.tfvars
  backend.tfvars            State bucket name
  providers.tf              google provider
  variables.tf, main.tf, outputs.tf
  terraform.tfvars          Project ID, billing account, budget, destroyable flag, GitHub repository IDs
  .terraform.lock.hcl       Provider lock, committed
```

The two roots are identical apart from their tfvars. Keep them that way: a change to `main.tf` in one root goes into the other in the same PR.

## What one environment contains

| Resource | Dev value | Notes |
| --- | --- | --- |
| Enabled APIs | 14, listed in `main.tf` | Never disabled on destroy |
| Landing bucket | `gs://packaging-ops-agent-dev-landing` | `us-central1`, versioned, keeps 5 noncurrent versions, public access prevented |
| BigQuery datasets | `bronze`, `silver`, `gold`, `evals` | `US` multi-region |
| Agent service account | `agent-runtime@packaging-ops-agent-dev.iam.gserviceaccount.com` | No key. `roles/bigquery.jobUser` on the project, `roles/bigquery.dataViewer` on `gold` and nothing else |
| Budget | `packaging-ops-agent-dev monthly ceiling`, $25 | On the billing account, filtered to the project, measured before credits. Emails billing-account admins at 50, 90, and 100 % |
| Workload Identity Pool | `github-actions`, provider `github-oidc` | Issuer `token.actions.githubusercontent.com`. Condition: `repository_owner_id` and `repository_id` equal this repository's. A deleted pool keeps its ID for 30 days |
| CI service account | `github-ci@packaging-ops-agent-dev.iam.gserviceaccount.com` | No key. `roles/viewer` on the project only; that covers the state bucket and the budget. `roles/iam.workloadIdentityUser` granted to `principalSet://…/attribute.repository_id/1440268397` only |

`destroyable = true` in dev lets `terraform destroy` remove the bucket and datasets even when they hold data. Prod sets it to `false`.

## Commands

All through `make`, from the repo root:

```bash
make bootstrap ENV=dev        # once per environment: create the state bucket with gcloud
make plan ENV=dev             # init against the state bucket, then plan
make plan ENV=dev PLAN_FLAGS="-lock=false -out=plan.tfplan"   # what CI runs: read-only, saved to a file
make show-plan ENV=dev        # print that saved plan as plain text
make apply ENV=dev            # plan to a file, apply that file
make apply ENV=prod CONFIRM=prod   # only with the owner's explicit go-ahead
make terraform-check          # fmt -check and validate on both roots, no cloud access. Part of make check
```

Terraform cannot create the bucket that holds its own state, so `make bootstrap` creates it with `gcloud` (uniform access, public access prevented, versioning on). It is safe to rerun.

### Credentials

The google provider and the GCS backend use Application Default Credentials. In a Claude Code session there is no key file; the Makefile copies the session's short-lived token from `CLOUDSDK_AUTH_ACCESS_TOKEN` into `GOOGLE_OAUTH_ACCESS_TOKEN`, which both the provider and the backend accept. Locally, `gcloud auth application-default login` is enough.

In GitHub Actions the composite action `.github/actions/gcp-auth` obtains credentials through Workload Identity Federation and writes an external-account credential file that the provider and backend read as ADC. The values it needs are the two outputs of this root, `ci_workload_identity_provider` and `ci_service_account_email`, and they are the action's input defaults. The CI identity can only read, so CI plans with `-lock=false` and never applies.

### Why the CI identity has only project-level roles

A plan refreshes every resource in the root, including IAM bindings. Refreshing a project-level binding reads the project IAM policy, which `roles/viewer` allows. Refreshing a bucket-level binding reads that bucket's IAM policy, which needs `storage.buckets.getIamPolicy`, and no read-only role has it; the first CI run failed on exactly that. So anything granted to `github-ci` goes on the project, and the state bucket and the budget are read through Viewer, which the same run proved sufficient.

### Rebuilding dev

`terraform destroy` removes the pool and provider, but Google keeps a deleted pool's ID reserved for 30 days. A rebuild inside that window must either undelete the pool (`gcloud iam workload-identity-pools undelete github-actions --location=global`) before `make apply`, or use a different `pool_id`. Everything else in dev comes back as it was.

## Known limitation: object names with slashes from a session

The session's egress proxy decodes `%2F` in request paths, so a GCS JSON API call that names an object under a "folder" (`gs://bucket/a/b`) returns 404 from the sandbox even though the object exists. Listing works, uploads work, and BigQuery loads from GCS are server-side and unaffected. Reads and deletes by name from the sandbox work only through the XML API (`https://storage.googleapis.com/<bucket>/<object>`), whose paths carry literal slashes. This is why the state backend has no `prefix`: `default.tfstate` sits at the bucket root. Report it to the environment owner rather than working around it in code.

## Prod

The prod project does not exist yet. When it does: create it and link billing as in issue #3, grant the deployer identity Billing Account Costs Manager on the billing account, run `make bootstrap ENV=prod`, then `make plan ENV=prod`. Apply only with the owner's go-ahead.

## References

- Terraform on Google Cloud, root modules: https://docs.cloud.google.com/docs/terraform/best-practices/root-modules
- Storing Terraform state in Cloud Storage: https://docs.cloud.google.com/docs/terraform/resource-management/store-state
- Uniform bucket-level access: https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access
- Object versioning: https://docs.cloud.google.com/storage/docs/object-versioning
- Budgets, and the roles that manage them: https://docs.cloud.google.com/billing/docs/how-to/budgets and https://docs.cloud.google.com/billing/docs/how-to/billing-access
- Budget API fields, including `thresholdPercent` and credit treatment: https://docs.cloud.google.com/billing/docs/reference/budget/rest/v1/billingAccounts.budgets
- BigQuery roles (`dataViewer`, `jobUser`): https://docs.cloud.google.com/bigquery/docs/access-control
- Dataset-level IAM with Terraform: https://docs.cloud.google.com/bigquery/docs/control-access-to-resources-iam
- Enabling APIs: https://docs.cloud.google.com/service-usage/docs/enable-disable
- Service accounts: https://docs.cloud.google.com/iam/docs/service-accounts-create
- Workload Identity Federation with deployment pipelines (GitHub Actions): https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines
- Workload Identity Federation best practices: https://docs.cloud.google.com/iam/docs/best-practices-for-using-workload-identity-federation
