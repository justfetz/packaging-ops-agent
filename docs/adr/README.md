# Architecture decision records

One short record per major choice. Number them in order (`0001-...md`). Keep each under a page, link every technical claim to official documentation, and answer "what would change at client scale" in a sentence or two.

## Records

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-bigquery-over-databricks.md) | BigQuery over Databricks for the warehouse | Accepted |
| [0002](0002-langgraph-state-machine-over-react-loop.md) | An explicit LangGraph state machine over a ReAct loop | Accepted |
| [0003](0003-duckdb-for-local-and-ci-dbt-target.md) | DuckDB as the dbt target for local runs and CI | Accepted |
| [0004](0004-evals-gate-every-pr.md) | Evals gate every PR | Accepted |
| [0005](0005-gemini-via-vertex-ai.md) | Gemini through the Vertex AI API, not the Gemini Developer API | Accepted |
| [0006](0006-terraform-for-every-gcp-resource.md) | Terraform for every GCP resource, dev and prod as separate roots | Accepted |
| [0007](0007-workload-identity-federation-for-ci.md) | GitHub Actions reaches GCP through Workload Identity Federation, as a plan-only identity | Accepted |

## Template

```markdown
# NNNN. Title

Date: YYYY-MM-DD · Status: Accepted | Superseded by NNNN

## Context
What question had to be answered, and what constraints shaped it.

## Decision
What was chosen, in one or two sentences.

## Consequences
What gets easier, what gets harder, and what would change at client scale.

## References
Links to official docs that back the claims above.
```

## Verifying links from a session

CLAUDE.md requires every technical claim to link to official documentation, verified before writing. From a Claude Code session only `docs.cloud.google.com` and `pypi.org` are reachable; `docs.langchain.com`, `docs.getdbt.com`, `duckdb.org`, `deepeval.com`, `docs.databricks.com`, and `docs.github.com` are not in the environment's allowed network list. Each record says which of its references were fetched and which were confirmed only through search results that quote the page. Adding those hosts to the environment lets a future session fetch them directly.
