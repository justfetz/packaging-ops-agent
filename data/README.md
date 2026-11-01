# data/

Seeded synthetic data for **Ironwood Container**, the fictional corrugated sheet feeder in [docs/domain-spec.md](../docs/domain-spec.md): four plants, five corrugators, November 2024 through October 2026. The generator writes raw CSV and JSON lines files that land in the GCS landing bucket and become the Bronze layer in M1.2. Messy data is deliberate so Silver has real work to do, and twenty planted facts give the dbt tests (M1.4) and the eval golden set (M3) exact answers.

Built in M1.1 (issue [#15](https://github.com/justfetz/packaging-ops-agent/issues/15)). Build log: [docs/build-log/01-data.md](../docs/build-log/01-data.md).

## Files

```
config.yaml           Every number from the domain spec: plants, machines, grades, customers, causes, messiness rates
planted_facts.yaml    The 20 planted facts with expected values, tolerances, and the definition of each measure
generator/            The Python package (python -m data.generator)
raw/                  Output of make generate. Gitignored; the copy of record is the landing bucket
```

Inside `generator/`, one module per stage, in the order they run:

| Module | Does |
| --- | --- |
| `config.py` | Loads the two YAML files into typed objects |
| `shifts.py` | The calendar: machine-shifts, holidays, Q4 Saturday overtime, LA starting July 2025 |
| `production.py` | Wet-end runs (grade, width, step-down sequence) and the dry-end runs inside them; waste, speed, starch |
| `downtime.py` | Stop events sized to each machine's uptime, the planted events, the planned share, the operator's spelling habits |
| `timeline.py` | Clock times for every run and stop inside its shift; shift summaries |
| `orders.py` | An order line per run: dates, quantities, OTIF, price, cost, the standard cost table |
| `quality.py` | Lab tests per setup, per shift, per order, and at receiving |
| `mess.py` | Re-sent summaries, retests, kilograms at LA, clock resets, order edits, width disagreement |
| `writers.py` | Flat files with the month in the name, fixed formatting, `manifest.json` |
| `facts.py` | Recomputes all 20 facts from the written files, with the Silver rules they depend on |
| `calibrate.py` | Helpers that nudge a random draw to an exact total, count, mean, or ratio |

## Commands

```bash
make generate                 # data/raw, seed 42, about 20 seconds
make generate SEED=7 RAW_DIR=/tmp/raw7
make check-facts              # recompute the 20 facts from data/raw and compare to planted_facts.yaml
make upload ENV=dev           # gcloud storage rsync data/raw to gs://packaging-ops-agent-dev-landing/
make test                     # includes tests/test_generator.py: facts, checksum, messiness, determinism
```

The generator needs only PyYAML and the standard library. Same seed, same bytes: `manifest.json` carries a SHA-256 per file and one combined `checksum`, and `tests/test_generator.py` pins the checksum for seed 42. **Any change to the generator or to `config.yaml` changes the checksum.** Update the constant in the test from the `make generate` output and say so in the PR.

For seed 42 the set is 130 files, 305,046 rows, 47.1 MB, all under the 50 MB ceiling that keeps BigQuery scans in the free tier.

## Layout in the bucket

Flat, with the feed and the month in the file name, no folders:

```
raw__production_runs__2025-07.csv
raw__stop_events__2025-07.jsonl
raw__shift_summaries__2025-07.jsonl
raw__order_lines__2025-07.csv
raw__quality_tests__2025-07.csv
ref__plants.csv  ref__machines.csv  ref__customers.csv  ref__board_grades.csv
ref__standard_cost.csv  ref__downtime_causes.csv  ref__fault_codes.csv
manifest.json
```

Flat because the session proxy cannot read an object under a "folder" back by name (CLAUDE.md, GCP section). A month file holds the records that **arrived** in that month, by the feed's arrival column below, which is how late-arriving records end up in a later file than the event they describe. Timestamps are plant local time, `YYYY-MM-DD HH:MM:SS`, no zone; `ref__plants.csv` carries each plant's IANA zone. Booleans are `true`/`false`; empty string is null in CSV, `null` in JSON lines.

`make upload` uses `gcloud storage rsync`, so a rerun copies only changed files. `gcloud storage ls gs://packaging-ops-agent-dev-landing/` lists them from a session; legacy `gsutil` returns `401 Invalid Credentials` in a session because it does not read the injected token.

## Feeds

Record names follow the vendor-neutral names in the spec's section 6. Tabular feeds are CSV; the two event-style feeds the machine and plant system emit are JSON lines.

### `raw__production_runs` (CSV, by `run_start`)

One row per **dry-end run**: one order on one knife inside a wet-end setup. 68,360 rows.

| Column | Meaning |
| --- | --- |
| `run_id`, `wet_end_setup_id` | The setup id groups the runs of one grade at one web width. Consecutive runs on a machine never share grade and width across a setup boundary, so grouping consecutive runs gives the same setups |
| `machine_code`, `plant_code`, `order_line_id`, `grade_code` | Keys into the reference feeds and `raw__order_lines` |
| `roll_width_in` | Web width read from the machine. Disagrees with the planner's value in `raw__order_lines` on about 1% of runs (item 10) |
| `knife_position` | `upper` or `lower`. Runs inside a setup alternate |
| `cutoff_in`, `sheet_width_in`, `outs` | Sheet length, sheet width across the web, sheets across the web |
| `scheduled_lineal_ft`, `scheduled_cuts`, `actual_lineal_ft`, `actual_cuts` | Planned from the order quantity versus produced; the difference is the over or under run |
| `sqft_produced`, `trim_sqft`, `shear_waste_sqft` | Board consumed = produced + trim + shear. Waste % = (trim + shear) / consumed |
| `starch_qty` | Pounds, except LA before 2025-10-01, which is kilograms (item 6). No unit column on purpose |
| `run_start`, `run_end` | Wall clock. `run_end - run_start - downtime_seconds` is running time; speed in feet per minute is derived from it. 14 rows have `run_end` before `run_start` (item 7) |
| `shift_date`, `shift_no` | The shift the run belongs to. Shift 3 starts at 22:00 and carries the date it started |
| `stops_count`, `downtime_seconds` | Stop events that happened inside this run |
| `new_wet_end_setup`, `width_reset` | True on the first run of a setup; `width_reset` when that setup went to a wider web than the previous one in the shift |

### `raw__stop_events` (JSON lines, by `start_time`)

One row per stoppage of 30 seconds or more. 15,442 rows.

| Column | Meaning |
| --- | --- |
| `event_id`, `machine_code`, `start_time`, `end_time`, `duration_seconds` | |
| `machine_section` | Section that raised it: wet end, bridge, double backer, slitter-scorer, knife, stacker, discharge, conveyor; null for power and scheduling causes |
| `fault_code` | Control-system fault from `ref__fault_codes`, where one exists (mostly Maintenance causes) |
| `cause_code` | The operator's cause, typed by hand: 68 distinct spellings of 15 causes, plus `Other`, plus null (items 1 to 3) |
| `comment` | Free text. On an `Other` event it names the real cause |

There is no `run_id`; Silver joins stops to runs by machine and time, which the `stops_count` on the run confirms.

### `raw__shift_summaries` (JSON lines, by `emitted_at`)

One row per machine-shift, emitted at shift end, plus the re-sends (item 4). 7,408 rows for 7,105 shifts.

Totals of the run records in the shift (`run_count`, `total_lineal_ft`, `total_sqft_produced`, `total_trim_sqft`, `total_shear_waste_sqft`, `total_cuts`, `stops_count`, `downtime_seconds`), `scheduled_minutes` (480), `crew_lead_id` and `crew_lead_name`, `shift_start`, `shift_end`, `emitted_at`. Scheduled minutes from this feed are the denominator for uptime.

### `raw__order_lines` (CSV, by `updated_at`)

One row per order line version; a line edited after download has two rows (item 8). 70,414 rows for 68,360 lines.

| Column | Meaning |
| --- | --- |
| `order_id`, `order_line_id`, `line_version`, `updated_at` | Latest `updated_at` per line wins |
| `customer_id`, `plant_code`, `grade_code` | |
| `order_date`, `requested_ship_date`, `shipped_date` | On time = shipped on or before requested |
| `qty_sheets`, `shipped_qty` | In full = shipped within 10% of ordered. Version 1 of an edited line has no shipment yet |
| `sheet_width_in`, `sheet_length_in`, `score_pattern`, `unitizing`, `unit_count` | Sheet spec. MSF shipped = shipped_qty × width × length / 144 / 1000 |
| `roll_width_in` | The planner's hand-keyed web width (item 10) |
| `price_per_msf`, `std_cost_per_msf` | Revenue and cost are both per MSF shipped. Margin = 1 − cost / revenue |
| `scheduling_notes` | Mostly empty |

### `raw__quality_tests` (CSV, by `recorded_at`)

One row per test result, plus retests (item 5). 143,033 rows for 137,500 tests.

| Column | Meaning |
| --- | --- |
| `test_id`, `recorded_at` | Latest `recorded_at` per `test_id` wins |
| `test_type` | `ECT`, `Mullen`, `moisture`, `caliper`, `pin_adhesion`, `warp`, `score`, `ring_crush` |
| `plant_code`, `machine_code`, `grade_code`, `run_id`, `order_line_id` | Ring crush is a receiving test: plant only |
| `sampled_at` | When the sample was taken; the fact definitions group by this |
| `measured_value`, `unit`, `spec_min`, `spec_max`, `result`, `comment` | `result` is `pass` or `fail` |

Frequencies as generated: ECT or Mullen and moisture once per wet-end setup, a second ECT on setups over 25,000 feet; caliper once and pin adhesion twice per machine-shift; warp on half of the double wall and E flute orders; score quality on scored orders (70% at LA, 30% elsewhere); ring crush once or twice per plant per weekday. The spec says "every run" for ECT, caliper, and moisture; the board does not change inside a wet-end setup, so the setup is the run that matters for those tests, and it keeps the feed under 20 MB.

### Reference feeds

`ref__plants`, `ref__machines`, `ref__customers`, `ref__board_grades` are the dimensions from the spec, written from `config.yaml`. `ref__standard_cost` is finance's standard cost per MSF by grade and month; it steps up 6.1% in March 2025 and 5.8% in February 2026 (the paper price increases), and `std_cost_per_msf` on an order line is that standard with per-line noise and the customer calibration. `ref__downtime_causes` has the canonical cause list with category, planned flag, and typical minutes; `ref__fault_codes` maps each control-system fault to its section and cause.

## Deliberate messiness

Numbered as in the spec's section 11. Each becomes a Silver rule and a dbt test in M1.3. `generator/facts.py` already implements the rule in Python so the planted facts can be checked against raw files.

| # | Mess | Where it is made | Rate for seed 42 | Silver rule |
| --- | --- | --- | --- | --- |
| 1 | Operator cause codes drift by plant | `downtime._dress`, `config.yaml` `cause_spellings`, `variant_rate_by_plant` | 68 spellings; Chicago 45% variants, PA 8% | Lower-case lookup against the spellings table |
| 2 | Cause `Other` with a comment naming the real cause | `downtime._dress`, `OTHER_COMMENTS` | 8% of events | Word-boundary match of `other_comment_keywords` in the comment; exactly one cause matches |
| 3 | Fault code without operator cause, and vice versa | `downtime._dress` | 85% of Maintenance stops carry a fault code; 15% of those have no cause | Cause from `ref__fault_codes` when `cause_code` is null. Every event has at least one of the two |
| 4 | Shift summaries re-sent after corrections | `mess.resend_shift_summaries` | 4% of shifts, half exact, half with a corrected waste or stop count | Latest `emitted_at` per machine, shift_date, shift_no |
| 5 | Quality retests with the same test id | `mess.add_retests` | 4% of tests; the earlier record is always a fail | Latest `recorded_at` per `test_id` |
| 6 | LA starch in kilograms for three months | `mess.la_starch_in_kilograms` | LA runs before 2025-10-01 | Multiply by 2.20462 where plant = LA and run_start < 2025-10-01 |
| 7 | Run end before run start (clock reset) | `mess.clock_reset_runs` | 14 runs at ATL and PA | Exclude from speed; keep for volume and waste |
| 8 | Order lines edited after download | `mess.edit_order_lines` | 3% of lines, quantity ±10 to 30% | Latest `updated_at` per `order_line_id` |
| 9 | Micro-stops under 30 seconds are not logged | `timeline.lay_out` | Run wall time plus stops is about 200 of 480 minutes per shift | Nothing to fix; `scheduled − runs − stops` is "unaccounted" and worth a Gold column |
| 10 | Roll width keyed by hand in one feed, read from the machine in another | `mess.disagree_roll_width` | 1% of lines, ±5 inches | Machine value wins; count the disagreements |

## Planted facts

[planted_facts.yaml](planted_facts.yaml) has all twenty with the expected values, a tolerance per measure, and a `definition` that states the arithmetic. The generator reads the targets from that file, so there is one place to change a number. The test `test_planted_fact[PF-xx]` recomputes each from the written files; `make check-facts` prints the same comparison.

How the targets are hit: the generator draws plausible values first and then calibrates. Counts are placed exactly (46 missplices, 1,840 stacker jams, 212 minutes). Means and totals are scaled to the target and rounded, with the residual on one record (wet-end run length, PM minutes, starch). Rates are set by choosing exactly `round(n × rate)` records (OTIF, test failures). Ratios over overlapping groups, such as Atlanta waste by shift and ATL-C2 waste by cutoff, use iterative proportional fitting on shear waste. Downtime is budgeted per machine from its uptime target, planned events first, then the planned share is completed with order-change and no-orders stops, then unplanned filler to the machine total.

| ID | Measured for seed 42 |
| --- | --- |
| PF-01 | 46 missplices, mean 7.0 minutes, 12 in Dec to Feb; the largest three-month window on any machine |
| PF-02 | 1,840 stacker jams, 18,400.0 minutes; largest unplanned cause at Chicago by count and minutes |
| PF-03 | PA-C1 95.8%; ATL-C1 93.6, ATL-C2 94.3, CHI-C1 86.9, LA-C1 90.8 |
| PF-04 | 6.21% and 1.74% (roughly 1,100 tests per quarter, so one failure is 0.09 points) |
| PF-05 | 9.50% and 2.09% |
| PF-06 | 4.8% and 3.1%; other plants' shift gaps are 0.5 to 0.7 points |
| PF-07 | 38,500, 31,000, 14,600, 9,200 exactly |
| PF-08 | 11.4 and 3.2 |
| PF-09 | 2.7 and 0.9 |
| PF-10 | 41.0% |
| PF-11 | 410.0 and 780.0 |
| PF-12 | 91.3%, 84.6%, 96.1%; ATL 92.9, LA 88.6 |
| PF-13 | 6.1% step; 14.2% and 8.9% |
| PF-14 | 61.0% |
| PF-15 | 3.90 and 3.10 lb/MSF after converting Q3 2025 from kilograms |
| PF-16 | 7.4% and 3.0% |
| PF-17 | 31.0% planned; PM mean 92.0 minutes |
| PF-18 | 212 minutes, 2026-01-14 09:15 to 12:47, both Atlanta machines, cause boiler |
| PF-19 | C007 Lakeshore Furniture Works 22.4%; C001 Southern Brands Converting 9.8% |
| PF-20 | 5.6% and 1.4% |

## Simplifications and where the data departs from the spec

- **Throughput per shift is lower than the spec's "typical performance".** Section 3 says 200,000 to 400,000 lineal feet per shift on a 110" machine. PF-07 and PF-08 together fix Atlanta at 3.2 wet-end runs × 38,500 feet ≈ 123,000 feet per machine-shift and Chicago at about 105,000. The planted facts win because they are exact targets; the result is that runs plus logged stops fill about 200 of 480 minutes and the rest is unaccounted time (item 9, much larger than micro-stops alone would explain). The owner may want to revise either PF-08 or the typical-performance paragraph.
- **Dry-end runs inside a setup are laid out one after another**, alternating knives, and the setup's lineal feet is their sum, as the spec's section 5 says. On a real corrugator the two knives cut the same web side by side; a side-by-side model would halve the feet and break PF-07's definition.
- **Runs do not cross shift boundaries.** The first setup of a shift always differs in grade or width from the last setup of the previous shift.
- **Wet-end change stops are not one per setup.** A splice-through grade change does not stop the machine; the planned "Order change, grade change" stop happens on a share of hard transitions (into or out of double wall and E flute), most often at Chicago. Otherwise Chicago's 11.4 changes per shift would cost more downtime than its uptime allows.
- **Weekend maintenance** happens outside scheduled time and is not logged. Weekly PM and knife changes are.
- **25 customers**, not "about 20", so Chicago can have eleven with none over 10%.
- **Quality test frequencies** are per setup rather than per dry-end run for board tests; see the feed section.
- **Customer, grade, and width assignment is random within the plant's mix.** A furniture maker can buy 26 ECT B. Nothing in the planted facts depends on it.
