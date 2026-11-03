# 01 · Data (M1)

_Started 2026-10-31. Draft written by Claude Code during the work; Jason edits it into his own voice._

## What this milestone is for

M1 turns the plan's "synthetic packaging dataset" into something BigQuery can hold: a seeded generator writing raw files to the landing bucket, dbt models from Bronze to Gold with tests and column descriptions, and a DuckDB target so `dbt build` runs in CI without touching the cloud. The gate is "`dbt build` passes in CI and in dev". Everything the agent will answer in M2, and everything the evals will check in M3, is decided by the data shape and the planted facts chosen here.

## Turning the milestone into issues

| Issue | Task | Who |
| --- | --- | --- |
| [#14](https://github.com/justfetz/packaging-ops-agent/issues/14) | Domain spec: the fictional company, plants, machines, grades, customers, messiness, and twenty planted facts | Jason with Claude, merged in [#21](https://github.com/justfetz/packaging-ops-agent/pull/21) |
| [#15](https://github.com/justfetz/packaging-ops-agent/issues/15) | Seeded generator writing raw CSV and JSON lines to the landing bucket, with the planted facts realised and tested | Claude, merged in [#22](https://github.com/justfetz/packaging-ops-agent/pull/22) |
| [#24](https://github.com/justfetz/packaging-ops-agent/issues/24) | M1.1b: model wet-end change time explicitly in the raw run records and plant PF-21 | Claude, merged in [#25](https://github.com/justfetz/packaging-ops-agent/pull/25) |
| [#16](https://github.com/justfetz/packaging-ops-agent/issues/16) | M1.2: dbt project skeleton with DuckDB and BigQuery targets, `dbt build` in CI | Claude (this entry) |
| M1.3 to M1.5 | Bronze load and Silver rules with tests, Gold models and singular tests for the planted facts, the dev build on merge | Next |

The spec came first on purpose. A generator written before the spec would have planted whatever was convenient; the spec forced the generator to hit numbers somebody chose for a reason.

## Issue #15: the generator

### What was built

`data/generator/` is a Python package with a CLI (`python -m data.generator generate|check`) and three `make` targets: `generate`, `check-facts`, `upload`. It reads every number from `data/config.yaml` and the planted targets from `data/planted_facts.yaml`, and writes five raw feeds partitioned by month plus seven reference tables, flat in one directory, with a `manifest.json` carrying a SHA-256 per file and one combined checksum. For seed 42: 130 files, 317,157 rows, 48.5 MB, 18 seconds. The set is in `gs://packaging-ops-agent-dev-landing/` as of this PR. `data/README.md` documents every column, every messiness rule, and every planted fact.

### Decisions made while building

- **Calibrate, don't hope.** Twenty exact targets cannot come out of random draws. Every stage draws plausible values and then adjusts a group to its target: scale a list to an exact sum, pick exactly `round(n × rate)` records, or fit overlapping ratios iteratively (Atlanta waste by shift and ATL-C2 waste by cutoff share runs). The helpers live in `calibrate.py` and are the part of the code worth reading first.
- **Downtime is a budget, not a stream.** Each machine's total downtime follows from its uptime target. Planted events go in first (PM with a 92-minute mean, knife changes, the missplice schedule, Chicago's 1,840 stacker jams, the Atlanta boiler failures), then the companywide planned share is completed with order-change and no-orders stops, then unplanned filler brings each machine to its total. PF-03 and PF-17 fall out exactly, and the cause mix still looks like the spec's table.
- **The facts file is the contract.** `planted_facts.yaml` holds the expected value, a tolerance, and a one-paragraph definition for each measure. The generator reads the targets from it, `facts.py` recomputes the measures from the written files, and the test compares. M1.4's dbt singular tests and M3's golden questions should use the same definitions, so the three layers cannot drift apart silently.
- **The Silver rules are already written once, in Python.** To check a planted downtime count against raw files, something has to normalise 68 spellings, resolve `Other` through the comment, and fall back to the fault code. `facts.CauseNormaliser` does that, and it raises if any event is unrecoverable, which is how the generator proves the mess is fixable. M1.3 ports it to SQL.
- **One `random.Random` per stage**, seeded from the run seed and the stage name. Changing the quality module does not reshuffle production. The checksum test still changes on any edit, which is the point; the PR says why.
- **Flat file names with the month in them**, as the issue asked, because the session proxy cannot read an object under a "folder" back by name. The side effect is useful: partitioning by the arrival timestamp (`recorded_at`, `updated_at`, `emitted_at`) puts late-arriving records in a later month's file, which is the messiness the spec wanted.
- **Quality tests are per wet-end setup, not per dry-end run**, for ECT, and for moisture at Chicago; caliper and moisture elsewhere are per shift. The board does not change inside a setup, and "every run" at dry-end grain would have been 300,000 rows on its own. Pin adhesion is twice a shift rather than once, so PF-20's 5.6% has enough tests behind it to land within 0.1 points.
- **Feet are balanced across shifts.** After review, PF-08 moved to Atlanta 7.5, Chicago 16, PA 9, LA 10 changes per shift so the plants produce what the spec's throughput paragraph says. With that much production per shift the random spread of setup lengths overflowed shifts constantly, so the generator now scales each shift's setups to the time available (scheduled × uptime − 50 minutes of slack) before restoring the plant total. Feet move between shifts; the plant means (PF-07) do not change.

### What broke

- **The spec's numbers did not all fit together.** Section 3 said a 110" machine runs 200,000 to 400,000 lineal feet a shift. PF-07 and PF-08 fixed Atlanta at 3.2 setups of 38,500 feet, about 123,000 feet a shift, and Chicago at about 105,000. Both could not hold, and the first cut left every shift with 250 to 300 unaccounted minutes. Jason resolved it in review by moving PF-08 (Atlanta 7.5, Chicago 16, PA 9, LA 10) and giving the 98" specialty machines their own range (120,000 to 200,000). Atlanta, PA, and LA now carry about 50 unaccounted minutes a shift. Chicago cannot get there: PF-11 pins its speeds and PF-07 with PF-08 pins its feet, and 16 setups of 9,200 feet take under 300 minutes at 400 to 780 fpm, so it keeps about 135 minutes between setups. Closing that would mean moving PF-07, PF-08, or PF-11 for Chicago.
- **Sorting stop events by offset crashed** once two stops in one run drew the same offset: the tuple sort fell through to comparing the events. Sort by the offset alone.
- **Order-change stops at Chicago blew the uptime budget.** 11.4 wet-end changes a shift at 3 to 8 minutes each is 60 minutes of planned downtime before anything breaks, which alone puts Chicago under 88% and makes PA's 95.8% impossible at its own change rate. Resolved by treating a grade change as a stop only on hard transitions into or out of double wall and E flute, which is also how a splicer-equipped corrugator behaves.
- **The 60-second floor on run time moved the Chicago speed means** by 6 feet per minute after calibration, because short runs got clamped. The calibration now iterates against the rounded seconds.
- **The fixed-time boiler stop landed at the wrong time on ATL-C2.** The timeline placed fixed events only inside runs; when 09:15 fell in a gap between runs the event slid to the next run start. Gaps now place fixed events at their clock time.
- **A YAML flow mapping ate a comma.** `notes: The volume grade, about 40% of all lineal feet` inside `{ … }` became two keys. Quoted every value with a comma. Worth remembering for `evals/golden.yaml`.
- **PF-20 could not be hit with one pin adhesion test per shift.** About 390 tests in a quarter means one failure is 0.26 points; the target tolerance is 0.1. Two tests a shift fixed it without changing the spec's "per shift" reading much.
- **`gsutil ls` returns 401 in a session** even though `gcloud storage ls` works, because gsutil does not read the token the environment injects. The issue's done-when said `gsutil ls`; `gcloud storage ls` is what the README and Makefile use.
- **The raw set came out at 50.2 MB** on the first full run. Dropping a redundant setup id from the quality feed, trimming trailing zeros, and taking a mid-run ECT only on setups over 25,000 feet brought it to 47.1 MB.

### How it was tested

`tests/test_generator.py` generated the full set once per session into a temp directory (about 20 seconds) and then: compared all 50 measures of the 20 facts against `planted_facts.yaml`; asserts the combined checksum for seed 42; checks size and row counts; checks each messiness item is present at its configured rate, including unaccounted minutes per shift under 60 at three plants; and regenerates once more to prove byte-identical output for the same seed. 33 tests, 42 seconds. `make check-facts` against `data/raw` prints the same comparison. The upload was verified with `gcloud storage ls` and by reading `manifest.json` back from the bucket.

## Issue #24: wet-end change time, M1.1b

### Why

The #15 review left every machine-shift with minutes that were neither running time nor a logged stop: Atlanta 46, PA 48, LA 54, Chicago 135. Divided by the wet-end changes per shift (7.5, 9, 10, 16) that is 5 to 8.4 minutes per change at every plant, which is what a splice or width change costs at crawl speed. Jason's call in #24: that is the expensive change the spec's section 5 describes, so model it and name it rather than minimise it. Chicago losing over two hours a shift to transitions is the Chicago story in one number.

### What was built

- `setup_minutes` on `raw__production_runs`: the wet-end change time of the setup, on its first run, 0 on the runs that follow. One decimal. The clock agrees with it: the first run starts that many minutes after whatever came before, less any logged stop in between. M1.4 rolls it into `fct_wet_end_runs`.
- **PF-21**: Chicago loses about 135 minutes per machine-shift to wet-end changes, Atlanta about 45. In `planted_facts.yaml`, the spec's table, `facts.py`, and the test. 21 facts now.
- Spec section 5 has a change-time paragraph: 5 to 10 minutes at crawl speed, neither a logged stop nor production at rate, longest for specialty transitions at Chicago.
- The timeline gives each setup a floor of 1.5 to 3 minutes and then a weighted share of the shift's idle time (specialty transitions 1.6, width resets 1.25), scaled per plant to the target. What little is left sits at the end of the shift as unlogged micro-stops.
- `tests/test_generator.py` replaces the under-60 and under-150 unaccounted-minutes test with two: the plant mean per change is between 5 and 10 minutes with Chicago highest and no change under the floor, and the shift reconciles to within a minute once change time is counted.

### Decisions made while building

- **PF-21 is derived, and the file says so.** Scheduled minutes less the stops the uptime allows (PF-03) less the running time the feet take at the derived speeds (PF-07, PF-08, PF-11) is change time. The generator can hand that time to the changes but cannot invent more, so the fact's tolerance is 0.5 minutes rather than 0.05 and the definition explains why. The issue said Atlanta 46; that was 45.5 rounded, and the floors in full shifts cost a few tenths, so the fact says 45 and the data gives 45.0. Chicago lands on 134.9 against 135.
- **Downtime now comes before the feet.** The first cut gave every change a floor and the shift's leftover time, and a third of the changes at Atlanta, PA, and LA came out under 3 minutes while Chicago's were fine. The cause was ordering: feet were balanced across shifts before any stop existed, so a shift that then drew the weekly PM or a long breakdown had no idle time left and ran late. The generator now sizes every stop and gives it a shift first, balances each shift's feet to what it has left, and only then attaches stops to runs (`downtime.attach_stops`). Late shifts fell from 10 to 15% to 2 to 6% at every plant, the per-shift spread of idle time fell by two thirds, and the change-time distribution is unimodal: Chicago has nothing under 3 minutes and 71% between 5 and 10. No pinned fact moved.
- **Allocation never exceeds a shift's idle time.** Rounding change time to tenths of a minute at plant level handed some shifts a few seconds more than they had. At Chicago, where changes take all the idle time, those seconds had nowhere to go and carried from shift to shift for good; 17% of Chicago shifts were running late before the per-shift cap went in. The plant total is now met by handing spare tenths only to shifts with room.
- **The balancer's speed estimate matches the speed stage.** It lacked Atlanta's third-shift factor, which put 12 minutes of systematic error into every Atlanta night shift.

### What broke

- The first version of the overrun check counted a shift as late when its last run ended after the shift, and ignored the stops after the last run, so it reported three quarters of shifts late at every plant. Counting stops as activity gave the real numbers in the table below.
- Placing the no-orders waits in light shifts, which seemed the obvious fix for LA's spread, did nothing, because at that point in the pipeline the unplanned filler did not exist yet and every shift looked equally light. Reordering the filler ahead of the flex did not help either; the per-shift variance was the filler itself. Both changes were backed out in favour of building all downtime before the feet.

| Plant | Idle minutes per shift (mean, sd) before | after | Late shifts before | after |
| --- | --- | --- | --- | --- |
| Atlanta | 45.5, 37.5 | 45.5, 17.6 | 15% | 6% |
| Chicago | 134.9, 40.5 | 134.9, 7.4 | 1% | 2% |
| PA | 48.1, 33.3 | 47.9, 14.8 | 10% | 4% |
| LA | 53.6, 43.9 | 53.6, 10.8 | 14% | 3% |

### How it was tested

All 21 facts hold under `make check-facts` and in `tests/test_generator.py`, which now has 35 tests. The seed-42 set is 130 files, 317,032 rows, 48.7 MB; the checksum is re-pinned. `make check` passes, and the set is re-uploaded to the dev landing bucket with `make upload ENV=dev`.

## Issue #16: the dbt skeleton, M1.2

### What was built

`dbt/` is a dbt Core 1.12 project with `dbt-duckdb` 1.11 and `dbt-bigquery` 1.12 as dev dependencies, two targets in a committed `profiles.yml`, the twelve raw feeds defined once as sources, one skeleton model per layer (`smoke_bronze` → `smoke_silver` → `smoke_gold`, one row each) with generic tests on every column and one singular test, and `make dbt-build TARGET=duckdb|dev` plus `make dbt-docs`. CI gained a fourth job, `dbt build (DuckDB)`, that generates the raw set and builds on DuckDB with no cloud access. `dbt/README.md` documents both targets and how each one authenticates.

### Decisions made while building

- **Sources are the file prefix on both targets.** The source identifier is `raw__production_runs` or `ref__plants`, the same string as the file name before the month. On BigQuery that is the table M1.3's load creates in `bronze`; on DuckDB it is the glob in the `external_location` that dbt-duckdb substitutes for the relation (`read_csv('data/raw/raw__production_runs__*.csv', ...)`). One definition, nothing branches on the target name in the models, and the BigQuery adapter never sees the DuckDB setting. `RAW_DIR` reaches the yaml through `env_var`, so the tests can point the sources at a temporary set.
- **The skeleton models do not read the sources.** The `bronze` dataset is empty until M1.3 loads it, and the issue asked for the dev build to pass now. A bronze model over a source would have passed on DuckDB and failed on dev, or needed a load this issue does not own (M1.3 chooses between `bq load` and external tables). So the chain starts from a literal row, and the sources are proven another way: `tests/test_dbt_sources.py` renders every `external_location` as dbt would and reads it with DuckDB, and the row counts match the manifest for all twelve feeds (317,032 rows).
- **One schema per layer, by overriding `generate_schema_name`.** dbt's default would have put `+schema: silver` into a `bronze_silver` dataset. The override uses the custom name as-is, so the three datasets Terraform created are the three layers, and dbt never creates a dataset.
- **Session auth without a key file.** The sandbox has no Application Default Credentials, only the short-lived token in `CLOUDSDK_AUTH_ACCESS_TOKEN`. `profiles.yml` picks `oauth-secrets` with that token when the variable is set and plain `oauth` (ADC) otherwise, which is the same split the Makefile already makes for Terraform. A laptop and CI never see the branch.
- **A byte cap from day one.** `maximum_bytes_billed: 1000000000` on the dev target. Issue #19 asks for it in M1.5; it costs nothing to set now, and the whole raw set is under 50 MB.
- **`make` sets `DBT_PROJECT_DIR` and `DBT_PROFILES_DIR`**, so `uv run dbt <anything>` works from the repo root without `--project-dir` flags, and the DuckDB file and the source globs resolve against the repo root. Running dbt from inside `dbt/` would not find the raw files; the README says to go through `make`.

### What broke

- **dbt 1.11 deprecated the bare `accepted_values: {values: [...]}` form.** The first build passed with six deprecation warnings; the tests now use `arguments:`. Worth knowing before M1.3 writes dozens of them.
- **DuckDB 2.0 removed `fetchone()` on relations.** The source test used it; `fetchall()` is the replacement. Nothing in the dbt build touched it.
- **`docs.getdbt.com`, `duckdb.org`, and `github.com/duckdb/dbt-duckdb` are not reachable from a session**, as ADR 0003 found. The behaviour the README describes was confirmed in the installed adapter source and by running it, and the links are given for the reader.

### How it was tested

`make dbt-build TARGET=duckdb` on freshly generated data: 3 models, 19 generic tests, 1 singular test, 0.8 seconds after a 2-second parse. `make dbt-build TARGET=dev` from the session against BigQuery: the same 23 nodes in 20 seconds, `smoke_bronze` a view in `bronze`, `smoke_silver` and `smoke_gold` tables in `silver` and `gold`, confirmed with `bq ls` and a query. `dbt show --inline` over all twelve sources on DuckDB returned the manifest's row counts exactly. `make dbt-docs` writes `index.html` and `catalog.json`. `make test` runs 48 tests including the 13 new source checks, and `make check` passes with the pinned Terraform.

The new CI job must be added to the branch ruleset's required checks by the owner; the job name is `dbt build (DuckDB)`.

## What I would change

- Chicago's 135 minutes a shift now say "the plant" rather than "the generator", and PF-21 names them. The number is still a consequence of PF-07, PF-08, and PF-11; if a golden question ever asks how long a Chicago change takes, the answer is 8.4 minutes, and only moving one of those facts changes it.
- Shifts that run late are now 2 to 6%; the rest of the spread is unplanned stops drawn after the feet were set. Making a late shift shed feet instead would mean a wet-end run spanning shifts, which the spec rules out.
- Stop events have no `run_id`; Silver joins by time. That is realistic and it is also the first place the dbt work will hurt. If it takes more than an afternoon, add the id to the feed and note it.
- `facts.py` reads every file with the `csv` module in two seconds. Once dbt exists, the same checks should run against DuckDB so there is one implementation of each rule, not two.
- The dbt skeleton proves the plumbing, not the data. The first real models in M1.3 will be the first time a source is read on BigQuery, and the Bronze load choice (`bq load` into native tables, or external tables over the bucket) decides whether Bronze is cheap to rebuild or free to rebuild. Native tables are the simpler story for `make load`, external tables mean no copy and no stale Bronze.
- The customer assignment is random within a plant. If the document corpus (M4) wants "the furniture maker buys 51 ECT BC", the generator needs a grade affinity per customer. Small change, do it when a golden question needs it.

## Where M1 stands

| Issue | Status |
| --- | --- |
| #14 Domain spec | Merged in [#21](https://github.com/justfetz/packaging-ops-agent/pull/21) |
| #15 Generator | Merged in [#22](https://github.com/justfetz/packaging-ops-agent/pull/22). Raw set in the dev landing bucket, tests in CI |
| #24 Wet-end change time | Merged in [#25](https://github.com/justfetz/packaging-ops-agent/pull/25). `setup_minutes` in the run feed, PF-21, 21 facts hold, set re-uploaded |
| #16 dbt skeleton | This PR. Two targets, sources for all twelve feeds, skeleton chain green on DuckDB and dev, `dbt build (DuckDB)` in CI |
| M1.3 Bronze and Silver | Not started. The rules are listed in `data/README.md` |
| M1.4 Gold | Not started. The fact definitions are in `data/planted_facts.yaml` |
| M1.5 Dev build on merge | Not started |

## Owner notes
