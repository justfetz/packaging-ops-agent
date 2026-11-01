# Domain spec: Ironwood Container

_Written by Jason Fetzer with Claude Code, October 2026. Issue #14. This is the source of truth for the synthetic data (M1), the planted facts that become dbt tests (M1) and golden eval questions (M3), and the document corpus (M4). Everything here is fictional. Numbers are chosen to be plausible to someone who has worked in a box plant, not to match any real company._

The company name is a placeholder. Rename here and in `data/config.yaml` before M1.1 if a better one comes along.

## 1. Scope decisions

- **Ironwood is a sheet feeder.** Corrugators only, no converting. It sells corrugated sheets to independent box plants and to a few large customers' in-house converting operations. This keeps the data model to one machine type and matches the depth of knowledge behind this spec.
- **Four plants, five corrugators.** Enough contrast for the evals without a generator that takes a week.
- **Two years of data**, November 2024 through October 2026. Los Angeles only from July 2025.
- **Record names are vendor-neutral.** Real corrugator control systems have their own names for these records. The repo uses the generic names in section 6.

## 2. Company

Ironwood Container is an independent corrugated sheet feeder with four plants and no mills of its own. It buys liner and medium on the open market, so industry paper price increases hit cost directly and pass through to customers with a lag. Floor space is tight at every plant, so board and finished-sheet storage is a constant scheduling constraint.

**Growth path:** Atlanta first, then Chicago, then Pennsylvania, then Los Angeles. Each expansion was an attempt to enter a new market, and each plant reflects the era and the ambition it was built with.

**Corporate facts to plant:**

- Two paper price increases, March 2025 and February 2026, each adding about 6% to cost per MSF. Price follows 30 to 60 days later. Margin dips in the lag window on every contract without an escalator, visible by customer.
- Chicago has a winter quality effect: moisture-related test failures rise December through February.

## 3. Plants

| Plant | Code | Location | Commissioned | Market and mix | Character |
| --- | --- | --- | --- | --- | --- |
| Atlanta | ATL | Atlanta, GA | 2002 | High-volume brown box, long sheet runs, one anchor customer on a partnership agreement | The star. Oldest equipment, best numbers. High labor turnover, which shows up as higher setup time and waste on third shift |
| Chicago | CHI | Chicago, IL | 2009 | Specialty: E flute, double wall, preprinted liner, short runs, customers close by | The problem child. Lineal-foot scheduling with frequent wet-end changes and hard transitions in and out of specialty grades. Cold climate: board stored on trailers in winter, moisture problems, different storage practice |
| Pennsylvania | PA | Off I-81, central PA | 2014 | Volume for the I-95 and I-81 corridor, long runs, distribution-center customers | Steady. Good equipment, mid-range on everything. The control plant |
| Los Angeles | LA | LA area, CA | July 2025 | Specialty produce packaging: fruit and vegetable sheets, moisture-resistant grades, one dominant customer | Newest. Data starts mid-2025. Still ramping, so early months are noisy |

**Calendar.** 24/5, three shifts Monday through Friday, Saturday as an overtime day when backlog needs it. Weekly preventive maintenance of one to two hours per machine, scheduled midday or early in a shift around production: blades, cleaning, glue traps, general machine health. Weekend maintenance on Saturdays from about 7 to 2 or 3, roughly every other week, moving to Sunday when Saturday was taken for overtime production.

**Seasonality.** Q4 retail peak for Atlanta and PA. Produce seasons for LA. Atlanta summer humidity (June through August) affects splicing and bond.

## 4. Machines

Five corrugators. Section order, wet end to dry end: roll stands and splicers, single facers, bridge, preheaters and glue unit, double backer (hot plates), slitter-scorer, cutoff knives, stackers, bander.

