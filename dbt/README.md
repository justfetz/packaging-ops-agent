# dbt/

dbt project modeling Bronze → Silver → Gold in BigQuery, with tests and column descriptions that double as the agent's semantic layer. One project, two targets: `dbt-bigquery` for dev and prod, `dbt-duckdb` for local runs and CI.

Filled in **M1 · Data**. Gold tables are listed in `docs/PLAN.md` under "Domain and data".
