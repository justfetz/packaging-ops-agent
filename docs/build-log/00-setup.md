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

## Issue #4: the Terraform skeleton

The first infrastructure-as-code PR. Everything issue #3 did by hand, except the project itself and the deployer identity, is now declared under `infra/terraform/` and applied to dev. Decision record: [ADR 0006](../adr/0006-terraform-for-every-gcp-resource.md).

### What was built

- **Five small modules** (`project_services`, `landing_bucket`, `bigquery_datasets`, `agent_service_account`, `budget`) and **two roots**, `envs/dev` and `envs/prod`. The roots are identical except for `terraform.tfvars` and `backend.tfvars`.
- **Fourteen APIs** enabled as `google_project_service`, including the five that #3 enabled by hand and `iamcredentials`, which #5 needs for Workload Identity Federation. APIs are never disabled on destroy, so a dev teardown cannot break a service another resource still needs.
- **The landing bucket**, versioned with a lifecycle rule that keeps five noncurrent versions, uniform bucket-level access, public access prevention enforced.
- **Four BigQuery datasets** (`bronze`, `silver`, `gold`, `evals`) in the `US` multi-region. Dev sets `delete_contents_on_destroy`; prod does not.
- **The agent's runtime identity**, `agent-runtime@…`, with `roles/bigquery.jobUser` on the project and `roles/bigquery.dataViewer` on `gold` and nothing else. No key: Cloud Run will attach it in M2. `bq show` on `bronze` confirms the account does not appear there.
- **The $25 budget** as `google_billing_budget` on the billing account, filtered to the project number, thresholds at 50, 90, and 100 %, spend measured before credits so a free-trial credit cannot mask real usage.
- **`make bootstrap`, `make plan`, `make apply`, `make terraform-check`.** `apply` plans to a file and applies that file, so what runs is exactly what was shown. `apply` with `ENV=prod` refuses to run without `CONFIRM=prod`. `terraform-check` joined `make check`, and CI got a second job that installs the version pinned in `.terraform-version` straight from `releases.hashicorp.com` with a SHA256 check, then runs it.

### How it was tested

`make plan ENV=dev` (23 to add), `make apply ENV=dev` (23 added), then a second `make plan ENV=dev`: "No changes. Your infrastructure matches the configuration." After that, `gcloud billing budgets list`, `bq ls`, `bq show` on `gold` and `bronze`, `gcloud storage buckets describe`, and `gcloud projects get-iam-policy` confirmed each resource from outside Terraform. `make check` passes locally with the new Terraform step.

### What broke

- **`terraform init` could not reach the provider registry.** `registry.terraform.io` is not in the environment's allowed hosts; `releases.hashicorp.com` is. The provider binaries are also published on the release host, so the session downloaded Terraform 1.17.1 and `hashicorp/google` 8.9.0 from there, verified both against their `SHA256SUMS`, and pointed Terraform at a filesystem mirror with `TF_CLI_CONFIG_FILE`. The steps are in `infra/terraform/README.md`. A side effect: the committed lock file has only the `h1:` hash for `linux_amd64`, which CI uses; a Mac needs one `terraform providers lock` run, also documented there.
- **The first attempt at installing Terraform was refused by the sandbox** because it wrote to `~/.bashrc` and `~/.terraformrc`. Everything now lives in the session scratchpad. Worth remembering: install tools there, not in the home directory.
- **The first `make plan` failed with "Error loading state: <nil>"** after `init` had created `terraform/state/default.tfstate` in the bucket. `gcloud storage ls` showed the object; `gcloud storage cat` on it returned 404, and so did `gcloud storage rm`. A controlled test with `flat.txt` and `nested/deep.txt` isolated it: the session's egress proxy decodes `%2F` in request paths, so any JSON API call that names an object with a slash in it hits the wrong URL. Listing works (the name is a query parameter), uploads work, and the XML API works because its paths carry literal slashes. The fix for state was to drop the backend `prefix` so `default.tfstate` sits at the bucket root. The stale objects were deleted through the XML API. This one needs reporting to whoever owns the environment proxy; M1's data generator writes paths with slashes and will hit it the moment a session tries to read a file back.
- **The provider rejected the budget's `all_updates_rule`** unless it named a Monitoring channel or a Pub/Sub topic. The block is gone: with no rule set, budget emails go to the billing account's admins, which is the owner. A notification channel can be added when there is somewhere other than an inbox for it to go.
- **Service account IDs must be 6 to 30 characters.** `agent` was too short; it is `agent-runtime`.
- **Enabling Cloud Run created the default Compute Engine service account** in the project. Terraform does not manage it and it has no role bindings. Something to keep an eye on when #5 narrows IAM.

### Decisions recorded

- **State bucket per environment, created by `gcloud`, not Terraform.** The bootstrap chicken-and-egg problem is real, and a four-line `make bootstrap` is simpler than a second Terraform root to manage one bucket.
- **Budget filters on the project number, measured before credits.** The billing account also carries a `$15 Monthly Budget Alert` with no project filter, created by hand in #3. It is left alone; it is a billing-account-wide net, and the Terraform one is the per-project ceiling the plan asks for.
- **The deployer stays Owner for now.** Removing roles from the identity that runs Terraform, from inside a Terraform run, is a lockout waiting to happen. #5 creates the CI identity with only the roles it needs; the deployer can be narrowed by hand once CI no longer depends on it.

### References