| Machine | Plant | Width | Commissioned | Nominal speed | Capability | Known weak spot |
| --- | --- | --- | --- | --- | --- | --- |
| ATL-C1 | Atlanta | 110" | 2002 | 800 fpm | Single and double wall: B, C, BC | Splicer on roll stand 2 misses intermittently, more in humid months. Causes short stops and a web break every few weeks |
| ATL-C2 | Atlanta | 98" | 2006 | 800 fpm | Single wall: B and C | Cutoff knife 2 does not hold accuracy below 21" cutoff. Short-blank orders go to C1 or run with higher waste |
| CHI-C1 | Chicago | 98" | 2009 | 900 fpm | E, B, C, BC, EB; preprinted liner | Lower stacker jams on short sheets and E flute. Frequent short stops, the plant's biggest downtime cause |
| PA-C1 | Pennsylvania | 110" | 2014 | 1,000 fpm | Single and double wall | None chronic. The control machine |
| LA-C1 | Los Angeles | 98" | 2025 | 1,000 fpm | B, C, BC; food-grade and moisture-resistant liners, higher starch and wax-alternative additive use | Slitter-scorer score alignment drifts, causing score-line quality rejects. Ramp-up noise through 2025 |

Each corrugator has two cutoff knives, upper and lower, each feeding its own stacker. Two orders run side by side on the web, one per knife.

**Paper widths run.** 110, 105, 100, 95, and 90 inches. Order width determines the roll width chosen; the gap is trim waste. Narrow rolls on a wide machine mean lost capacity, which is a scheduling decision the data should show.

**Targets and typical performance.** Uptime target 95% of scheduled time. A 110" machine produces 200,000 to 400,000 lineal feet per 8-hour shift depending on grade, width, and order length. Atlanta runs near the top of that range, Chicago near the bottom because of short runs and roll changes, LA below it while ramping.

**Crew.** About 10 per shift per corrugator: two forklift drivers, three on the wet end, one on the deck, two on the dry end handling tags and stacks, one at the bander turning and strapping units, plus a lead operator. Turnover in Atlanta shows up as more new-operator shifts with higher setup time and waste.

## 5. Production structure: wet end and dry end

The expensive change on a corrugator is at the wet end. A new grade or a new web width means the splicers and roll stands change. Everything downstream is cheap by comparison: an order change at the knife is a dry-end setup of a few minutes. So production has two grains.

- A **wet-end run** is one grade at one web width. It is the sum of the dry-end runs inside it. A good schedule makes wet-end runs long, 30,000 to 40,000 lineal feet, by stacking many orders of the same grade and width.
- A **dry-end run** is one order on one knife inside a wet-end run.

In practice wet-end runs are shorter than anyone wants, because order quantities fluctuate and differ by plant. Chicago's problem-child status is mostly this: many short wet-end runs.

**Width sequencing.** The rule is step down: run 110, then 105, 100, 95, then reset to 110 on the next grade. Every reset is a wet-end change. Many resets per shift means a bad schedule or a bad order book, and the data should show which plant has that problem.

**Speed.** Feet per minute is derived: lineal feet produced over run time, per dry-end run. Speed steps with grade and width: double wall and E flute run slower; a narrow web on a wide machine runs at full speed but wastes capacity.

**Gold implication.** `fct_production_runs` is at dry-end run grain and carries a `wet_end_run_id`, the grade, the web width, derived feet per minute, waste %, and flags for whether the run started a new wet-end setup and whether that setup was a width reset. A second Gold table, `fct_wet_end_runs`, rolls up to grade and width: total lineal feet, order count, duration, and the change type that started it.

## 6. Data produced by the machines

Each corrugator emits telemetry over a protocol link to the plant system. An order is downloaded to the machine, and a return comes back when the order completes. Three record types matter.

