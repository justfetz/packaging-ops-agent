"""Give every run and stop event a clock time inside its shift.

A shift is laid out in sequence: setups in order, each with its order-change
stop (if any), its wet-end change time at crawl speed, and its dry-end runs;
standalone stops (PM, knife change, no orders) are inserted between setups;
unplanned stops happen inside the run they were assigned to and stretch it.

The time a shift has left after running time and logged stops is wet-end
change time (spec section 5). Each setup gets a floor that every change
needs plus a weighted share of the rest, with specialty transitions and
width resets weighing more, and the shares are scaled per plant so the mean
per machine-shift lands on the PF-21 target. The first run of the setup
carries it as `setup_minutes`. A shift that is already full of stops gives
its changes only their floors and runs late; the next shift starts late and
absorbs it. What little is left over sits at the end of the shift as
unlogged micro-stops (spec item 9).

The planted Atlanta boiler and power events have a fixed clock time and are
placed at exactly that time, inside whichever run is going at that moment.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict

from .calibrate import scale_to_sum
from .config import Config, PlannedFact
from .model import Run, Shift, ShiftSummary, StopEvent, WetEndRun
from .production import SPECIALTY_FLUTES, change_minutes_per_shift

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
    facts: dict[str, PlannedFact],
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

    ordered = sorted(shifts, key=lambda s: (s.start, s.machine_code))
    content: dict[tuple, int] = {}
    for shift in ordered:
        setups = wet_by_shift.get(shift.key, [])
        seconds = sum(r.run_seconds for w in setups for r in w.runs)
        seconds += sum(
            e.duration_seconds for w in setups for r in w.runs for e in in_run.get(id(r), [])
        )
        seconds += sum(e.duration_seconds for w in setups for e in before_setup.get(w.setup_id, []))
        seconds += sum(e.duration_seconds for e in standalone.get(shift.key, []))
        seconds += sum(e.duration_seconds for e in fixed.get(shift.key, []))
        content[shift.key] = seconds
    _assign_change_time(cfg, facts, ordered, wet_by_shift, content, rng)

    leads = _CrewLeads(cfg, rng)
    summaries: list[ShiftSummary] = []
    carry: dict[str, dt.datetime] = {}
    for shift in ordered:
        setups = wet_by_shift.get(shift.key, [])
        t = max(shift.start, carry.get(shift.machine_code, shift.start))
        pending_fixed = sorted(fixed.get(shift.key, []), key=lambda e: e.start_time)
        loose = standalone.get(shift.key, [])
        slots = _standalone_slots(loose, len(setups), rng)
        budget = max(
            0,
            shift.scheduled_minutes * 60
            - content[shift.key]
            - int((t - shift.start).total_seconds()),
        )
        tail = max(0, budget - sum(w.setup_seconds for w in setups))

        for i, w in enumerate(setups):
            for ev in slots.get(i, []):
                t = _place_standalone(ev, t, pending_fixed)
            for ev in before_setup.get(w.setup_id, []):
                t = _place_standalone(ev, t, pending_fixed)
            t = _advance(t, w.setup_seconds, pending_fixed)
            w.runs[0].setup_minutes = w.setup_seconds / 60
            for r in w.runs:
                t = _place_run(r, t, in_run.get(id(r), []), pending_fixed, rng)
        for ev in slots.get(len(setups), []):
            t = _place_standalone(ev, t, pending_fixed)
        t = _advance(t, tail, pending_fixed)
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


def _assign_change_time(
    cfg: Config,
    facts: dict[str, PlannedFact],
    ordered: list[Shift],
    wet_by_shift: dict[tuple, list[WetEndRun]],
    content: dict[tuple, int],
    rng: random.Random,
) -> None:
    """Set `setup_seconds` on every wet-end run, in whole tenths of a minute.

    Each change gets a floor drawn from the configured range. The idle time a
    shift has after its content and the floors is shared out by weight, then
    the shares are scaled per plant so the plant's total equals its target
    (PF-21 for ATL and CHI, config for the others) times its machine-shifts.
    The idle time follows the chain of late finishes, which depends only on
    the floors, so one pass over the shifts in order is enough.
    """
    conf = cfg.wet_end_changes
    lo, hi = conf["floor_minutes"]
    floors: dict[int, int] = {}
    weights: dict[int, float] = {}
    last_grade: dict[str, str] = {}
    for shift in ordered:
        for w in wet_by_shift.get(shift.key, []):
            floors[id(w)] = round(rng.uniform(lo, hi) * 10) * 6
            weight = rng.uniform(0.6, 1.4)
            prev = last_grade.get(shift.machine_code)
            specialty = cfg.grade_by_code[w.grade_code].flute in SPECIALTY_FLUTES
            was_specialty = prev is not None and cfg.grade_by_code[prev].flute in SPECIALTY_FLUTES
            if prev is not None and specialty != was_specialty:
                weight *= conf["specialty_transition_factor"]
            if w.width_reset:
                weight *= conf["width_reset_factor"]
            weights[id(w)] = weight
            last_grade[shift.machine_code] = w.grade_code

    # Idle tenths of a minute per shift once the floors are in, following the
    # chain of late finishes a full shift hands to the next one.
    idle: dict[tuple, int] = {}
    carry: dict[str, int] = {}
    for shift in ordered:
        setups = wet_by_shift.get(shift.key, [])
        late = carry.get(shift.machine_code, 0)
        scheduled = shift.scheduled_minutes * 60
        budget = max(0, scheduled - content[shift.key] - late)
        floor_total = sum(floors[id(w)] for w in setups)
        idle[shift.key] = max(0, budget - floor_total) // 6
        carry[shift.machine_code] = max(
            0, late + content[shift.key] + max(budget, floor_total) - scheduled
        )

    # Per plant, the shifts share the target by their idle time, never beyond
    # it: a tenth too many would make the shift run late with nothing to
    # absorb it, and that lateness would carry forward for good.
    by_plant: dict[str, list[Shift]] = defaultdict(list)
    for shift in ordered:
        by_plant[shift.plant_code].append(shift)
    for plant, plant_shifts in by_plant.items():
        target = round(change_minutes_per_shift(cfg, facts, plant) * len(plant_shifts) * 10)
        floor_tenths = sum(floors[id(w)] for s in plant_shifts for w in wet_by_shift[s.key]) // 6
        room = [idle[s.key] for s in plant_shifts]
        want = max(0, min(target - floor_tenths, sum(room)))
        share = [int(r * want / sum(room)) for r in room] if sum(room) else [0] * len(room)
        short = want - sum(share)
        for i in sorted(range(len(room)), key=lambda i: share[i] - room[i] * want / sum(room)):
            if short == 0:
                break
            if share[i] < room[i]:
                share[i] += 1
                short -= 1
        for shift, tenths in zip(plant_shifts, share, strict=True):
            setups = wet_by_shift[shift.key]
            split = scale_to_sum([weights[id(w)] for w in setups], tenths, minimum=0)
            for w, extra in zip(setups, split, strict=True):
                w.setup_seconds = floors[id(w)] + extra * 6


def _advance(t: dt.datetime, gap_seconds: int, pending_fixed: list[StopEvent]) -> dt.datetime:
    """Move through an idle gap, placing a fixed-time stop at its clock time if it falls inside.

    The gap keeps its full length around the stop, so a wet-end change that the
    boiler failure interrupted still takes its minutes once steam is back.
    """
    remaining = gap_seconds
    while pending_fixed and pending_fixed[0].start_time < t + dt.timedelta(seconds=remaining):
        ev = pending_fixed.pop(0)
        start = max(t, ev.start_time)
        remaining -= int((start - t).total_seconds())
        ev.start_time, ev.end_time = start, start + dt.timedelta(seconds=ev.duration_seconds)
        t = ev.end_time
    return t + dt.timedelta(seconds=remaining)


def _place_standalone(ev: StopEvent, t: dt.datetime, pending_fixed: list[StopEvent]) -> dt.datetime:
    # A fixed-time stop that would strike during this stop goes first, at its clock time.
    while pending_fixed and pending_fixed[0].start_time < t + dt.timedelta(
        seconds=ev.duration_seconds
    ):
        f = pending_fixed.pop(0)
        t = _place_fixed_now(f, max(t, f.start_time))
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
    offsets = sorted(
        ((rng.randint(0, run.run_seconds), ev) for ev in stops), key=lambda pair: pair[0]
    )
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
