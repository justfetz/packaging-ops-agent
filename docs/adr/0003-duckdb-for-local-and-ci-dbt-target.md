# 0003. DuckDB as the dbt target for local runs and CI

Date: 2026-10-31 · Status: Accepted

## Context

The dbt project models Bronze → Silver → Gold in BigQuery ([ADR 0001](0001-bigquery-over-databricks.md)). The plan wants `dbt build` to run on every PR as a gate, alongside unit tests and a fast eval subset ([docs/PLAN.md](../PLAN.md), "When evals run"). Running every PR against BigQuery would mean cloud credentials in every CI job before Workload Identity Federation exists (issue #5), a shared dev dataset that concurrent PRs would trample, and BigQuery bytes on every push. BigQuery itself has no local runtime to install.

## Decision

One dbt project with two targets in `profiles.yml`: `duckdb` for local runs and CI, `bigquery` for dev and prod. `dbt build` on DuckDB is the PR gate; `dbt build` on dev BigQuery runs on merge to main and nightly, where the full eval set also runs. Models are written in portable SQL, and anything dialect-specific goes through `adapter.dispatch` macros.

## Consequences

**Easier**

- **A PR gate with no cloud.** DuckDB is an in-process analytical database with no external dependencies and no server to install or maintain. `pip install` is the whole setup, and a CI runner with no GCP credentials can still build and test every model.
- **Fast feedback.** The synthetic dataset is small, so a full `dbt build` on DuckDB runs in seconds on a laptop or a GitHub Actions runner.
- **dbt tests run twice.** The same `unique`, `not_null`, `accepted_values`, and `relationships` tests run on DuckDB in the PR and on BigQuery after merge, so a data-quality regression is caught before merge and a dialect difference is caught right after.
- **Isolation.** Each PR builds its own DuckDB file. There is no shared dev dataset to collide on.

**Harder**

- **Two dialects.** BigQuery GoogleSQL and DuckDB SQL differ in functions, types, and quoting. Anything that is not portable (for example a BigQuery `STRUCT` or `ARRAY` idiom, or a date function) needs a dispatched macro with a `default__` and a `bigquery__` implementation. The rule is portable SQL first, macro second, and a dialect-specific model only with a comment saying why.
- **Green on DuckDB is not green on BigQuery.** The PR gate proves the models compile and the tests pass on DuckDB. Only the post-merge build proves them on BigQuery. A failure there is a bug that the PR gate could not see, and the build log should record each one.
- **Community adapter.** `dbt-duckdb` is a community-maintained adapter, not a dbt Labs one. It tracks dbt Core closely (1.11.1 on PyPI at the time of writing, against dbt Core 1.12.6), but upgrades need a check that both adapters still agree on the dbt Core version.
- **The eval numbers that matter come from BigQuery.** SQL execution accuracy in the PR eval subset runs against DuckDB, so a query that is correct on BigQuery but not DuckDB would score as wrong. The nightly run against dev BigQuery is the number the scoreboard shows.

**At client scale**

The pattern holds: the PR gate stays on an in-process engine, the warehouse builds on merge. What changes is that a client's models are larger and more dialect-specific, so the dispatched-macro layer grows and a sampled, anonymized subset of real data replaces the synthetic generator for the local target. A client already on dbt v2 (Fusion) gets DuckDB built in, with the caveat that the bundled driver cannot load DuckDB extensions.

## References

`docs.getdbt.com` and `duckdb.org` are not in the session's allowed network list, so these pages were confirmed through search results that quote them, not fetched directly. Package versions are from PyPI, which the session can reach.

- DuckDB adapter setup, community-maintained, repo at `duckdb/dbt-duckdb`: https://docs.getdbt.com/docs/core/connect-data-platform/duckdb-setup
- Community adapters list: https://docs.getdbt.com/docs/community-adapters
- `profiles.yml`: several targets per profile, selected with `--target`: https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml
- `adapter.dispatch` for macros with adapter-specific implementations: https://docs.getdbt.com/reference/dbt-jinja-functions/dispatch
- BigQuery adapter setup and authentication methods: https://docs.getdbt.com/docs/core/connect-data-platform/bigquery-setup
- Why DuckDB: in-process, no external dependencies, no server: https://duckdb.org/why_duckdb
- `dbt-duckdb` 1.11.1, `dbt-bigquery` 1.12.1, `dbt-core` 1.12.6, `duckdb` 2.0.0 on PyPI at the time of writing: https://pypi.org/project/dbt-duckdb/ · https://pypi.org/project/dbt-bigquery/ · https://pypi.org/project/dbt-core/ · https://pypi.org/project/duckdb/