| Record | Grain | Fields |
| --- | --- | --- |
| **Stop event** | One per stoppage | Machine, start and end time, duration in seconds, machine section that raised it (wet end, bridge, double backer, slitter-scorer, knife, stacker, discharge, conveyor), machine fault code where one exists. The plant system attaches the operator's cause code from a list and a free-text comment |
| **Run record** | One per order per knife | Order, grade, roll width, knife position (upper or lower), scheduled lineal feet and cuts, actual lineal feet and cuts (the over or under run), square footage produced, trim square footage, shear waste in square feet, start and end time, shift, number of stops, seconds down during the run |
| **Shift summary** | One per shift per machine, emitted at shift change | Totals of all run records in the shift, crew lead, scheduled minutes |

MSF is how production is planned and sold. Lineal feet and square feet are what the machine reports. Converting between them, given width, is a Silver job.

## 7. Downtime

Three categories, by who owns the fix: Operator (anything a human touches), Maintenance (machine faults), Management (planned work, outages, waiting).

| Cause | Category | Planned | Typical minutes | Favors |
| --- | --- | --- | --- | --- |
| Missplice | Operator | No | 4 to 12 | ATL-C1 roll stand 2, humid months |
| Roll prep wrong | Operator | No | 10 to 20 | Atlanta third shift, new operators |
| Paper or raw material problem | Operator | No | 10 to 30 | Chicago preprinted liner, LA MR liner |
| Order change, grade change | Operator | Yes | 3 to 8 | Chicago, many per shift |
| Web break | Maintenance | No | 15 to 45 | ATL-C1 after a missplice, Chicago in winter |
| Slitter blade wobble, score drift | Maintenance | No | 10 to 30 | LA-C1 |
| Air pressure loss | Maintenance | No | 10 to 40 | ATL-C2 |
| Boiler or steam issue | Maintenance | No | 30 to 180 | Any, rare, hits both ATL machines at once |
| Stacker jam | Maintenance | No | 5 to 15 | CHI-C1 lower stacker, short sheets and E flute |
| Discharge or conveyor fault | Maintenance | No | 10 to 30 | Chicago, PA |
| Knife change | Maintenance | Yes | 20 to 40 | All, weekly |
| Preventive maintenance | Management | Yes | 60 to 120 | All, weekly, midday or early shift |
| Power outage | Management | No | 30 to 240 | Rare, Atlanta summer storms |
| No orders, waiting on schedule | Management | Yes | 30 to 120 | LA while ramping, Chicago between specialty runs |
| Waiting on forklift or paper delivery | Management | No | 5 to 15 | Atlanta volume shifts |

Minimum logged stop is 30 seconds. Micro-stops below that appear only as lost speed, which is why downtime seconds and lost production never fully reconcile.

## 8. Board grades

ECT is the standard. Mullen burst grades survive for a few legacy customers. Recipes are liner/medium/liner basis weights in pounds and are approximate; the generator needs them consistent, not mill-accurate.

| Grade | Flute | Recipe (lb) | Test basis | Runs mainly at | Notes |
| --- | --- | --- | --- | --- | --- |
| 26 ECT B | B | 26/23/26 | ECT 26 | Chicago | Light e-commerce mailers |
| 29 ECT C | C | 33/23/33 | ECT 29 | ATL, PA | Light RSC |
| 32 ECT C | C | 35/26/35 | ECT 32 | ATL, PA, LA | The volume grade, about 40% of all lineal feet |
| 32 ECT B | B | 35/26/35 | ECT 32 | Chicago | Print surface, retail |
| 40 ECT C | C | 42/26/42 | ECT 40 | ATL, PA | Heavier shipping |
| 44 ECT C | C | 42/30/42 | ECT 44 | ATL, PA | Second volume grade: furniture, appliances |
| 44 ECT C MR | C | 42/30/42, wet-strength liner | ECT 44, moisture | LA | Moisture-resistant produce grade, higher starch, wax-alternative coating |
| 200# C | C | 42/26/42 | Mullen 200 | ATL | Legacy Mullen customers |
| 275# C | C | 69/33/69 | Mullen 275 | PA | Legacy heavy Mullen |
| 48 ECT BC | BC double wall | 42/26/26/26/42 | ECT 48 | Chicago, PA | Entry double wall |
| 51 ECT BC | BC | 42/26/33/26/42 | ECT 51 | Chicago, ATL-C1 | Cabinets, furniture. Harder to run |
| 71 ECT BC | BC | 69/33/33/33/69 | ECT 71 | Chicago | Heaviest. Slow, high waste, few customers |
| 32 ECT E | E | 35/26/35 | ECT 32 | Chicago | Small retail, often preprinted liner |

