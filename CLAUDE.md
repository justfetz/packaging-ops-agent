# CLAUDE.md

Guidance for Claude Code sessions in `packaging-ops-agent`. The repo is the project's memory: chats are temporary, so anything worth keeping gets committed. Read this file, then the issue you were given. Read `docs/PLAN.md` only when an issue points at it or a design question comes up.

## What this project is

A live, public agentic analytics app over a synthetic packaging supply chain, built on GCP, with evals as the headline. Anyone can ask a question and see the answer, the SQL, the sources, and the trace. A public scoreboard shows eval scores over time and the PRs the eval gate blocked. Every step is documented in `docs/build-log/`.

The full plan, milestones, and gates are in `docs/PLAN.md`. Current milestone: **M0 · Setup**.

## Stack

| Layer | Choice |
| --- | --- |
| Language | Python 3.12 (pinned in `.python-version`), managed with `uv` |
| API and agent | FastAPI, LangGraph, Gemini via Vertex AI |
| Data | GCS landing zone, BigQuery warehouse, dbt (`dbt-bigquery` for dev and prod, `dbt-duckdb` for local and CI) |
| Vector search | BigQuery vector search and text search |
| Evals | pytest, DeepEval, custom code checks; golden set in `evals/golden.yaml` |
| Tracing | Langfuse |
| Serving | Docker, Artifact Registry, Cloud Run |
| Infrastructure | Terraform, dev and prod as separate roots; GitHub Actions with Workload Identity Federation |
| Secrets | Secret Manager. Never in code, env files, or chat |

One tool per layer. Do not add an alternative without an ADR.

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
make check     # lint + test, the same as CI
make run       # uvicorn on http://127.0.0.1:8080
```

Planned for later milestones: `make eval` (M3) and `make plan ENV=dev|prod` (M0.3). Always go through `make` rather than calling tools directly, so local runs and CI stay identical.

## Coding standards

- Python 3.12, type hints on every public function, docstrings where the "why" is not obvious.
- `ruff` is the only linter and formatter. Config lives in `pyproject.toml`. Fix findings; do not add `noqa` without a reason in the comment.
- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. Commit both. Use `uv add` so the lock stays in sync.
- Tools the agent calls are plain, typed Python functions with unit tests. The LLM chooses tools; it does not implement them.
- SQL that the agent generates must pass the guardrails in order: `sqlglot` parse, single `SELECT` only, allowlisted Gold tables only, enforced `LIMIT`, BigQuery dry run with `maximum_bytes_billed`.
- Prompts live in versioned files. The prompt version is logged on every trace.
- Deterministic settings (temperature 0) for SQL generation. The model is set in config so evals can compare models.
- Every technical claim in docs links to official documentation. Verify before writing; the plan flags unverified details in the source transcript.

## How sessions work

- One GitHub issue per task. One session works one issue and opens one PR. Branch names are given by the session.
- Start by reading this file and the issue. Build, run `make check`, run evals once they exist, push, open the PR.
- PR description states the change, how it was tested, and the change in eval scores (once there are scores).
- Draft or update the milestone's `docs/build-log/` entry in the same PR: what was built, how, what broke, what you would change.
- Every bug found becomes a new golden question in `evals/golden.yaml` (from M3 on).
- CI must be green before merge. Claude never merges; the owner reviews and merges.

## Permissions and safety

- Run freely: `gcloud`, `bq`, `terraform plan`, `dbt build` against DuckDB or dev, tests, evals.
- Ask first: `terraform apply` to prod, anything that deletes data, anything that changes billing or IAM in prod.
- Dev can be torn down and rebuilt at any time.
- Keys and secrets never appear in code, env files committed to the repo, PR text, or chat. CI authenticates to GCP with Workload Identity Federation, not a stored key.
- Cost controls: Cloud Run scales to zero, BigQuery stays on on-demand pricing with byte caps, nothing always-on in the MVP. Budget ceiling of $25 per month with alerts at 50%, 90%, and 100%.

## GCP

Recorded by M0.2 (issue #3). Dev only for now; prod gets its own project later.

| Setting | Value |
| --- | --- |
| Project ID | `packaging-ops-agent-dev` (project number `925041489941`) |
| Region | `us-central1` for every regional resource. BigQuery datasets use the `US` multi-region |
| Budget ceiling | $25 per month, alerts at 50%, 90%, and 100%. Defined in Terraform (issue #4) |
| Gemini access | Vertex AI (`aiplatform.googleapis.com`), regional endpoint in `us-central1` |
| Deployer identity | `deployer@packaging-ops-agent-dev.iam.gserviceaccount.com`. Owner for now; #4 narrows it |
| Session auth | The Claude Code environment injects a short-lived token for `*.googleapis.com` and sets `GCP_PROJECT_ID`. No key file exists in the sandbox |

`gcloud`, `bq`, and `curl` against `*.googleapis.com` work in a session with no setup. Pass `--project "$GCP_PROJECT_ID"` explicitly; the sandbox has no default project configured. CI uses Workload Identity Federation instead (issue #5).

## Definition of done

A change is done when all of these hold:

1. `make check` passes locally and CI is green on the PR.
2. New behavior has a unit test. Agent behavior changes have a golden question.
3. Eval gates still pass (from M3 on), and the PR description records the score change.
4. Docs that the change affects are updated in the same PR: this file, the directory README, the ADR, or the build log.
5. No secrets, keys, or project-specific values that belong in config were committed.
