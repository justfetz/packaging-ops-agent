# CLAUDE.md

Guidance for Claude Code sessions in `packaging-ops-agent`. The repo is the project's memory: chats are temporary, so anything worth keeping gets committed. Read this file, then the issue you were given. Read `docs/PLAN.md` only when an issue points at it or a design question comes up.

## What this project is

A live, public agentic analytics app over a synthetic packaging supply chain, built on GCP, with evals as the headline. Anyone can ask a question and see the answer, the SQL, the sources, and the trace. A public scoreboard shows eval scores over time and the PRs the eval gate blocked. Every step is documented in `docs/build-log/`.

The full plan, milestones, and gates are in `docs/PLAN.md`. Current milestone: **M0 · Setup**.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 (pinned in `.python-version`), managed with `uv` |
| API and agent | FastAPI, LangGraph, Gemini via Vertex AI (Google renamed the product Gemini Enterprise Agent Platform in April 2026; the API is still `aiplatform.googleapis.com`) |
| Data | GCS landing zone, BigQuery warehouse, dbt (`dbt-bigquery` for dev and prod, `dbt-duckdb` for local and CI) |
| Vector search | BigQuery vector search and text search |
| Evals | pytest, DeepEval, custom code checks; golden set in `evals/golden.yaml` |
| Tracing | Langfuse |
| Serving | Docker, Artifact Registry, Cloud Run |
| Infrastructure | Terraform, dev and prod as separate roots; GitHub Actions with Workload Identity Federation |
| Secrets | Secret Manager. Never in code, env files, or chat |

One tool per layer. Do not add an alternative without an ADR. The reasoning behind each choice is in `docs/adr/`.

## Repo layout

```
app/              FastAPI service and LangGraph agent (Python package `app`)
data/             Seeded synthetic data generator, writes raw CSV and JSON to GCS
dbt/              dbt project: Bronze → Silver → Gold, tests, column descriptions
evals/            Golden set, eval runner, DeepEval metrics
infra/terraform/  Terraform modules and `envs/dev`, `envs/prod` roots
tests/            Unit tests (pytest)
docs/PLAN.md      The build plan
docs/adr/         Architecture decision records, one per major choice
docs/build-log/   One entry per milestone, written as the work happens
docs/source/      Source material, such as the original Gemini transcript
.github/workflows CI
```

Each directory has a README that says what belongs in it and which milestone fills it.

## Commands

```bash
make install   # uv sync --locked
make lint      # ruff check + ruff format --check
make format    # fix lint and reformat
make test      # pytest
make terraform-check  # terraform fmt -check + validate on both roots, no cloud access
make check     # lint + test + terraform-check, the same as CI
make run       # uvicorn on http://127.0.0.1:8080

make bootstrap ENV=dev   # once per environment: create the Terraform state bucket with gcloud
make plan ENV=dev        # terraform plan. Runs freely. PLAN_FLAGS="-out=plan.tfplan" saves it; make show-plan prints it
make apply ENV=dev       # terraform apply. ENV=prod also needs CONFIRM=prod and the owner's go-ahead
```

Planned for later milestones: `make eval` (M3). Always go through `make` rather than calling tools directly, so local runs and CI stay identical. `make check` needs Terraform at the version in `infra/terraform/.terraform-version`; in a Claude Code session install it the way `infra/terraform/README.md` describes.

## Coding standards

- Python 3.12, type hints on every public function, docstrings where the "why" is not obvious.
- `ruff` is the only linter and formatter. Config lives in `pyproject.toml`. Fix findings; do not add `noqa` without a reason in the comment.
- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Commit both. Use `uv add` so the lock stays in sync.
- Tools the agent calls are plain, typed Python functions with unit tests. The LLM chooses tools; it does not implement them.
- SQL that the agent generates must pass the guardrails in order: `sqlglot` parse, single `SELECT` only, allowlisted Gold tables only, enforced `LIMIT`, BigQuery dry run with `maximum_bytes_billed`.
- Prompts live in versioned files. The prompt version is logged on every trace.
- Deterministic settings (temperature 0) for SQL generation. The model is set in config so evals can compare models.
- Every technical claim in docs links to official documentation. Verify before writing; the plan flags unverified details in the source transcript. Google Cloud docs live at `docs.cloud.google.com` (reachable from a session). Other vendors' docs are not reachable from a session; say so in the doc when a link could only be confirmed through search results.

## How sessions work

- One GitHub issue per task. One session works one issue and opens one PR. Branch names are given by the session.
- Start by reading this file and the issue. Build, run `make check`, run evals once they exist, push, open the PR.
- PR description states the change, how it was tested, and the change in eval scores (once there are scores).
- Draft or update the milestone's `docs/build-log/` entry in the same PR: what was built, how, what broke, what you would change.
- Every build-log entry ends with an `## Owner notes` section. Claude creates it empty and never writes in it; the owner fills it before merge.
- Every bug found becomes a new golden question in `evals/golden.yaml` (from M3 on).
- CI must be green before merge. `main` is protected: changes arrive by pull request with the three CI checks (`Lint and test`, `Terraform fmt and validate`, `Terraform plan (dev)`) passing, and that applies to admins too. Claude never merges; the owner reviews and merges.