- Root modules and environment separation: https://docs.cloud.google.com/docs/terraform/best-practices/root-modules
- State in Cloud Storage: https://docs.cloud.google.com/docs/terraform/resource-management/store-state
- Budget API, `thresholdPercent` and credit treatment: https://docs.cloud.google.com/billing/docs/reference/budget/rest/v1/billingAccounts.budgets
- BigQuery roles: https://docs.cloud.google.com/bigquery/docs/access-control
- Dataset-level IAM with Terraform: https://docs.cloud.google.com/bigquery/docs/control-access-to-resources-iam
- Uniform bucket-level access and object versioning: https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access, https://docs.cloud.google.com/storage/docs/object-versioning

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

- `terraform fmt -check` and `validate` are in CI as of #4. Add `dbt build` the same way the moment M1 lands, rather than letting CI lag the code.
- Have CI post the `terraform plan` output on PRs once #5 gives it an identity, so the owner reviews the plan, not just the HCL.
- The PR comment with eval results (planned for M3) should reuse this workflow rather than a second one, so there is one CI file to read.
- Add the other vendors' documentation hosts to the Claude Code environment's allowed domains (listed in `docs/adr/README.md`), so the "verify before writing" rule can be followed by fetching rather than searching.
- Treat the model ID as a dated value. Issue #3 verified `gemini-2.5-flash` on the day it was already past its retirement date. A short `make` target that prints the launch stage of the configured model would have caught it.

## Where M0 stands

| Issue | Status |
| --- | --- |
| #2 Repo scaffold | Merged in PR [#7](https://github.com/justfetz/packaging-ops-agent/pull/7), CI green |
| #3 GCP bootstrap | Project, billing, deployer, and environment verified from a session. The billing role is granted (the budget in #4 proves it). One owner step left: commit the Gemini transcript |
| #4 Terraform skeleton | Applied to dev: 23 resources, second plan clean, CI checks fmt and validate. Prod root exists and waits for a prod project |
| #5 WIF for CI | Ready to start. `iamcredentials` is enabled and the datasets, bucket, and agent identity it will reference exist |
| #6 ADRs | Merged in PR [#9](https://github.com/justfetz/packaging-ops-agent/pull/9): five records, linked from the README |

## Owner notes

- Most of the initial work is setup and plumbing. Lots to learn before a single line of the actual app exists.
- Setup order: GCP project first, then a Claude Code cloud environment. The environment holds the variables and the GCP secret, scoped to `*.googleapis.com`.
- I found it useful to keep one "main" chat for directional questions, and separate sessions for the work.
- Provenance matters: where did the idea come from and why. The Gemini transcript is in `docs/source/` for that reason.
- One session per issue. The container is built at the start, so if you add a variable afterwards the running session doesn't know.
- Terraform is the setup scope: GCP resources as files. I still have questions about what it does under the hood.
- Evals are the whole point of the project.
- Workload identity: CI proves who it is to Google with a GitHub token instead of a stored key. Still working through it.
- Issues are the project work. Chat is for discussion.
- Read every file added or removed in a PR.
- My own estimate to make something production-ready: 8 to 10 weeks.
- Gemini also said to keep practicing SQL and Python because top-tier shops still interview for it live. I agree. The plan for that is to write the M3 reference SQL by hand and to rewrite one function per PR myself before merging, rather than separate exercises.

### Why Terraform exists, as it was explained to me

I asked why Google can't just make its resources files, and whether Terraform is about version control. Google did make its own: Deployment Manager launched in 2015 and is now deprecated. Its replacement, Infrastructure Manager, is Google running Terraform for you, and Google co-maintains the Terraform Google provider. AWS has CloudFormation and Azure has Bicep, and both still live, but Terraform won anyway. Three reasons.

**One language for everything.** A real system is not only GCP. This project already has GCP resources, GitHub repository settings, and soon Langfuse and DNS. Terraform has a provider for each, so one plan can show a change that spans a BigQuery dataset and a GitHub branch rule. CloudFormation only knows AWS.

**The plan step.** Terraform compares the files to what exists and shows the diff before doing anything. That turns infrastructure changes into something you can review in a PR, the same as code. "7 to add, 0 to change, 0 to destroy" is the sentence that makes a reviewer comfortable.

**State.** Terraform remembers what it created, so it can detect drift when someone clicks in the console, and it can destroy exactly what it built and nothing else. That is what lets dev be torn down and rebuilt.

Version control is the enabler rather than the reason. Files in git give history, review, and rollback for free, but the point of the files is reproducibility: prod is dev with different variables, and a new project is `apply` rather than a day of clicking.

The lesson landed through our own M0. The service account and billing role I clicked in the console are the only resources Terraform does not know about, and when issue #5 wanted to narrow the deployer's roles it could not safely touch what it did not create. Clicking works once, leaves no record, cannot be reviewed, and cannot be repeated exactly.

### Local versus cloud sessions, as I understand it so far

| | Cloud session | Local session |
| --- | --- | --- |
| Runs on | An Anthropic VM that clones the repo from GitHub | My laptop, in my checkout |
| Credentials | What the environment holds: the deployer secret, proxied GitHub auth | Whatever I am logged into: my own gcloud account, SSH keys, Docker |
| Lifetime | Keeps running after I close the laptop | Stops when I close the terminal |
| Sees | Only what is committed and pushed | Uncommitted files, local databases, a browser I can open |
| Fits | "Work issue #N": autonomous, ends in a PR | Debugging, exploring, running the app and clicking on it |
