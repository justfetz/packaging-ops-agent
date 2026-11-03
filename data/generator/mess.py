"""Deliberate messiness, items 4 to 8 and 10 of docs/domain-spec.md section 11.

Items 1 to 3 (cause-code spellings, "Other" with a comment, fault code without
an operator cause) are applied when stop events are created in downtime.py.
Item 9 (unlogged micro-stops) is what the timeline leaves in a shift after
running time, logged stops, and wet-end change time: a few minutes at most.
Each function here is one item, so data/README.md can point at it.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import random

from .config import Config
from .model import OrderLine, QualityTest, Run, ShiftSummary

KG_PER_LB = 0.45359237


def resend_shift_summaries(cfg: Config, summaries: list[ShiftSummary], rng: random.Random) -> None:
    """Item 4: 3 to 5% of shift summaries are re-sent with a later emitted_at.

    Half are exact copies, half carry an end-of-shift correction to the waste
    or stop count. Latest emitted_at wins.
    """
    rate = cfg.messiness["shift_summary_resend_rate"]
    near = cfg.messiness["shift_summary_near_dup_share"]
    extra: list[ShiftSummary] = []
    for s in summaries:
        if rng.random() >= rate:
            continue
        copy = dataclasses.replace(s)
        copy.emitted_at = s.emitted_at + dt.timedelta(minutes=rng.randint(30, 3 * 24 * 60))
        if rng.random() < near:
            if rng.random() < 0.5:
                copy.total_shear_waste_sqft = round(
                    s.total_shear_waste_sqft * rng.uniform(0.97, 1.03)
                )
            else:
                copy.stops_count = max(0, s.stops_count + rng.choice([-1, 1]))
        extra.append(copy)
    summaries.extend(extra)


def add_retests(cfg: Config, tests: list[QualityTest], rng: random.Random) -> None:
    """Item 5: a retest keeps the test_id and arrives hours or days later.

    The record already in the list is the final result. For the chosen tests an
    earlier failing record is added and the final record's recorded_at moves
    later, so a naive load double counts and a latest-wins load is right.
    """
    rate = cfg.messiness["quality_retest_rate"]
    extra: list[QualityTest] = []
    for t in tests:
        if rng.random() >= rate:
            continue
        original = dataclasses.replace(t)
        original.result = "fail"
        original.comment = "retest requested"
        if t.spec_min is not None and t.measured_value >= t.spec_min:
            original.measured_value = round(t.spec_min * rng.uniform(0.88, 0.99), 3)
        elif t.spec_max is not None and t.measured_value <= t.spec_max:
            original.measured_value = round(t.spec_max * rng.uniform(1.05, 1.4) + 0.1, 3)
        t.recorded_at = original.recorded_at + dt.timedelta(minutes=rng.randint(120, 72 * 60))
        extra.append(original)
    tests.extend(extra)


def la_starch_in_kilograms(cfg: Config, runs: list[Run]) -> None:
    """Item 6: LA logged starch in kilograms for its first three months."""
    until = cfg.messiness["la_starch_kg_until"]
    until = until if isinstance(until, dt.date) else dt.date.fromisoformat(str(until))
    for r in runs:
        if r.plant_code == "LA" and r.run_start.date() < until:
            r.starch_qty = round(r.starch_qty * KG_PER_LB, 1)


def clock_reset_runs(cfg: Config, runs: list[Run], rng: random.Random) -> None:
    """Item 7: a handful of run records have end time before start time.

    Only Atlanta and Pennsylvania, so the Chicago speed facts stay clean.
    """
    n = cfg.messiness["clock_reset_runs"]
    pool = [r for r in runs if r.plant_code in ("ATL", "PA")]
    for r in rng.sample(pool, n):
        r.run_end = r.run_start - dt.timedelta(minutes=rng.randint(5, 600))


def edit_order_lines(cfg: Config, lines: list[OrderLine], rng: random.Random) -> None:
    """Item 8: quantity edits appear as a second record with the same line id.

    The existing record becomes version 2 (the latest); an earlier version 1
    with the pre-edit quantity is added.
    """
    rate = cfg.messiness["order_line_edit_rate"]
    extra: list[OrderLine] = []
    for line in lines:
        if rng.random() >= rate:
            continue
        first = dataclasses.replace(line)
        first.line_version = 1
        first.qty_sheets = max(50, round(line.qty_sheets * rng.uniform(0.7, 1.3) / 50) * 50)
        first.shipped_date = None
        first.shipped_qty = None
        line.line_version = 2
        line.updated_at = first.updated_at + dt.timedelta(hours=rng.randint(3, 48))
        extra.append(first)
    lines.extend(extra)


def disagree_roll_width(cfg: Config, lines: list[OrderLine], rng: random.Random) -> None:
    """Item 10: the planner-keyed roll width disagrees with the machine on 1% of runs."""
    rate = cfg.messiness["roll_width_disagree_rate"]
    for line in lines:
        if rng.random() < rate:
            line.roll_width_in += rng.choice([-5, 5])