## Permissions and safety

- Run freely: `gcloud`, `bq`, `terraform plan`, `dbt build` against DuckDB or dev, tests, evals.
- Ask first: `terraform apply` to prod, anything that deletes data, anything that changes billing or IAM in prod.
- Dev can be torn down and rebuilt at any time.
- Keys and secrets never appear in code, env files committed to the repo, PR text, or chat. CI authenticates to GCP with Workload Identity Federation, not a stored key.
- Cost controls: Cloud Run scales to zero, BigQuery stays on on-demand pricing with byte caps, nothing always-on in the MVP. Budget ceiling of $25 per month with alerts at 50%, 90%, and 100%.

## GCP

Recorded by M0.2 (issue #3) and M0.3 (issue #4). Dev only for now; prod gets its own project later. Everything below the deployer identity is created by Terraform (`infra/terraform/`, [ADR 0006](docs/adr/0006-terraform-for-every-gcp-resource.md)).

| Setting | Value |
| --- | --- |
| Project ID | `packaging-ops-agent-dev` (project number `925041489941`) |
| Region | `us-central1` for every regional resource. BigQuery datasets use the `US` multi-region |
| Budget ceiling | $25 per month, alerts at 50%, 90%, and 100%, measured before credits. `google_billing_budget` in Terraform, scoped to the project |
| Gemini access | Vertex AI (`aiplatform.googleapis.com`), regional endpoint in `us-central1`. Starting default model `gemini-3.8-flash`, embeddings `gemini-embedding-001`, both set in config. `gemini-2.5-flash` retired on 2026-10-20; see ADR 0005 |
| Deployer identity | `deployer@packaging-ops-agent-dev.iam.gserviceaccount.com`. Owner on the project and Billing Account Costs Manager on the billing account. Used by sessions and by the owner for `apply`; CI never uses it. Narrowing it is still open |
| CI identity | `github-ci@packaging-ops-agent-dev.iam.gserviceaccount.com`. No key. `roles/viewer` on the project, `roles/storage.objectViewer` on the state bucket, `roles/billing.viewer` on the billing account: enough to `plan`, nothing that can `apply`. Impersonated only by GitHub Actions jobs from this repository, matched on repository ID, through Workload Identity Pool `github-actions`, provider `github-oidc` ([ADR 0007](docs/adr/0007-workload-identity-federation-for-ci.md)) |
| Agent identity | `agent-runtime@packaging-ops-agent-dev.iam.gserviceaccount.com`. No key. `roles/bigquery.jobUser` on the project and `roles/bigquery.dataViewer` on `gold` only |
| Terraform state | `gs://packaging-ops-agent-dev-tfstate`, object `default.tfstate` at the bucket root. Created by `make bootstrap`, not by Terraform |
| Landing bucket | `gs://packaging-ops-agent-dev-landing`, versioned, uniform access, public access prevented |
| BigQuery datasets | `bronze`, `silver`, `gold`, `evals` in the `US` multi-region |
| Session auth | The Claude Code environment injects a short-lived token for `*.googleapis.com` and sets `GCP_PROJECT_ID`. No key file exists in the sandbox. The Makefile hands the same token to Terraform through `GOOGLE_OAUTH_ACCESS_TOKEN` |

`gcloud`, `bq`, and `curl` against `*.googleapis.com` work in a session with no setup. Pass `--project "$GCP_PROJECT_ID"` explicitly; the sandbox has no default project configured.

CI authenticates differently. A job declares `permissions: id-token: write` and calls the composite action `.github/actions/gcp-auth`, which runs `google-github-actions/auth` with the pool provider and the CI service account. GitHub mints an OIDC token for the job, Google's Security Token Service checks it against the provider's condition (this repository's numeric ID and owner ID), and the job gets a short-lived token for `github-ci`. The action writes a credential file that the Terraform google provider, the GCS backend, `gcloud`, and `bq` all pick up as Application Default Credentials. Nothing is stored in GitHub: no secret, no key, no variable. The `terraform-plan` job uses this to plan dev with `-lock=false` on every pull request from this repository and posts the plan as a PR comment; fork PRs skip it. Any later CI job that needs GCP, such as evals, reuses the same action and adds roles to `github-ci` in Terraform.

Two session limits to know about. `registry.terraform.io` is not reachable, so Terraform and the google provider are installed from `releases.hashicorp.com` into the scratchpad with a filesystem mirror (steps in `infra/terraform/README.md`). And the session proxy decodes `%2F` in request paths, so a GCS object under a "folder" cannot be read or deleted by name through the JSON API from the sandbox; list and upload work, and the XML API path form works. Keep that in mind when M1 writes to the landing bucket.

## Definition of done

A change is done when all of these hold:

1. `make check` passes locally and CI is green on the PR.
2. New behavior has a unit test. Agent behavior changes have a golden question.
3. Eval gates still pass (from M3 on), and the PR description records the score change.
4. Docs that the change affects are updated in the same PR: this file, the directory README, the ADR, or the build log.
5. No secrets, keys, or project-specific values that belong in config were committed.
