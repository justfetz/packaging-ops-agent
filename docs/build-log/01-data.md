# 01 · Data (M1)

_Started 2026-10-31. Draft written by Claude Code during the work; Jason edits it into his own voice._

## What this milestone is for

M1 turns the plan's "synthetic packaging dataset" into something BigQuery can hold: a seeded generator writing raw files to the landing bucket, dbt models from Bronze to Gold with tests and column descriptions, and a DuckDB target so `dbt build` runs in CI without touching the cloud. The gate is "`dbt build` passes in CI and in dev". Everything the agent will answer in M2, and everything the evals will check in M3, is decided by the data shape and the planted facts chosen here.

## Turning the milestone into issues

| Issue | Task | Who |
| --- | --- | --- |
| [#14](https://github.com/justfetz/packaging-ops-agent/issues/14) | Domain spec: the fictional company, plants, machines, grades, customers, messiness, and twenty planted facts | Jason with Claude, merged in [#21](https://github.com/justfetz/packaging-ops-agent/pull/21) |
| [#15](https://github.com/justfetz/packaging-ops-agent/issues/15) | Seeded generator writing raw CSV and JSON lines to the landing bucket, with the planted facts realised and tested | Claude (this entry) |
| M1.2 to M1.4 | Bronze load, Silver rules and tests, Gold models and singular tests for the planted facts | Next |

The spec came first on purpose. A generator written before the spec would have planted whatever was convenient; the spec forced the generator to hit numbers somebody chose for a reason.

## Issue #15: the generator

### What was built

`data/generator/` is a Python package with a CLI (`python -m data.generator generate|check`) and three `make` targets: `generate`, `check-facts`, `upload`. It reads every number from `data/config.yaml` and the planted targets from `data/planted_facts.yaml`, and writes five raw feeds partitioned by month plus seven reference tables, flat in one directory, with a `manifest.json` carrying a SHA-256 per file and one combined checksum. For seed 42: 130 files, 305,046 rows, 47.1 MB, 18 seconds. The set is in `gs://packaging-ops-agent-dev-landing/` as of this PR. `data/README.md` documents every column, every messiness rule, and every planted fact.

### Decisions made while building

- **Calibrate, don't hope.** Twenty exact targets cannot come out of random draws. Every stage draws plausible values and then adjusts a group to its target: scale a list to an exact sum, pick exactly `round(n × rate)` records, or fit overlapping ratios iteratively (Atlanta waste by shift and ATL-C2 waste by cutoff share runs). The helpers live in `calibrate.py` and are the part of the code worth reading first.
- **Downtime is a budget, not a stream.** Each machine's total downtime follows from its uptime target. Planted events go in first (PM with a 92-minute mean, knife changes, the missplice schedule, Chicago's 1,840 stacker jams, the Atlanta boiler failures), then the companywide planned share is completed with order-change and no-orders stops, then unplanned filler brings each machine to its total. PF-03 and PF-17 fall out exactly, and the cause mix still looks like the spec's table.
- **The facts file is the contract.** `planted_facts.yaml` holds the expected value, a tolerance, and a one-paragraph definition for each measure. The generator reads the targets from it, `facts.py` recomputes the measures from the written files, and the test compares. M1.4's dbt singular tests and M3's golden questions should use the same definitions, so the three layers cannot drift apart silently.
- **The Silver rules are already written once, in Python.** To check a planted downtime count against raw files, something has to normalise 68 spellings, resolve `Other` through the comment, and fall back to the fault code. `facts.CauseNormaliser` does that, and it raises if any event is unrecoverable, which is how the generator proves the mess is fixable. M1.3 ports it to SQL.
- **One `random.Random` per stage**, seeded from the run seed and the stage name. Changing the quality module does not reshuffle production. The checksum test still changes on any edit, which is the point; the PR says why.
- **Flat file names with the month in them**, as the issue asked, because the session proxy cannot read an object under a "folder" back by name. The side effect is useful: partitioning by the arrival timestamp (`recorded_at`, `updated_at`, `emitted_at`) puts late-arriving records in a later month's file, which is the messiness the spec wanted.
- **Quality tests are per wet-end setup, not per dry-end run**, for ECT, moisture, and caliper. The board does not change inside a setup, and "every run" at dry-end grain would have been 300,000 rows on its own. Pin adhesion is twice a shift rather than once, so PF-20's 5.6% has enough tests behind it to land within 0.1 points.

### What broke

- **The spec's numbers do not all fit together.** Section 3 says a 110" machine runs 200,000 to 400,000 lineal feet a shift. PF-07 and PF-08 fix Atlanta at 3.2 setups of 38,500 feet, about 123,000 feet a shift, and Chicago at about 105,000. Both cannot hold. The planted facts are exact targets, so they won, and every shift carries 250 to 300 minutes of time that is neither running nor a logged stop. The README calls this out; the owner should decide whether PF-08 or the throughput paragraph moves.
- **Order-change stops at Chicago blew the uptime budget.** 11.4 wet-end changes a shift at 3 to 8 minutes each is 60 minutes of planned downtime before anything breaks, which alone puts Chicago under 88% and makes PA's 95.8% impossible at its own change rate. Resolved by treating a grade change as a stop only on hard transitions into or out of double wall and E flute, which is also how a splicer-equipped corrugator behaves.
- **The 60-second floor on run time moved the Chicago speed means** by 6 feet per minute after calibration, because short runs got clamped. The calibration now iterates against the rounded seconds.
- **The fixed-time boiler stop landed at the wrong time on ATL-C2.** The timeline placed fixed events only inside runs; when 09:15 fell in a gap between runs the event slid to the next run start. Gaps now place fixed events at their clock time.
- **A YAML flow mapping ate a comma.** `notes: The volume grade, about 40% of all lineal feet` inside `{ … }` became two keys. Quoted every value with a comma. Worth remembering for `evals/golden.yaml`.
- **PF-20 could not be hit with one pin adhesion test per shift.** About 390 tests in a quarter means one failure is 0.26 points; the target tolerance is 0.1. Two tests a shift fixed it without changing the spec's "per shift" reading much.
- **`gsutil ls` returns 401 in a session** even though `gcloud storage ls` works, because gsutil does not read the token the environment injects. The issue's done-when said `gsutil ls`; `gcloud storage ls` is what the README and Makefile use.
- **The raw set came out at 50.2 MB** on the first full run. Dropping a redundant setup id from the quality feed, trimming trailing zeros, and taking a mid-run ECT only on setups over 25,000 feet brought it to 47.1 MB.

### How it was tested

`tests/test_generator.py` generates the full set once per session into a temp directory (about 20 seconds) and then: compares all 48 measures of the 20 facts against `planted_facts.yaml`; asserts the combined checksum for seed 42; checks size and row counts; checks each messiness item is present at its configured rate; and regenerates once more to prove byte-identical output for the same seed. 33 tests, 42 seconds. `make check-facts` against `data/raw` prints the same comparison. The upload was verified with `gcloud storage ls` and by reading `manifest.json` back from the bucket.

## What I would change

- The spec's throughput paragraph and PF-08 need a decision. If PF-08 stays, the agent will be asked "why is the machine idle half the shift" and the honest answer is "the generator". A cleaner fix is PF-08 at about 8 and 7 changes per shift, or a wet-end run that spans shifts.
- Stop events have no `run_id`; Silver joins by time. That is realistic and it is also the first place the dbt work will hurt. If it takes more than an afternoon, add the id to the feed and note it.
- `facts.py` reads every file with the `csv` module in two seconds. Once dbt exists, the same checks should run against DuckDB so there is one implementation of each rule, not two.
- The customer assignment is random within a plant. If the document corpus (M4) wants "the furniture maker buys 51 ECT BC", the generator needs a grade affinity per customer. Small change, do it when a golden question needs it.

## Where M1 stands

| Issue | Status |
| --- | --- |
| #14 Domain spec | Merged in [#21](https://github.com/justfetz/packaging-ops-agent/pull/21) |
| #15 Generator | This PR. Raw set in the dev landing bucket, 20 facts hold, tests in CI |
| M1.2 Bronze | Not started |
| M1.3 Silver | Not started. The rules are listed in `data/README.md` |
| M1.4 Gold | Not started. The fact definitions are in `data/planted_facts.yaml` |

## Owner notes
