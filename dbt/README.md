# dbt/

dbt project modeling Bronze → Silver → Gold, with tests and column descriptions that double as the agent's semantic layer. One project, two targets ([ADR 0003](../docs/adr/0003-duckdb-for-local-and-ci-dbt-target.md)): `duckdb` for local runs and CI, `dev` for BigQuery in `packaging-ops-agent-dev`. Prod gets a third output when the project exists.

Skeleton built in M1.2 (issue [#16](https://github.com/justfetz/packaging-ops-agent/issues/16)). The real models arrive in M1.3 (Bronze and Silver, [#17](https://github.com/justfetz/packaging-ops-agent/issues/17)) and M1.4 (Gold, [#18](https://github.com/justfetz/packaging-ops-agent/issues/18)); M1.5 ([#19](https://github.com/justfetz/packaging-ops-agent/issues/19)) runs the dev build on merge. Gold tables are listed in `docs/PLAN.md` under "Domain and data". Build log: [docs/build-log/01-data.md](../docs/build-log/01-data.md).

## Layout

```
dbt_project.yml       Project config. One schema per layer, materialization per layer
profiles.yml          The two targets. Committed: nothing in it is secret
models/sources.yml    The twelve raw feeds, defined once for both targets
models/bronze/        One model per raw feed, as close to the source as possible (M1.3)
models/silver/        Cleaned, typed, deduplicated entities (M1.3)
models/gold/          Facts and dimensions the agent queries (M1.4)
tests/                Singular tests, one file per assertion. The planted facts go here in M1.4
macros/               Shared macros. generate_schema_name puts each layer in its own schema
target/, logs/        dbt artifacts and the DuckDB file. Gitignored; `dbt clean` removes them
```

Each layer's folder has a `schema.yml` with the model and column descriptions and the generic tests. Today each folder holds one skeleton model (`smoke_bronze` → `smoke_silver` → `smoke_gold`, one row each) so the chain runs end to end on both targets; M1.3 and M1.4 replace them.

## Commands

All from the repo root, through `make`, which sets `DBT_PROJECT_DIR` and `DBT_PROFILES_DIR` to this directory:

```bash
make generate                    # the DuckDB target reads data/raw, so generate it first (about 20 s)
make dbt-build TARGET=duckdb     # build and test every model on DuckDB. What CI runs on every PR
make dbt-build TARGET=dev        # the same against BigQuery in packaging-ops-agent-dev
make dbt-docs TARGET=duckdb      # dbt docs generate into dbt/target; then: uv run dbt docs serve
uv run dbt show --target duckdb --inline "select count(*) from {{ source('raw', 'production_runs') }}"
```

`TARGET` defaults to `duckdb`. `RAW_DIR` (default `data/raw`) tells the DuckDB target where the raw files are, the same variable `make generate` writes to. Any other dbt command works the same way: `uv run dbt run --target dev --select silver`, `uv run dbt test --target duckdb`, `uv run dbt clean`.

### The `duckdb` target

In-process, no server. The database is one file, `dbt/target/packaging_ops.duckdb` (`DBT_DUCKDB_PATH` overrides it), and the three layers are schemas inside it. The raw feeds are not loaded; each source is a `read_csv` or `read_json` call over the files in `RAW_DIR`, through dbt-duckdb's `external_location` setting on the source (below). A full build of the skeleton takes about a second; the full raw set is 48.7 MB, so the real models will take seconds, not minutes.

### The `dev` target

BigQuery, project `packaging-ops-agent-dev`, location `US`. The three layers are the `bronze`, `silver`, and `gold` datasets Terraform created ([infra/terraform](../infra/terraform/README.md)); dbt owns the tables inside them and never creates a dataset. `maximum_bytes_billed` is 1 GB per query, so a bad model stops at a fraction of a cent on on-demand pricing. Before M1.3 loads the raw feeds into `bronze`, the sources exist only as definitions on this target; the skeleton models do not read them, which is why the dev build passes on an empty Bronze.

Credentials come from the environment, never from a file in the repo:

| Where | How dbt authenticates |
| --- | --- |
| A laptop | `method: oauth`, Application Default Credentials. `gcloud auth application-default login` once |
| GitHub Actions (M1.5) | The same `oauth` method. `.github/actions/gcp-auth` writes an external-account credential file through Workload Identity Federation, and the BigQuery client reads it as ADC |
| A Claude Code session | There is no ADC file in the sandbox, only the short-lived token in `CLOUDSDK_AUTH_ACCESS_TOKEN`. `profiles.yml` switches to `method: oauth-secrets` with that token when the variable is set, the same token the Makefile hands to Terraform. The session proxy injects the real credential on every call to `*.googleapis.com` |

### Sources

`models/sources.yml` defines the source `raw` once, with one table per feed the generator writes: `production_runs`, `stop_events`, `shift_summaries`, `order_lines`, `quality_tests`, and the seven `ref__` tables. The identifier is the file prefix (`raw__production_runs`, `ref__plants`), so the same name is the BigQuery table in `bronze` that M1.3's load creates, and the glob the DuckDB target reads:

| Target | `{{ source('raw', 'production_runs') }}` becomes |
| --- | --- |
| `dev` | `` `packaging-ops-agent-dev`.`bronze`.`raw__production_runs` `` |
| `duckdb` | `read_csv('data/raw/raw__production_runs__*.csv', header = true, union_by_name = true)` |

The DuckDB side is the `external_location` entry in each table's `config`, which dbt-duckdb substitutes for the relation when it renders `source()`; the BigQuery adapter ignores the setting. `{{ env_var('RAW_DIR', 'data/raw') }}` is rendered by dbt and `{identifier}` by dbt-duckdb. The JSON lines feeds use `read_json(..., format = 'newline_delimited')`. Types are inferred from the files today; M1.3 decides whether Bronze keeps them or reads everything as text and casts in Silver.

`tests/test_dbt_sources.py` renders every `external_location` the way dbt does, reads it with DuckDB, and checks the row count against the generator's manifest, so a renamed feed fails `make test` before it fails `make dbt-build`.

### Schemas

dbt's default puts a model with a custom schema in `<target schema>_<custom schema>`, which on BigQuery would be a dataset called `bronze_silver`. `macros/generate_schema_name.sql` overrides it to use the custom schema as-is, so `+schema: silver` in `dbt_project.yml` means the `silver` dataset on BigQuery and the `silver` schema in the DuckDB file. A model with no `+schema` lands in the target's own schema (`bronze` on `dev`, `main` on DuckDB); every layer folder sets one.

## CI

The job `dbt build (DuckDB)` in `.github/workflows/ci.yml` runs `make generate` and then `make dbt-build TARGET=duckdb` on every pull request and on every push to `main`, with no cloud access. It uploads `run_results.json` and `manifest.json` as a workflow artifact for a week. The branch ruleset requires it alongside the other three checks. The dev build on merge to `main` is M1.5.

## Conventions

- Portable SQL first. Anything dialect-specific goes through a macro with `adapter.dispatch`, with a `default__` and a `bigquery__` implementation, and a comment saying why (ADR 0003).
- Generic tests use the `arguments:` form (`accepted_values: {arguments: {values: [...]}}`); dbt 1.11 deprecated the bare form.
- Every model and column gets a description in its folder's `schema.yml`. From M1.4 on, a blank description fails the build; the agent reads these in M2.
- Lowercase keywords, one column per line, CTEs over subqueries.

## References

`docs.getdbt.com` and `duckdb.org` are not reachable from a Claude Code session (ADR 0003 notes the same), so the dbt and DuckDB behaviour above was confirmed against the installed adapter source (`dbt/adapters/duckdb/relation.py` for `external_location`, `dbt/adapters/bigquery/credentials.py` for the connection methods and `maximum_bytes_billed`) and by running both targets. The links are the pages that document it.

- dbt `profiles.yml`, targets, and `--target`: https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml
- dbt environment variables `DBT_PROJECT_DIR` and `DBT_PROFILES_DIR`: https://docs.getdbt.com/reference/global-configs/environment-variable-configs
- `generate_schema_name`: https://docs.getdbt.com/docs/build/custom-schemas
- dbt-duckdb, including `external_location` on sources: https://github.com/duckdb/dbt-duckdb
- DuckDB `read_csv` and `read_json`: https://duckdb.org/docs/stable/data/csv/overview · https://duckdb.org/docs/stable/data/json/overview
- dbt-bigquery authentication methods, `maximum_bytes_billed`, `location`: https://docs.getdbt.com/docs/core/connect-data-platform/bigquery-setup
- Application Default Credentials: https://docs.cloud.google.com/docs/authentication/application-default-credentials
- BigQuery `maximumBytesBilled` on a query job: https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/Job#JobConfigurationQuery
