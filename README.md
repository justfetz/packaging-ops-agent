# packaging-ops-agent

A live, public agentic analytics app over a synthetic packaging supply chain, built on GCP, with evals as the headline. Ask a question and get the answer, the SQL, the sources, and the trace. A public scoreboard shows eval scores over time and the PRs the eval gate blocked.

**Status:** M0 · Setup. Nothing is deployed yet.

- Build plan: [docs/PLAN.md](docs/PLAN.md)
- Build log: [docs/build-log/](docs/build-log/)
- Decision records: [docs/adr/](docs/adr/) · [BigQuery over Databricks](docs/adr/0001-bigquery-over-databricks.md) · [LangGraph over a ReAct loop](docs/adr/0002-langgraph-state-machine-over-react-loop.md) · [DuckDB for local and CI](docs/adr/0003-duckdb-for-local-and-ci-dbt-target.md) · [Evals gate every PR](docs/adr/0004-evals-gate-every-pr.md) · [Gemini via Vertex AI](docs/adr/0005-gemini-via-vertex-ai.md) · [Terraform for every GCP resource](docs/adr/0006-terraform-for-every-gcp-resource.md)
- Infrastructure: [infra/terraform/](infra/terraform/), dev applied, prod pending a project
- How Claude Code sessions work in this repo: [CLAUDE.md](CLAUDE.md)

## Run locally

```bash
make install
make check   # lint + tests + terraform fmt/validate, same as CI
make run     # http://127.0.0.1:8080/healthz
make plan ENV=dev   # terraform plan against the dev project
```

Requires [uv](https://docs.astral.sh/uv/) and [Terraform](https://developer.hashicorp.com/terraform/install) at the version in `infra/terraform/.terraform-version`. Python 3.12 is pinned in `.python-version` and uv installs it if missing.