## 9. Customers and orders

**Customers.** About 20. Segments: independent box plants (the majority, about 12), large brand converting operations buying overflow sheets (two: fictional analogues of a big-box retailer and an e-commerce company), e-commerce packagers, furniture and cabinet makers, produce packers (LA), and distribution-center packaging.

**Concentration.** Atlanta's anchor is a national brand's in-house converting operation on a partnership agreement, about 40% of ATL volume. LA's anchor is a produce packer, about 60% of LA volume. Chicago has the longest tail, no customer over 10%. PA is in between.

**Orders.** A sheet order carries: customer, requested ship date, one or more lines, each with quantity in sheets, board grade, width and length in inches, score pattern (none, standard, male-female, tele-twin rarely), unitizing instructions (banded, palletized, unit count), and scheduling notes. Typical line is 500 to 5,000 sheets; Atlanta volume lines run to 20,000; Chicago specialty lines are often under 1,000. Lead time 3 to 10 days, shorter for anchors.

**On time** means shipped on or before the requested date. **In full** means shipped quantity within the industry over/under tolerance of ±10%. OTIF is both.

**Price and cost.** Price $15 to $60 per MSF: volume 32 ECT around $18 to $22, 44 ECT $25 to $30, double wall $35 to $50, 71 ECT and specialty MR at the top. Cost is paper-dominated: roughly 65% paper, 5% starch and additives, 15% labor, 8% energy, 7% freight.

## 10. Quality tests

| Test | Frequency | Notes |
| --- | --- | --- |
| Edge crush (ECT) | Every run, start and mid-run | The primary grade test |
| Ring crush | On incoming paper components, at receiving | Component test, feeds paper-problem downtime |
| Mullen burst | 200# and 275# grades only | Legacy |
| Caliper and moisture | Every run | Moisture is the Chicago winter problem |
| Pin adhesion | Per shift | Bond. Atlanta's humid-summer problem |
| Warp | Per order on specialty and double wall | |
| Score quality | Per order where scored | LA's slitter-scorer problem |
| Starch streak and bond visual | Per run | Recorded pass/fail with comment |

Starch pounds per MSF is tracked per run and matters to the LA anchor, both as cost and as a food-contact concern.

**Failure patterns.** Chicago moisture and warp in winter. LA score quality from slitter-scorer drift, improving through 2026. Atlanta pin adhesion in humid summer months.

## 11. Deliberate messiness

Each item becomes a Silver rule and a dbt test in M1.3.

1. Operator cause codes drift by plant: the same stop is "missplice", "mis-splice", "splice miss", or "SPLICE" depending on who typed it. Chicago has the most variants.
2. About 8% of stop events have cause "Other" with a comment that names the real cause.
3. Machine fault codes are a fixed list. Some stop events carry a fault code but no operator cause, and vice versa.
4. Shift summaries get re-sent after end-of-shift corrections, so 3 to 5% are exact or near duplicates with a later timestamp.
5. Quality retests arrive hours or days after the run with the same test ID and a new result. Latest wins.
6. LA logged starch consumption in kilograms for its first three months, then switched to pounds.
7. A handful of run records have end time before start time, from a machine clock reset.
8. Order lines are changed after download: quantity edits show up as a second order-line record with the same line ID.
9. Micro-stops under 30 seconds are not logged, so downtime seconds and lost production do not reconcile.
10. Roll width is keyed by hand in one feed and read from the machine in another, disagreeing on about 1% of runs.

## 12. Planted facts

