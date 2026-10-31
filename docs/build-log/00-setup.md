# 00 · Setup (M0)

_Started 2026-10-30. Draft written by Claude Code during the work; Jason edits it into his own voice._

## What this milestone is for

M0 exists so that every later change lands in a repo that already has a lint step, a test step, and a CI gate. The plan's gate for M0 is "CI green on an empty app". Everything else in M0 (GCP project, Terraform skeleton, Workload Identity Federation, the first ADRs) builds on that.

## Turning the milestone into issues

The plan says each milestone becomes a set of GitHub issues, and each issue is one Claude Code session and one PR. M0 became five:

| Issue | Task | Who |
| --- | --- | --- |
| [#2](https://github.com/justfetz/packaging-ops-agent/issues/2) | Repo scaffold: CLAUDE.md, layout, CI running lint and tests on an empty app | Claude (this entry) |
| [#3](https://github.com/justfetz/packaging-ops-agent/issues/3) | GCP project bootstrap: project, billing, budget alerts at $25 and $50, deployer service account, Claude Code environment | Jason (manual) |
| [#4](https://github.com/justfetz/packaging-ops-agent/issues/4) | Terraform skeleton: dev and prod roots, remote state, APIs, budget alerts as code | Claude |
| [#5](https://github.com/justfetz/packaging-ops-agent/issues/5) | GitHub Actions to GCP with Workload Identity Federation | Claude |
| [#6](https://github.com/justfetz/packaging-ops-agent/issues/6) | Foundational ADRs | Claude |

The split follows a dependency order: #3 is manual and unblocks #4, which unblocks #5. #2 and #6 have no cloud dependency, so they can go first.

## Issue #2: the scaffold

### Decisions made while building

- **uv for dependency management.** One tool for the interpreter, the virtualenv, and the lock file. `uv sync --locked` in CI fails if `uv.lock` drifts from `pyproject.toml`, which catches the "works on my machine" class of bug for free.
- **Python 3.12, not 3.13.** Pinned in `.python-version`. The dbt and Google Cloud client libraries that arrive in M1 and M2 have historically lagged the newest CPython by a few months, and the Cloud Run base images track the same cadence. 3.12 avoids finding that out the hard way.
- **ruff as the only linter and formatter.** It covers pycodestyle, pyflakes, isort, bugbear, pyupgrade, and simplify in one pass, so there is no black-vs-isort ordering to debug. Rule set is in `pyproject.toml`.
- **The "empty app" is a FastAPI app with one route, `GET /healthz`,** and one test that calls it. That is the smallest thing that exercises the import path, the test client, and the framework, and the health route is what Cloud Run will probe later anyway.
- **Everything goes through `make`.** CI calls `make install`, `make lint`, `make test`. Local runs call the same targets. The Makefile is the one place where tool invocations live, so CLAUDE.md can say "run `make check`" and mean exactly what CI does.
- **CLAUDE.md is written for the next session, not this one.** It has the stack, the layout, the commands, the standards, the permission rules, and the definition of done. The GCP table is left as "pending" on purpose, so #3 has a clear place to put the project ID, region, and budget ceiling.
- **Each layer directory has a README** saying what belongs there and which milestone fills it. An empty `dbt/` folder is a question; `dbt/README.md` is an answer.

### What broke

- **ruff reported the test's imports as unsorted** because `app` was not recognized as first-party. The first `src` setting listed the package directories themselves (`["app", "tests", ...]`), which tells ruff to look _inside_ `app/` for first-party modules instead of treating `app` as one. Setting `src = ["."]` fixed it.
- **Starlette 1.10 deprecates `httpx` for its test client** and asks for `httpx2` instead. The test passed with a warning. Swapping the dev dependency from `httpx` to `httpx2` removed the warning. Worth knowing in M2 when the API gets real endpoints and tests.
- **The GitHub Action versions I reached for first were two majors stale.** `actions/checkout` is on v7 and `astral-sh/setup-uv` is on v10. The plan's warning about unverified claims applies to CI pins too.
- **The first CI run failed in five seconds** with `Unable to resolve action astral-sh/setup-uv@v10`. setup-uv publishes only full version tags (`v10.3.3`), no floating `v10`, and its README pins by commit SHA with a version comment. The workflow now does the same: `astral-sh/setup-uv@68559e9… # v10.3.3`. `actions/checkout` does publish a floating `v7`, so it stays as is. Lesson: a release page showing "v10.3.3" does not mean `@v10` resolves. Check the tags page, or pin the SHA.
- setup-uv now caches by default on GitHub-hosted runners, so the explicit `enable-cache` input came out.
- **Resolved versions were newer than expected:** FastAPI 0.162, Starlette 1.10, pytest 9.2, ruff 0.17. Nothing in the scaffold depended on specifics, but it is a reminder to check versions rather than assume them.

### How it was tested

`make lint` and `make test` locally, then the CI workflow on the PR. The CI result and anything it caught are recorded below.

### CI result

| Run | Result | Time | Cause |
| --- | --- | --- | --- |
| 1 | Failed | 5 s | `astral-sh/setup-uv@v10` did not resolve (no floating major tag) |
| 2 | Passed | 9 s | Pinned setup-uv to the v10.3.3 commit SHA |

Run 2 is the M0 gate: CI green on an empty app. The nine-second wall time is the baseline to watch as dbt, Terraform checks, and evals join the workflow.

## Issue #3: the GCP project

This is the one owner-task in M0. Jason created the project, linked billing, created the `deployer` service account, and wired its key into the Claude Code environment as a network secret before the session started. The session's job was to verify the result from inside the sandbox, record the values, and find whatever the manual steps missed.

### What the session found

- **Auth works with no key in the sandbox.** The environment sets `GCP_PROJECT_ID` and `CLOUDSDK_AUTH_ACCESS_TOKEN`, and the agent proxy injects a short-lived token on every request to `*.googleapis.com`. `gcloud`, `bq`, and `curl` all work without configuration. `GOOGLE_APPLICATION_CREDENTIALS` is unset and there is no key file. This is what the issue's "no key in the sandbox" check was asking for.
- **The first `gcloud projects describe` failed anyway**, because a fresh project has the Cloud Resource Manager API disabled, and `gcloud` cannot describe a project without it. The same went for the Cloud Billing and IAM APIs. A new project ships with BigQuery, Cloud Storage, Logging, Monitoring, and a handful of others enabled, and not much else.
- **Enabled by the session:** `cloudresourcemanager`, `cloudbilling`, `billingbudgets`, `iam`, and `aiplatform`. All are APIs that Terraform in #4 needs anyway (the Google provider calls Resource Manager and IAM for almost everything, and the budget resource calls Billing Budgets). Enabling an API is free and reversible, and dev can be rebuilt at any time, so it fit the "run `gcloud` freely" rule. #4 should declare these as `google_project_service` resources so the list lives in code.
- **Billing is linked** (`billingEnabled: true`) and the project IAM has two owners: Jason and the `deployer` service account. The service account has exactly one user-managed key, created at 13:01 UTC on 2026-10-31, which matches the issue's "create one JSON key" step.
- **Gemini and embeddings are reachable in `us-central1`.** `GET publishers/google/models/gemini-2.5-flash` and `.../gemini-embedding-001` on the `us-central1` Vertex AI endpoint both return `launchStage: GA`. That settles the region question the issue left pending: `us-central1` for every regional resource, and the `US` multi-region for BigQuery datasets, so BigQuery and Vertex AI calls stay in the same geography.
- **BigQuery answers queries** (`SELECT 1` through `bq query`), so M1's `dbt-bigquery` target has nothing in the way.

### What is still blocked, and why

- **Budget alerts are not visible from the session.** `gcloud billing budgets list` on the billing account returns "The caller does not have permission". Project Owner says nothing about the billing account; budgets are a billing-account resource with their own roles. Before #4 can create the budget with Terraform, the `deployer` service account needs **Billing Account Costs Manager** (`roles/billing.costsManager`) on billing account `01B7CD-00412F-D365AB`, granted in the console under Billing → Account management. That role covers creating and listing budgets without granting the ability to change payment settings. The budget can also be created by hand in the console first for an earlier safety net; Terraform can import it later.
- **The Gemini transcript is not committed yet.** It is not in the repo or in Drive under any obvious name, so that step stays with Jason. `docs/source/README.md` already says where it goes.
- **Doc verification was impossible from the session.** The Google Cloud documentation now lives at `docs.cloud.google.com` (the `cloud.google.com/...` URLs 301-redirect there), and that host is not in the environment's allowed network list, so every fetch failed with a DNS error. CLAUDE.md requires every technical claim in docs to link to official documentation, which future sessions cannot verify until **`docs.cloud.google.com` is added to the environment's allowed domains**. The references below are the `cloud.google.com` URLs for the claims above, written from memory and not fetched; a human should click each once.

### Decisions recorded

- **Budget ceiling: $25 per month, alerts at 50%, 90%, and 100%.** The plan said "$25 and $50"; the issue tightened it to a single $25 ceiling with three thresholds, which is also how the Cloud Billing budget resource is shaped (one amount, several threshold rules). CLAUDE.md and the plan now say the same thing.
- **Gemini access through Vertex AI**, not AI Studio: the credentials are IAM, the models are regional, and spend lands on the same budget as everything else. The ADR is #6's job.
- **Region `us-central1`.** Confirmed empirically above rather than from the locations page, for the reason in the previous section.

### How it was tested

Every claim in "What the session found" is the output of a command run in the session: `gcloud projects describe`, `gcloud billing projects describe`, `gcloud iam service-accounts list` and `keys list`, `gcloud projects get-iam-policy`, `gcloud services list --enabled`, `bq query`, and two `curl` calls to the Vertex AI publisher model endpoint. `make check` still passes; this issue changed only docs.

### References

- Enabling APIs on a project: https://cloud.google.com/service-usage/docs/enable-disable
- Budgets and the roles that manage them: https://cloud.google.com/billing/docs/how-to/budgets and https://cloud.google.com/billing/docs/how-to/billing-access
- Vertex AI model locations: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations
- BigQuery dataset locations, including the `US` multi-region: https://cloud.google.com/bigquery/docs/locations

## Issue #6: the foundational ADRs

Five decision records in `docs/adr/`, written from the plan, the M0.2 findings, and the official docs. The hard part was not the writing; it was the verifying.

### What the records say

| ADR | Decision | The client-scale sentence |
| --- | --- | --- |
| [0001](../adr/0001-bigquery-over-databricks.md) | BigQuery over Databricks | On-demand per-TiB pricing gives way to editions and slot capacity; the dbt layer is what survives a platform change |
| [0002](../adr/0002-langgraph-state-machine-over-react-loop.md) | Explicit LangGraph graph over a ReAct loop | The graph is the governance artifact; scale adds nodes and a durable checkpointer, not a new pattern |
| [0003](../adr/0003-duckdb-for-local-and-ci-dbt-target.md) | DuckDB for local and CI dbt runs | Same pattern; the dispatched-macro layer grows and a sampled real subset replaces the synthetic generator |
| [0004](../adr/0004-evals-gate-every-pr.md) | Evals as a required PR check | Same gate; the golden set comes from real tickets and production traces, plus a no-regression margin |
| [0005](../adr/0005-gemini-via-vertex-ai.md) | Gemini through the Vertex AI API | Same decision with VPC Service Controls, CMEK, and Provisioned Throughput turned on |

### What the verification found

- **Vertex AI was renamed on April 22, 2026.** Google now calls it Gemini Enterprise Agent Platform, the Vertex AI docs are frozen, and the old URLs redirect to `docs.cloud.google.com/gemini-enterprise-agent-platform/...`. The endpoint (`aiplatform.googleapis.com`), the IAM permissions, and the SDK flag (`vertexai=True`) did not change. ADR 0005 records both names and the repo keeps saying "Vertex AI" for the API. The plan, written in October 2026, still used the old name, which is a small example of why the plan says to verify every claim.
- **The model issue #3 verified is already retired.** `gemini-2.5-flash` returned `launchStage: GA` from the `us-central1` endpoint on October 31, and still does, but Google's lifecycle page lists its retirement date as October 20, 2026, and the model page carries a retirement notice. The lifecycle page names `gemini-3.8-flash` or `gemini-3.5-flash-lite` as replacements; the session confirmed both are GA in `us-central1`, as is `gemini-3.5-flash`. CLAUDE.md now names `gemini-3.8-flash` as the starting default, in config, and M2 should treat the model ID as a value to re-check, not a constant.
- **The DeepEval metric the plan flagged.** DeepEval has no built-in answer-correctness class. Its RAG metrics are `FaithfulnessMetric`, `AnswerRelevancyMetric`, and the three `Contextual*` metrics; answer correctness is written as a custom `GEval` or, here, as a code check for expected facts. ADR 0004 says which.
- **`docs.cloud.google.com` is reachable now.** The M0.2 blocker is cleared: every Google Cloud link in the five records was fetched and the quoted claims checked against the page text. `cloud.google.com/...` URLs still redirect to the new host, so the records link to `docs.cloud.google.com` directly, except the pricing pages, which stay on `cloud.google.com`.
- **Every other vendor's docs are still unreachable.** `docs.langchain.com`, `docs.getdbt.com`, `duckdb.org`, `deepeval.com`, `docs.databricks.com`, and `docs.github.com` all fail DNS from the session. The workaround was web search restricted to each official domain, which returns the page title, URL, and quoted passages. Each ADR's References section says which links were fetched and which were confirmed that way, and `docs/adr/README.md` lists the hosts to add to the environment so a future session can fetch them. PyPI is reachable, so package names and versions in the records come from `pypi.org` directly.
- **The Databricks comparison is about this project, not Databricks.** ADR 0001 argues from the $25 budget and the one-cloud constraint: a SQL warehouse has an auto-stop floor and accrues charges while idle, Free Edition is non-commercial and capped at one 2X-Small warehouse, and BigQuery's on-demand tier plus `maximumBytesBilled` fits a public demo that must fail cheaply. It is not a claim that BigQuery is better in general, which is the honest version of interview story three.

### How it was tested

This issue changed only docs. `make check` passes. The Google Cloud references were fetched with `curl` and grepped for the quoted sentences; the model launch stages came from `GET .../publishers/google/models/{model}` on the `us-central1` endpoint; package versions came from the PyPI JSON API.

## What I would change

- Add `terraform fmt -check` and `dbt build` to CI as soon as #4 and M1 land, rather than letting CI stay Python-only for long.
- The PR comment with eval results (planned for M3) should reuse this workflow rather than a second one, so there is one CI file to read.
- Add the other vendors' documentation hosts to the Claude Code environment's allowed domains (listed in `docs/adr/README.md`), so the "verify before writing" rule can be followed by fetching rather than searching.
- Treat the model ID as a dated value. Issue #3 verified `gemini-2.5-flash` on the day it was already past its retirement date. A short `make` target that prints the launch stage of the configured model would have caught it.

## Where M0 stands

| Issue | Status |
| --- | --- |
| #2 Repo scaffold | Merged in PR [#7](https://github.com/justfetz/packaging-ops-agent/pull/7), CI green |
| #3 GCP bootstrap | Project, billing, deployer, and environment verified from a session. Two owner steps left: grant `deployer` Billing Account Costs Manager on the billing account, and commit the Gemini transcript |
| #4 Terraform skeleton | Ready to start once the billing role is granted (the budget resource needs it); everything else it needs is in place |
| #5 WIF for CI | Blocked on #4 |
| #6 ADRs | Five records written and linked from the README; this PR |
