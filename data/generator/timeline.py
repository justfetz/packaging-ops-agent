"""Give every run and stop event a clock time inside its shift.

A shift is laid out in sequence: setups in order, each with its order-change
stop (if any) and its dry-end runs; standalone stops (PM, knife change, no
orders) are inserted between setups; unplanned stops happen inside the run
they were assigned to and stretch it. Whatever time is left in the shift is
spread as gaps between runs: unlogged micro-stops and slow running, which is
why downtime seconds and lost production never reconcile (spec item 9).

The planted Atlanta boiler and power events have a fixed clock time and are
placed at exactly that time, inside whichever run is going at that moment.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict

from .config import Config
from .model import Run, Shift, ShiftSummary, StopEvent, WetEndRun

FIRST_NAMES = [
    "Marcus",
    "Dana",
    "Luis",
    "Priya",
    "Terrell",
    "Hannah",
    "Victor",
    "Renee",
    "Omar",
    "Keisha",
    "Brent",
    "Sofia",
    "Darnell",
    "Megan",
    "Hector",
    "Lauren",
    "Andre",
    "Carla",
    "Jamal",
    "Nicole",
    "Ruben",
    "Tasha",
    "Glenn",
    "Yolanda",
    "Felix",
    "Monica",
    "Dwayne",
    "Erin",
    "Pablo",
    "Shonda",
]
LAST_NAMES = [
    "Whitfield",
    "Okafor",
    "Ramirez",
    "Nguyen",
    "Baptiste",
    "Kowalski",
    "Delgado",
    "Hartman",
    "Jefferson",
    "Castillo",
    "Mbeki",
    "Sorensen",
    "Pruitt",
    "Villanueva",
    "Fontaine",
    "Garza",
    "Lindqvist",
    "Abernathy",
    "Oyelaran",
    "Marchetti",
    "Haskins",
    "Duarte",
    "Pennington",
    "Reyes",
]


def lay_out(
    cfg: Config,
    shifts: list[Shift],
    wet_runs: list[WetEndRun],
    events: list[StopEvent],
    rng: random.Random,
) -> list[ShiftSummary]:
    wet_by_shift: dict[tuple, list[WetEndRun]] = defaultdict(list)
    for w in wet_runs:
        wet_by_shift[w.shift.key].append(w)
    in_run: dict[int, list[StopEvent]] = defaultdict(list)
    before_setup: dict[str, list[StopEvent]] = defaultdict(list)
    standalone: dict[tuple, list[StopEvent]] = defaultdict(list)
    fixed: dict[tuple, list[StopEvent]] = defaultdict(list)
    for ev in events:
        assert ev.shift is not None
        if ev.placement == "in_run" and ev.run is not None:
            in_run[id(ev.run)].append(ev)
        elif ev.placement == "before_setup" and ev.run is not None:
            before_setup[ev.run.wet_end_setup_id].append(ev)
        elif ev.placement == "fixed":
            fixed[ev.shift.key].append(ev)
        else:
            ev.placement = "standalone"
            standalone[ev.shift.key].append(ev)

    leads = _CrewLeads(cfg, rng)
    summaries: list[ShiftSummary] = []
    carry: dict[str, dt.datetime] = {}
    for shift in sorted(shifts, key=lambda s: (s.start, s.machine_code)):
        setups = wet_by_shift.get(shift.key, [])
        t = max(shift.start, carry.get(shift.machine_code, shift.start))
        pending_fixed = sorted(fixed.get(shift.key, []), key=lambda e: e.start_time)
        loose = standalone.get(shift.key, [])
        slots = _standalone_slots(loose, len(setups), rng)

        content = sum(r.run_seconds for w in setups for r in w.runs)
        content += sum(
            e.duration_seconds for w in setups for r in w.runs for e in in_run.get(id(r), [])
        )
        content += sum(e.duration_seconds for w in setups for e in before_setup.get(w.setup_id, []))
        content += sum(e.duration_seconds for e in loose) + sum(
            e.duration_seconds for e in pending_fixed
        )
        gap_budget = max(
            0, shift.scheduled_minutes * 60 - content - int((t - shift.start).total_seconds())
        )
        gaps = _gaps(gap_budget, len(setups) + 1, rng)

        t = _advance(t, gaps[0], pending_fixed)
        for i, w in enumerate(setups):
            for ev in slots.get(i, []):
                t = _place_standalone(ev, t, pending_fixed)
            for ev in before_setup.get(w.setup_id, []):
                t = _place_standalone(ev, t, pending_fixed)
            for r in w.runs:
                t = _place_run(r, t, in_run.get(id(r), []), pending_fixed, rng)
            t = _advance(t, gaps[i + 1], pending_fixed)
        for ev in slots.get(len(setups), []):
            t = _place_standalone(ev, t, pending_fixed)
        for ev in pending_fixed:  # nothing was running when it struck
            start = max(t, ev.start_time)
            ev.start_time, ev.end_time = start, start + dt.timedelta(seconds=ev.duration_seconds)
            t = ev.end_time
        if t > shift.end:
            carry[shift.machine_code] = t
        else:
            carry.pop(shift.machine_code, None)
        summaries.append(_summary(shift, setups, leads, rng))
    return summaries


def _standalone_slots(
    loose: list[StopEvent], n_setups: int, rng: random.Random
) -> dict[int, list[StopEvent]]:
    slots: dict[int, list[StopEvent]] = defaultdict(list)
    for ev in loose:
        if ev.true_cause == "Preventive maintenance" and n_setups:
            pos = max(1, min(n_setups, round(n_setups * rng.uniform(0.4, 0.7))))
        else:
            pos = rng.randint(0, n_setups)
        slots[pos].append(ev)
    return slots


def _gaps(budget: int, slots: int, rng: random.Random) -> list[int]:
    weights = [rng.uniform(0.2, 1.0) for _ in range(slots)]
    if slots > 1:
        weights[0] *= 0.5  # shifts start promptly
    total = sum(weights)
    gaps = [int(budget * w / total) for w in weights]
    gaps[-1] += budget - sum(gaps)
    return gaps


def _advance(t: dt.datetime, gap_seconds: int, pending_fixed: list[StopEvent]) -> dt.datetime:
    """Move through an idle gap, placing a fixed-time stop at its clock time if it falls inside."""
    end = t + dt.timedelta(seconds=gap_seconds)
    while pending_fixed and pending_fixed[0].start_time < end:
        ev = pending_fixed.pop(0)
        start = max(t, ev.start_time)
        ev.start_time, ev.end_time = start, start + dt.timedelta(seconds=ev.duration_seconds)
        end = max(end, ev.end_time)
        t = ev.end_time
    return end


def _place_standalone(ev: StopEvent, t: dt.datetime, pending_fixed: list[StopEvent]) -> dt.datetime:
    while pending_fixed and pending_fixed[0].start_time <= t:
        t = _place_fixed_now(pending_fixed.pop(0), t)
    ev.start_time = t
    ev.end_time = t + dt.timedelta(seconds=ev.duration_seconds)
    return ev.end_time


def _place_fixed_now(ev: StopEvent, t: dt.datetime) -> dt.datetime:
    ev.start_time = t
    ev.end_time = t + dt.timedelta(seconds=ev.duration_seconds)
    return ev.end_time


def _place_run(
    run: Run,
    t: dt.datetime,
    stops: list[StopEvent],
    pending_fixed: list[StopEvent],
    rng: random.Random,
) -> dt.datetime:
    while pending_fixed and pending_fixed[0].start_time <= t:
        t = _place_fixed_now(pending_fixed.pop(0), t)
    run.run_start = t
    offsets = sorted((rng.randint(0, run.run_seconds), ev) for ev in stops)
    wall_end = t + dt.timedelta(seconds=run.run_seconds + sum(e.duration_seconds for e in stops))
    inside: list[StopEvent] = []
    while pending_fixed and pending_fixed[0].start_time < wall_end:
        f = pending_fixed.pop(0)
        inside.append(f)
        wall_end += dt.timedelta(seconds=f.duration_seconds)

    cursor = t  # absolute clock
    elapsed = 0  # running seconds so far
    queue = list(offsets)
    for f in inside:
        # Normal stops before the fixed event's clock time go first.
        while queue and cursor + dt.timedelta(seconds=queue[0][0] - elapsed) < f.start_time:
            off, ev = queue.pop(0)
            cursor += dt.timedelta(seconds=off - elapsed)
            elapsed = off
            ev.start_time = cursor
            cursor += dt.timedelta(seconds=ev.duration_seconds)
            ev.end_time = cursor
        start = max(cursor, f.start_time)
        elapsed += int((start - cursor).total_seconds())
        f.start_time = start
        f.end_time = start + dt.timedelta(seconds=f.duration_seconds)
        cursor = f.end_time
    for off, ev in queue:
        cursor += dt.timedelta(seconds=max(0, off - elapsed))
        elapsed = max(elapsed, off)
        ev.start_time = cursor
        cursor += dt.timedelta(seconds=ev.duration_seconds)
        ev.end_time = cursor
    cursor += dt.timedelta(seconds=run.run_seconds - elapsed)

    run.run_end = cursor
    run.stops_count = len(stops) + len(inside)
    run.downtime_seconds = sum(e.duration_seconds for e in stops) + sum(
        e.duration_seconds for e in inside
    )
    for f in inside:
        f.run = run
        f.placement = "in_run"
    return cursor


class _CrewLeads:
    """A roster per plant and shift. Atlanta's third shift turns over fastest."""

    def __init__(self, cfg: Config, rng: random.Random) -> None:
        self.rng = rng
        self.tenures: dict[tuple[str, int], list[tuple[dt.date, str, str]]] = {}
        emp = 1000
        for plant in cfg.plants:
            for shift_no in (1, 2, 3):
                fast = plant.code == "ATL" and shift_no == 3
                day = plant.data_start
                roster: list[tuple[dt.date, str, str]] = []
                while day <= cfg.period_end:
                    emp += 1
                    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                    roster.append((day, f"EMP-{emp:04d}", name))
                    months = rng.randint(2, 5) if fast else rng.randint(8, 18)
                    day = day + dt.timedelta(days=30 * months)
                self.tenures[(plant.code, shift_no)] = roster

    def lead(self, plant: str, shift_no: int, day: dt.date) -> tuple[str, str]:
        roster = self.tenures[(plant, shift_no)]
        current = roster[0]
        for entry in roster:
            if entry[0] <= day:
                current = entry
        return current[1], current[2]


def _summary(
    shift: Shift, setups: list[WetEndRun], leads: _CrewLeads, rng: random.Random
) -> ShiftSummary:
    runs = [r for w in setups for r in w.runs]
    lead_id, lead_name = leads.lead(shift.plant_code, shift.shift_no, shift.shift_date)
    return ShiftSummary(
        summary_id="",
        machine_code=shift.machine_code,
        shift_date=shift.shift_date,
        shift_no=shift.shift_no,
        shift_start=shift.start,
        shift_end=shift.end,
        scheduled_minutes=shift.scheduled_minutes,
        crew_lead_id=lead_id,
        crew_lead_name=lead_name,
        run_count=len(runs),
        total_lineal_ft=sum(r.actual_lineal_ft for r in runs),
        total_sqft_produced=sum(r.sqft_produced for r in runs),
        total_trim_sqft=sum(r.trim_sqft for r in runs),
        total_shear_waste_sqft=sum(r.shear_waste_sqft for r in runs),
        total_cuts=sum(r.actual_cuts for r in runs),
        stops_count=sum(r.stops_count for r in runs),
        downtime_seconds=sum(r.downtime_seconds for r in runs),
        emitted_at=shift.end + dt.timedelta(minutes=rng.randint(1, 20)),
    )