Each fact is one generator rule (M1.1), one dbt singular test against Gold (M1.4), and one golden eval question (M3). Values are exact targets for the generator.

| ID | Fact | Tables |
| --- | --- | --- |
| PF-01 | ATL-C1 logged 46 missplice stops in June through August 2025, averaging 7 minutes, the most missplice events of any machine in any quarter. December 2025 through February 2026 it logged 12 | downtime |
| PF-02 | Lower stacker jams are Chicago's largest unplanned downtime cause over the full period: 1,840 events and 18,400 minutes | downtime |
| PF-03 | PA-C1 is the only machine above the 95% uptime target, at 95.8% for the period | runs, downtime |
| PF-04 | LA-C1's score-quality reject rate was 6.2% in Q3 2025 and 1.8% in Q3 2026 | quality |
| PF-05 | Chicago moisture test failure rate was 9.5% in December 2025 through February 2026 versus 2.1% in June through August 2025 | quality |
| PF-06 | Atlanta third shift runs 4.8% waste against 3.1% on first shift, the only plant with a shift gap over one point | runs |
| PF-07 | Average wet-end run length: Atlanta 38,500 lineal feet, PA 31,000, LA 14,600, Chicago 9,200 | wet-end runs |
| PF-08 | Chicago averages 11.4 wet-end changes per shift; Atlanta averages 3.2 | wet-end runs |
| PF-09 | Width resets per shift: Chicago 2.7, PA 0.9 | wet-end runs |
| PF-10 | 32 ECT C is 41% of all lineal feet produced companywide | runs |
| PF-11 | On CHI-C1, 71 ECT BC averages 410 feet per minute; 32 ECT C averages 780 | runs |
| PF-12 | Companywide OTIF is 91.3%. Chicago is lowest at 84.6%, PA highest at 96.1% | orders |
| PF-13 | The March 2025 paper increase raised cost per MSF 6.1%. The Atlanta anchor's contract price did not move until June, so that customer's margin fell from 14.2% in Q1 2025 to 8.9% in Q2 | orders |
| PF-14 | The LA anchor took 61% of sheets shipped from LA | orders |
| PF-15 | Starch pounds per MSF on 44 ECT C MR at LA fell from 3.9 in Q3 2025 to 3.1 in Q3 2026 | runs |
| PF-16 | On ATL-C2, runs with cutoff under 21 inches waste 7.4% against 3.0% for 21 inches and over | runs |
| PF-17 | Planned downtime is 31% of all downtime minutes companywide; weekly PM averages 92 minutes per machine | downtime |
| PF-18 | The longest single stop was a boiler failure in Atlanta on 14 January 2026, 212 minutes, taking down both ATL machines | downtime |
| PF-19 | Highest-margin customer over the period is a Chicago furniture maker at 22.4%; lowest is the Atlanta anchor at 9.8% | orders |
| PF-20 | Atlanta pin adhesion failures run 5.6% in June through August 2025 against 1.4% the rest of the year | quality |

Two facts are set up for the M4 document corpus: an incident report explains PF-18, and a maintenance manual section on the splicer explains PF-01. Questions about "why" need both tools.

## 13. Document corpus (sketch for M4)

Thirty to sixty short documents, all fictional, drawing on this spec:

- **Maintenance manuals**: one per machine section (splicer, single facer, double backer, slitter-scorer, cutoff knife, stacker), with fault codes, symptoms, and procedures. The splicer section explains PF-01.
- **Board grade specs**: one per grade in section 8, with recipe, test targets, and tolerance.
- **SOPs**: roll prep, wet-end change, width step-down scheduling rule, PM checklist, winter board storage (Chicago), food-contact handling (LA).
- **Incident reports**: the January 2026 Atlanta boiler failure (PF-18), a Chicago stacker jam cluster, the LA slitter-scorer corrective action, the Chicago winter moisture review.
- **Customer specs**: the LA anchor's moisture and starch requirements, the Atlanta anchor's partnership agreement summary with the price escalator gap (PF-13).
