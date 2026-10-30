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

_Pending: filled in after the first run on the PR._

## What I would change

- Add `terraform fmt -check` and `dbt build` to CI as soon as #4 and M1 land, rather than letting CI stay Python-only for long.
- The PR comment with eval results (planned for M3) should reuse this workflow rather than a second one, so there is one CI file to read.

## Where M0 stands

| Issue | Status |
| --- | --- |
| #2 Repo scaffold | In PR |
| #3 GCP bootstrap | Waiting on Jason |
| #4 Terraform skeleton | Blocked on #3 |
| #5 WIF for CI | Blocked on #4 |
| #6 ADRs | Ready to start |
