"""Recompute every planted fact from the generated raw files.

This is the reference implementation of the Silver rules the facts depend on:
latest record wins for shift summaries, quality tests, and order lines; cause
codes are normalised through spellings, "Other" comments, and fault codes;
starch is converted to pounds; runs with end before start are excluded from
speed. M1.3 and M1.4 implement the same rules in dbt and test the same values.

Everything reads from disk, so the checks see exactly what BigQuery will.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import Config, PlannedFact
from .mess import KG_PER_LB
from .shifts import is_summer, month_key, quarter_key

Rows = list[dict[str, Any]]


# ----------------------------------------------------------------------------
# Loading


def _read_csv(out_dir: Path, feed: str) -> Rows:
    rows: Rows = []
    for path in sorted(out_dir.glob(f"{feed}__*.csv")) or sorted(out_dir.glob(f"{feed}.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _read_jsonl(out_dir: Path, feed: str) -> Rows:
    rows: Rows = []
    for path in sorted(out_dir.glob(f"{feed}__*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def _ts(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _latest(rows: Rows, key: str, stamp: str) -> Rows:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = best.get(row[key])
        if current is None or row[stamp] > current[stamp]:
            best[row[key]] = row
    return list(best.values())


def _latest_by(rows: Rows, keys: tuple[str, ...], stamp: str) -> Rows:
    best: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        k = tuple(row[c] for c in keys)
        current = best.get(k)
        if current is None or row[stamp] > current[stamp]:
            best[k] = row
    return list(best.values())


def _pct(num: float, den: float) -> float:
    return round(100.0 * num / den, 3) if den else 0.0


# ----------------------------------------------------------------------------
# Cause normalisation (Silver rule for messiness items 1 to 3)


class CauseNormaliser:
    def __init__(self, cfg: Config) -> None:
        self.canonical = {c.code for c in cfg.causes}
        self.aliases: dict[str, str] = {}
        for canon, variants in cfg.messiness["cause_spellings"].items():
            self.aliases[canon.lower()] = canon
            for v in variants:
                self.aliases[v.lower()] = canon
        self.keywords = {
            canon: [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in kws]
            for canon, kws in cfg.messiness["other_comment_keywords"].items()
        }
        self.fault_to_cause = {f.code: f.cause for f in cfg.fault_codes}
        self.planned = {c.code: c.planned for c in cfg.causes}

    def resolve(self, event: dict[str, Any]) -> str:
        code = event.get("cause_code")
        if code and code != "Other":
            canon = self.aliases.get(code.lower())
            if canon is None:
                raise ValueError(f"unknown cause spelling {code!r} on {event['event_id']}")
            return canon
        if code == "Other":
            comment = event.get("comment") or ""
            hits = [
                canon
                for canon, pats in self.keywords.items()
                if any(p.search(comment) for p in pats)
            ]
            if len(hits) != 1:
                raise ValueError(f"comment {comment!r} on {event['event_id']} matches {hits}")
            return hits[0]
        fault = event.get("fault_code")
        if fault in self.fault_to_cause:
            return self.fault_to_cause[fault]
        raise ValueError(f"event {event['event_id']} has no recoverable cause")


# ----------------------------------------------------------------------------
# Measures


def measure_facts(cfg: Config, out_dir: Path) -> dict[str, dict[str, Any]]:
    runs = _read_csv(out_dir, "raw__production_runs")
    events = _read_jsonl(out_dir, "raw__stop_events")
    summaries = _latest_by(
        _read_jsonl(out_dir, "raw__shift_summaries"),
        ("machine_code", "shift_date", "shift_no"),
        "emitted_at",
    )
    lines = _latest(_read_csv(out_dir, "raw__order_lines"), "order_line_id", "updated_at")
    tests = _latest(_read_csv(out_dir, "raw__quality_tests"), "test_id", "recorded_at")
    std_cost = _read_csv(out_dir, "ref__standard_cost")
    plant_of = {m.code: m.plant for m in cfg.machines}

    normaliser = CauseNormaliser(cfg)
    for e in events:
        e["cause"] = normaliser.resolve(e)
        e["minutes"] = int(e["duration_seconds"]) / 60.0
        e["start"] = _ts(e["start_time"])
        e["planned"] = normaliser.planned[e["cause"]]
    for r in runs:
        for c in (
            "actual_lineal_ft",
            "sqft_produced",
            "trim_sqft",
            "shear_waste_sqft",
            "downtime_seconds",
        ):
            r[c] = int(r[c])
        r["start"] = _ts(r["run_start"])
        r["end"] = _ts(r["run_end"])
        r["cutoff"] = float(r["cutoff_in"])
        r["shift"] = int(r["shift_no"])
    for line in lines:
        qty = int(line["qty_sheets"])
        shipped = int(line["shipped_qty"]) if line["shipped_qty"] else 0
        line["msf"] = (
            shipped * float(line["sheet_width_in"]) * float(line["sheet_length_in"]) / 144 / 1000
        )
        line["revenue"] = line["msf"] * float(line["price_per_msf"])
        line["cost"] = line["msf"] * float(line["std_cost_per_msf"])
        on_time = bool(line["shipped_date"]) and line["shipped_date"] <= line["requested_ship_date"]
        in_full = abs(shipped - qty) <= 0.10 * qty
        line["otif"] = on_time and in_full
        line["ship_q"] = quarter_key(_date(line["shipped_date"] or line["order_date"]))

    out: dict[str, dict[str, Any]] = {}
    out["PF-01"] = _pf01(events)
    out["PF-02"] = _pf02(events)
    out["PF-03"] = _pf03(events, summaries)
    out["PF-04"] = _pf04(tests)
    out["PF-05"] = _pf05(tests)
    out["PF-06"] = _pf06(runs)
    out["PF-07"] = _pf07(runs)
    out["PF-08"] = _pf08(runs, summaries, plant_of)
    out["PF-09"] = _pf09(runs, summaries, plant_of)
    out["PF-10"] = _pf10(runs)
    out["PF-11"] = _pf11(runs)
    out["PF-12"] = _pf12(lines)
    out["PF-13"] = _pf13(lines, std_cost)
    out["PF-14"] = _pf14(lines)
    out["PF-15"] = _pf15(cfg, runs)
    out["PF-16"] = _pf16(runs)
    out["PF-17"] = _pf17(events)
    out["PF-18"] = _pf18(events)
    out["PF-19"] = _pf19(lines)
    out["PF-20"] = _pf20(tests)
    return out


def compare_facts(
    facts: dict[str, PlannedFact], measured: dict[str, dict[str, Any]]
) -> dict[str, list[tuple[str, Any, Any, bool]]]:
    """Per fact, (measure, expected, got, ok) rows."""
    out: dict[str, list[tuple[str, Any, Any, bool]]] = {}
    for fact_id, fact in facts.items():
        rows = []
        got_all = measured.get(fact_id, {})
        for name, expected in fact.expected.items():
            got = got_all.get(name)
            tol = fact.tolerance.get(name)
            if got is None:
                ok = False
            elif tol is not None:
                ok = abs(float(got) - float(expected)) <= tol
            else:
                ok = got == expected
            rows.append((name, expected, got, ok))
        out[fact_id] = rows
    return out


def _pf01(events: Rows) -> dict[str, Any]:
    by_machine_month: dict[tuple[str, str], list[float]] = defaultdict(list)
    for e in events:
        if e["cause"] == "Missplice":
            by_machine_month[(e["machine_code"], month_key(e["start"].date()))].append(e["minutes"])
    summer = [
        m for mo in ("2025-06", "2025-07", "2025-08") for m in by_machine_month[("ATL-C1", mo)]
    ]
    winter = [
        m for mo in ("2025-12", "2026-01", "2026-02") for m in by_machine_month[("ATL-C1", mo)]
    ]
    months = sorted({mo for _, mo in by_machine_month})
    windows = []
    for machine in {m for m, _ in by_machine_month}:
        for i in range(len(months) - 2):
            count = sum(len(by_machine_month[(machine, mo)]) for mo in months[i : i + 3])
            windows.append((count, machine, months[i]))
    windows.sort(reverse=True)
    return {
        "events_jun_aug_2025": len(summer),
        "mean_minutes_jun_aug_2025": round(sum(summer) / len(summer), 3) if summer else None,
        "events_dec_feb": len(winter),
        "is_largest_three_month_window": windows[0][1:] == ("ATL-C1", "2025-06")
        and windows[0][0] > windows[1][0],
        "runner_up_window": windows[1],
    }


def _pf02(events: Rows) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    minutes: dict[str, float] = defaultdict(float)
    for e in events:
        if e["machine_code"] == "CHI-C1" and not e["planned"]:
            counts[e["cause"]] += 1
            minutes[e["cause"]] += e["minutes"]
    top_count = max(counts, key=lambda c: counts[c])
    top_minutes = max(minutes, key=lambda c: minutes[c])
    return {
        "events": counts["Stacker jam"],
        "minutes": round(minutes["Stacker jam"], 3),
        "is_largest_unplanned_cause": top_count == "Stacker jam" and top_minutes == "Stacker jam",
    }


def _pf03(events: Rows, summaries: Rows) -> dict[str, Any]:
    scheduled: dict[str, int] = defaultdict(int)
    for s in summaries:
        scheduled[s["machine_code"]] += int(s["scheduled_minutes"]) * 60
    down: dict[str, int] = defaultdict(int)
    for e in events:
        down[e["machine_code"]] += int(e["duration_seconds"])
    uptime = {m: round(100 * (1 - down[m] / scheduled[m]), 3) for m in scheduled}
    above = [m for m, u in uptime.items() if u > 95.0]
    return {
        "pa_c1_uptime_pct": uptime["PA-C1"],
        "only_machine_above_95": above == ["PA-C1"],
        "uptime": uptime,
    }


def _fail_rate(tests: Rows) -> float:
    return _pct(sum(1 for t in tests if t["result"] == "fail"), len(tests))


def _pf04(tests: Rows) -> dict[str, Any]:
    la = [t for t in tests if t["machine_code"] == "LA-C1" and t["test_type"] == "score"]
    by_q: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in la:
        by_q[quarter_key(_ts(t["sampled_at"]).date())].append(t)
    return {"q3_2025_pct": _fail_rate(by_q["2025Q3"]), "q3_2026_pct": _fail_rate(by_q["2026Q3"])}


def _pf05(tests: Rows) -> dict[str, Any]:
    chi = [t for t in tests if t["plant_code"] == "CHI" and t["test_type"] == "moisture"]
    winter = [
        t
        for t in chi
        if month_key(_ts(t["sampled_at"]).date()) in ("2025-12", "2026-01", "2026-02")
    ]
    summer = [
        t
        for t in chi
        if month_key(_ts(t["sampled_at"]).date()) in ("2025-06", "2025-07", "2025-08")
    ]
    return {"winter_pct": _fail_rate(winter), "summer_pct": _fail_rate(summer)}


def _waste_pct(runs: Rows) -> float:
    waste = sum(r["trim_sqft"] + r["shear_waste_sqft"] for r in runs)
    produced = sum(r["sqft_produced"] for r in runs)
    return _pct(waste, waste + produced)


def _pf06(runs: Rows) -> dict[str, Any]:
    by_plant_shift: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_plant_shift[(r["plant_code"], r["shift"])].append(r)
    gaps = {
        p: round(_waste_pct(by_plant_shift[(p, 3)]) - _waste_pct(by_plant_shift[(p, 1)]), 3)
        for p in {p for p, _ in by_plant_shift}
    }
    return {
        "atl_shift3_pct": _waste_pct(by_plant_shift[("ATL", 3)]),
        "atl_shift1_pct": _waste_pct(by_plant_shift[("ATL", 1)]),
        "only_plant_with_gap_over_one_point": [p for p, g in gaps.items() if g > 1.0] == ["ATL"],
        "gaps": gaps,
    }


def _pf07(runs: Rows) -> dict[str, Any]:
    feet: dict[str, int] = defaultdict(int)
    plant_of_setup: dict[str, str] = {}
    for r in runs:
        feet[r["wet_end_setup_id"]] += r["actual_lineal_ft"]
        plant_of_setup[r["wet_end_setup_id"]] = r["plant_code"]
    total: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    for setup, ft in feet.items():
        total[plant_of_setup[setup]] += ft
        count[plant_of_setup[setup]] += 1
    return {p: round(total[p] / count[p], 2) for p in total}


def _machine_shifts(summaries: Rows, plant_of: dict[str, str]) -> dict[str, int]:
    shifts: dict[str, int] = defaultdict(int)
    for s in summaries:
        shifts[plant_of[s["machine_code"]]] += 1
    return shifts


def _pf08(runs: Rows, summaries: Rows, plant_of: dict[str, str]) -> dict[str, Any]:
    setups: dict[str, set[str]] = defaultdict(set)
    for r in runs:
        setups[r["plant_code"]].add(r["wet_end_setup_id"])
    shifts = _machine_shifts(summaries, plant_of)
    return {p: round(len(setups[p]) / shifts[p], 3) for p in setups}


def _pf09(runs: Rows, summaries: Rows, plant_of: dict[str, str]) -> dict[str, Any]:
    resets: dict[str, int] = defaultdict(int)
    for r in runs:
        if r["width_reset"] == "true":
            resets[r["plant_code"]] += 1
    shifts = _machine_shifts(summaries, plant_of)
    return {p: round(resets[p] / shifts[p], 3) for p in shifts}


def _pf10(runs: Rows) -> dict[str, Any]:
    total = sum(r["actual_lineal_ft"] for r in runs)
    vol = sum(r["actual_lineal_ft"] for r in runs if r["grade_code"] == "32ECT-C")
    return {"share_pct": _pct(vol, total)}


def _pf11(runs: Rows) -> dict[str, Any]:
    def mean_fpm(grade: str) -> float:
        group = [
            r
            for r in runs
            if r["machine_code"] == "CHI-C1" and r["grade_code"] == grade and r["end"] > r["start"]
        ]
        speeds = [
            r["actual_lineal_ft"]
            / (((r["end"] - r["start"]).total_seconds() - r["downtime_seconds"]) / 60)
            for r in group
        ]
        return round(sum(speeds) / len(speeds), 2)

    return {"fpm_71ect_bc": mean_fpm("71ECT-BC"), "fpm_32ect_c": mean_fpm("32ECT-C")}


def _pf12(lines: Rows) -> dict[str, Any]:
    by_plant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        by_plant[line["plant_code"]].append(line)
    rate = {p: _pct(sum(1 for x in g if x["otif"]), len(g)) for p, g in by_plant.items()}
    return {
        "companywide_pct": _pct(sum(1 for x in lines if x["otif"]), len(lines)),
        "CHI": rate["CHI"],
        "PA": rate["PA"],
        "chi_lowest_pa_highest": min(rate, key=lambda p: rate[p]) == "CHI"
        and max(rate, key=lambda p: rate[p]) == "PA",
        "by_plant": rate,
    }


def _margin(lines: Rows) -> float:
    revenue = sum(x["revenue"] for x in lines)
    cost = sum(x["cost"] for x in lines)
    return _pct(revenue - cost, revenue)


def _pf13(lines: Rows, std_cost: Rows) -> dict[str, Any]:
    by_grade: dict[str, dict[str, float]] = defaultdict(dict)
    for row in std_cost:
        by_grade[row["grade_code"]][row["month"][:7]] = float(row["cost_per_msf"])
    steps = [g["2025-03"] / g["2025-02"] - 1 for g in by_grade.values()]
    anchor = [x for x in lines if x["customer_id"] == "C001"]
    return {
        "cost_step_pct": round(100 * sum(steps) / len(steps), 3),
        "anchor_margin_q1_2025_pct": _margin([x for x in anchor if x["ship_q"] == "2025Q1"]),
        "anchor_margin_q2_2025_pct": _margin([x for x in anchor if x["ship_q"] == "2025Q2"]),
    }


def _pf14(lines: Rows) -> dict[str, Any]:
    la = [x for x in lines if x["plant_code"] == "LA"]
    total = sum(int(x["shipped_qty"] or 0) for x in la)
    anchor = sum(int(x["shipped_qty"] or 0) for x in la if x["customer_id"] == "C023")
    return {"share_pct": _pct(anchor, total)}


def _pf15(cfg: Config, runs: Rows) -> dict[str, Any]:
    until = cfg.messiness["la_starch_kg_until"]
    until = until if isinstance(until, dt.date) else dt.date.fromisoformat(str(until))

    def ratio(quarter: str) -> float:
        group = [
            r
            for r in runs
            if r["machine_code"] == "LA-C1"
            and r["grade_code"] == "44ECT-C-MR"
            and quarter_key(r["start"].date()) == quarter
        ]
        starch = 0.0
        for r in group:
            qty = float(r["starch_qty"])
            starch += qty / KG_PER_LB if r["start"].date() < until else qty
        return round(starch / (sum(r["sqft_produced"] for r in group) / 1000), 3)

    return {"q3_2025_lb_per_msf": ratio("2025Q3"), "q3_2026_lb_per_msf": ratio("2026Q3")}


def _pf16(runs: Rows) -> dict[str, Any]:
    c2 = [r for r in runs if r["machine_code"] == "ATL-C2"]
    return {
        "short_cutoff_pct": _waste_pct([r for r in c2 if r["cutoff"] < 21]),
        "long_cutoff_pct": _waste_pct([r for r in c2 if r["cutoff"] >= 21]),
    }


def _pf17(events: Rows) -> dict[str, Any]:
    total = sum(e["minutes"] for e in events)
    planned = sum(e["minutes"] for e in events if e["planned"])
    pm = [e["minutes"] for e in events if e["cause"] == "Preventive maintenance"]
    return {
        "planned_share_pct": _pct(planned, total),
        "pm_mean_minutes": round(sum(pm) / len(pm), 3),
    }


def _pf18(events: Rows) -> dict[str, Any]:
    longest = max(events, key=lambda e: int(e["duration_seconds"]))
    same = [
        e
        for e in events
        if int(e["duration_seconds"]) == int(longest["duration_seconds"])
        and e["start_time"] == longest["start_time"]
    ]
    return {
        "longest_minutes": longest["minutes"],
        "longest_date": longest["start"].date().isoformat(),
        "both_atl_machines": sorted(e["machine_code"] for e in same) == ["ATL-C1", "ATL-C2"]
        and longest["cause"] == "Boiler or steam issue",
    }


def _pf19(lines: Rows) -> dict[str, Any]:
    by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for x in lines:
        by_customer[x["customer_id"]].append(x)
    margins = {c: _margin(g) for c, g in by_customer.items()}
    high = max(margins, key=lambda c: margins[c])
    low = min(margins, key=lambda c: margins[c])
    return {
        "highest_customer": high,
        "highest_margin_pct": margins[high],
        "lowest_customer": low,
        "lowest_margin_pct": margins[low],
    }


def _pf20(tests: Rows) -> dict[str, Any]:
    atl = [
        t
        for t in tests
        if t["plant_code"] == "ATL"
        and t["test_type"] == "pin_adhesion"
        and _ts(t["sampled_at"]).year == 2025
    ]
    summer = [t for t in atl if is_summer(_ts(t["sampled_at"]).date())]
    rest = [t for t in atl if not is_summer(_ts(t["sampled_at"]).date())]
    return {"summer_2025_pct": _fail_rate(summer), "rest_of_2025_pct": _fail_rate(rest)}


__all__ = ["CauseNormaliser", "compare_facts", "measure_facts"]
