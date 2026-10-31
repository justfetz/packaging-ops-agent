# infra/terraform/

Terraform for every GCP resource. Shared modules under `modules/`, and one root per environment under `envs/dev` and `envs/prod`. Each root has its own state bucket (`backend.tfvars`) and its own values (`terraform.tfvars`). Decision record: [ADR 0001](../../docs/adr/0001-terraform-for-every-gcp-resource.md).

Filled in M0.3 (issue #4). Rules: `terraform plan` runs freely; `terraform apply` to prod needs the owner's go-ahead and `CONFIRM=prod`; dev can be destroyed and rebuilt at any time; no long-lived keys in the repo.

## Layout

```
.terraform-version          Pinned Terraform version. CI installs exactly this
modules/
  project_services/         google_project_service for every API the MVP uses
  landing_bucket/           Versioned, uniform-access GCS bucket for raw data and documents
  bigquery_datasets/        bronze, silver, gold, evals datasets
  agent_service_account/    Runtime identity: bigquery.jobUser on the project, dataViewer on gold only
  budget/                   google_billing_budget scoped to the project, thresholds at 50, 90, 100 %
envs/dev/, envs/prod/
  versions.tf               Terraform and provider constraints
  backend.tf                GCS backend, configured from backend.tfvars
  backend.tfvars            State bucket name
  providers.tf              google provider
  variables.tf, main.tf, outputs.tf
  terraform.tfvars          Project ID, billing account, budget, destroyable flag
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

`destroyable = true` in dev lets `terraform destroy` remove the bucket and datasets even when they hold data. Prod sets it to `false`.

## Commands

All through `make`, from the repo root:

```bash
make bootstrap ENV=dev        # once per environment: create the state bucket with gcloud
make plan ENV=dev             # init against the state bucket, then plan
make apply ENV=dev            # plan to a file, apply that file
make apply ENV=prod CONFIRM=prod   # only with the owner's explicit go-ahead
make terraform-check          # fmt -check and validate on both roots, no cloud access. Part of make check
```

Terraform cannot create the bucket that holds its own state, so `make bootstrap` creates it with `gcloud` (uniform access, public access prevented, versioning on). It is safe to rerun.

### Credentials

The google provider and the GCS backend use Application Default Credentials. In a Claude Code session there is no key file; the Makefile copies the session's short-lived token from `CLOUDSDK_AUTH_ACCESS_TOKEN` into `GOOGLE_OAUTH_ACCESS_TOKEN`, which both the provider and the backend accept. Locally, `gcloud auth application-default login` is enough.

### Running from a Claude Code session

The session's network policy allows `releases.hashicorp.com` but not `registry.terraform.io`, so `terraform init` cannot fetch the provider the normal way. Install Terraform and the provider from the release host into the scratchpad and point Terraform at a filesystem mirror:

```bash
S=/path/to/scratchpad; V=$(cat infra/terraform/.terraform-version); PV=8.9.0
mkdir -p "$S/bin" "$S/mirror/registry.terraform.io/hashicorp/google"
curl -sSO "https://releases.hashicorp.com/terraform/$V/terraform_${V}_linux_amd64.zip"
curl -sSO "https://releases.hashicorp.com/terraform/$V/terraform_${V}_SHA256SUMS"
grep linux_amd64.zip "terraform_${V}_SHA256SUMS" | sha256sum -c - && unzip -q "terraform_${V}_linux_amd64.zip" -d "$S/bin"
curl -sS -o "$S/mirror/registry.terraform.io/hashicorp/google/terraform-provider-google_${PV}_linux_amd64.zip" \
  "https://releases.hashicorp.com/terraform-provider-google/$PV/terraform-provider-google_${PV}_linux_amd64.zip"
printf 'provider_installation {\n  filesystem_mirror { path = "%s/mirror" include = ["registry.terraform.io/hashicorp/*"] }\n  direct { exclude = ["registry.terraform.io/hashicorp/*"] }\n}\n' "$S" > "$S/terraformrc"
export PATH="$S/bin:$PATH" TF_CLI_CONFIG_FILE="$S/terraformrc"
```

Verify the provider zip against its `SHA256SUMS` file the same way. Nothing goes in the home directory; the session's sandbox refuses that.

### Provider lock file

`.terraform.lock.hcl` was generated from the filesystem mirror, so it records only the `h1:` hash for `linux_amd64`. CI runs on `linux_amd64` and verifies against that hash. On a Mac, run this once in each root and commit the result:

```bash
terraform -chdir=infra/terraform/envs/dev providers lock -platform=linux_amd64 -platform=darwin_arm64
```

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
