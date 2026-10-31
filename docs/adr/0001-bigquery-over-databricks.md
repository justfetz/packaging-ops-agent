# 0001. BigQuery over Databricks for the warehouse

Date: 2026-10-31 · Status: Accepted

## Context

The source transcript built the medallion layers (Bronze → Silver → Gold) on Databricks. The build plan replaced it with BigQuery and moved Databricks to separate study, outside this project ([docs/PLAN.md](../PLAN.md), "Changes from the Gemini plan"). The constraints that shaped the choice:

- **Budget.** The whole project runs under a $25 per month ceiling, and nothing may run always-on in the MVP (CLAUDE.md, "Cost controls").
- **One cloud.** Gemini, Cloud Run, GCS, Secret Manager, and Terraform state are all on GCP. A second vendor means a second account, a second IAM model, and a second bill.
- **Two kinds of retrieval, one store.** The agent needs SQL over Gold tables and vector plus text search over document chunks. Running a separate vector database would break the "one tool per layer" rule.
- **Hard cost caps per query.** The agent writes SQL. A bad query must fail cheaply, not run up a bill.

## Decision

The warehouse is BigQuery, on on-demand pricing, in the `US` multi-region. Databricks is not part of this build. DuckDB stands in for BigQuery locally and in CI (see [ADR 0003](0003-duckdb-for-local-and-ci-dbt-target.md)).

## Consequences

**Easier**

- Nothing to keep running. BigQuery is serverless, so an idle project costs only storage. The first 1 TiB of query bytes and the first 10 GiB of storage per month are free, which is more than this dataset will ever use. A Databricks SQL warehouse, by contrast, has an auto-stop timer with a floor of 10 minutes for pro and classic warehouses and 5 minutes for serverless ones, and an idle warehouse keeps accruing DBU and cloud instance charges until it stops. Databricks Free Edition avoids the bill but is limited to one 2X-Small warehouse and may not be used for commercial purposes, so it cannot host a public demo.
- A per-query spending cap that the agent's guardrail can set. `maximumBytesBilled` makes a query fail, without charge, if it would bill more than the limit. Dry runs are free and return the bytes a query would scan, so the guardrail can check cost before executing.
- Vector search and text search in the same SQL engine as the facts. `VECTOR_SEARCH` runs a brute-force exact search without an index and approximate nearest neighbor with one. `SEARCH` with a search index covers keyword retrieval. No extra database for the document corpus.
- One IAM model. The agent's read-only service account sees the Gold dataset and nothing else, using the same roles and Terraform provider as everything else in the project.

**Harder**

- BigQuery has no local runtime. Every `dbt-bigquery` run needs a project and credentials, which is why CI uses DuckDB and why SQL has to stay portable between the two dialects.
- Budget alerts inform, they do not stop spend. A Cloud Billing budget "doesn't automatically cap Google Cloud ... usage or spending", so the byte caps and the Gold-only service account are the real controls.
- The interview story the plan asks for ("why not Databricks") has to be answered on the merits of this project, not on a claim that BigQuery is better in general. It is cheaper at this size, and it is the platform named in the requirement; it is not a verdict on Databricks.

**At client scale**

On-demand per-TiB pricing stops being the cheap option once query volume is steady; the switch is to BigQuery editions with slot capacity, and the agent's byte caps become slot reservations and per-user quotas. If the client already runs Databricks, the dbt project moves to `dbt-databricks` with a different target and the same model code, and the agent's SQL tool points at a SQL warehouse instead, which makes the dbt layer the part of this design that survives a platform change.

## References

Fetched and checked in this session:

- BigQuery is serverless and fully managed: https://docs.cloud.google.com/bigquery/docs/introduction
- On-demand per-TiB pricing, first 1 TiB of queries and first 10 GiB of storage free each month: https://cloud.google.com/bigquery/pricing
- `maximumBytesBilled` fails a query without charge when it would exceed the limit: https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job#JobConfigurationQuery
- Dry runs are free and return the estimated bytes processed: https://docs.cloud.google.com/bigquery/docs/running-queries#dry-run
- `VECTOR_SEARCH` with and without a vector index (brute force versus approximate nearest neighbor): https://docs.cloud.google.com/bigquery/docs/vector-search
- `SEARCH` function and search indexes: https://docs.cloud.google.com/bigquery/docs/search
- Regions and multi-regions, including `US`: https://docs.cloud.google.com/bigquery/docs/locations
- Budgets do not cap spending: https://docs.cloud.google.com/billing/docs/how-to/budgets

Checked against official pages through search results only, because `docs.databricks.com` is not in the session's allowed network list:

- SQL warehouse auto-stop defaults and minimums, and idle warehouses accruing charges: https://docs.databricks.com/aws/en/compute/sql-warehouse/create
- SQL warehouse types (serverless, pro, classic): https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-types
- Free Edition limits (one 2X-Small warehouse, no commercial use, no SLA): https://docs.databricks.com/aws/en/getting-started/free-edition-limitations
