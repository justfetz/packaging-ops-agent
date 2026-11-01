"""Stop events for every machine, sized to the planted uptime and planned share.

Per machine, total downtime minutes are fixed by its uptime target (PF-03 for
PA-C1; the others sit below 95%). Inside that total:

- planted events come first: weekly PM (mean 92 minutes, PF-17), weekly knife
  change, the missplice schedule (PF-01), Chicago's stacker jams (PF-02), the
  Atlanta boiler failures (PF-18) and summer power outages;
- the planned share (PF-17) is then completed with order-change stops on hard
  grade transitions and "no orders" waits, weighted to Chicago and LA;
- the rest of each machine's budget is unplanned filler drawn from the cause
  table with the machine's weights and the seasonal multipliers.

Events get their clock times from the timeline. Here they only know their
shift, their duration, and the run they interrupt.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict

from .calibrate import scale_to_sum
from .config import Cause, Config, PlannedFact
from .model import Run, Shift, StopEvent, WetEndRun
from .shifts import is_winter, month_key

OTHER_COMMENTS: dict[str, list[str]] = {
    "Missplice": ["splice missed on RS2, rethreaded", "bad splice, tail came through the SF"],
    "Roll prep wrong": ["roll prep wrong, core not stripped", "roll prep - wrong grade staged"],
    "Paper or raw material problem": ["soft roll, paper out of round", "bad paper, wet edge"],
    "Order change, grade change": [
        "grade change into double wall, glue reset",
        "hard grade change",
    ],
    "Web break": ["web broke at the bridge, rethread", "web down after the single facer"],
    "Slitter blade wobble, score drift": [
        "slitter heads not holding score",
        "slitter blade wobble",
    ],
    "Air pressure loss": ["plant air dropped, compressor cycling", "low air at the glue unit"],
    "Boiler or steam issue": ["boiler tripped, steam pressure low", "waiting on boiler to recover"],
    "Stacker jam": ["jam at lower stacker, short sheets", "sheets jam in the lower stacker"],
    "Discharge or conveyor fault": ["conveyor photo eye blocked", "discharge conveyor stopped"],
    "Knife change": ["knife blades swapped", "knife blade change, both knives"],
    "Preventive maintenance": ["weekly preventive checks", "preventive maintenance, glue traps"],
    "Power outage": ["power blip, drives faulted", "power out, storm"],
    "No orders, waiting on schedule": [
        "no orders released from scheduling",
        "no orders on the board",
    ],
    "Waiting on forklift or paper delivery": [
        "waiting on forklift to bring rolls",
        "forklift late",
    ],
}
GENERIC_COMMENTS = [
    "",
    "",
    "",
    "",
    "cleared and restarted",
    "called maintenance",
    "ok after restart",
]


class _Budget:
    def __init__(self, machine_code: str, scheduled_minutes: int, uptime_pct: float) -> None:
        self.machine_code = machine_code
        self.scheduled_minutes = scheduled_minutes
        self.total_minutes = round((1 - uptime_pct / 100.0) * scheduled_minutes)
        self.planned_seconds = 0
        self.unplanned_seconds = 0


def build_downtime(
    cfg: Config,
    facts: dict[str, PlannedFact],
    shifts: list[Shift],
    wet_runs: list[WetEndRun],
    runs: list[Run],
    rng: random.Random,
) -> list[StopEvent]:
    shifts_by_machine: dict[str, list[Shift]] = defaultdict(list)
    for s in shifts:
        shifts_by_machine[s.machine_code].append(s)
    for lst in shifts_by_machine.values():
        lst.sort(key=lambda s: s.start)
    shift_by_key = {s.key: s for s in shifts}
    runs_by_shift: dict[tuple, list[Run]] = defaultdict(list)
    for r in runs:
        runs_by_shift[(r.machine_code, r.shift_date, r.shift_no)].append(r)
    wet_by_machine: dict[str, list[WetEndRun]] = defaultdict(list)
    for w in wet_runs:
        wet_by_machine[w.shift.machine_code].append(w)

    budgets = {
        m.code: _Budget(
            m.code, sum(s.scheduled_minutes for s in shifts_by_machine[m.code]), m.uptime_pct
        )
        for m in cfg.machines
    }
    events: list[StopEvent] = []

    def add(ev: StopEvent) -> None:
        cause = cfg.cause_by_code[ev.true_cause]
        b = budgets[ev.machine_code]
        if cause.planned:
            b.planned_seconds += ev.duration_seconds
        else:
            b.unplanned_seconds += ev.duration_seconds
        events.append(ev)

    # --- planted, planned ---------------------------------------------------
    pm_mean = facts["PF-17"].expected["pm_mean_minutes"]
    for ev in _weekly_events(cfg, shifts_by_machine, "Preventive maintenance", pm_mean, rng):
        add(ev)
    for ev in _weekly_events(cfg, shifts_by_machine, "Knife change", None, rng):
        add(ev)

    # --- planted, unplanned -------------------------------------------------
    for ev in _missplices(cfg, facts, shifts_by_machine, runs_by_shift, rng):
        add(ev)
    for ev in _stacker_jams(cfg, facts, runs, rng):
        add(ev)
    for ev in _paired_atlanta_events(cfg, shift_by_key):
        add(ev)

    # --- planned flex: order changes and no-orders (PF-17 share) -----------
    total_minutes = sum(b.total_minutes for b in budgets.values())
    planned_target = round(facts["PF-17"].expected["planned_share_pct"] / 100.0 * total_minutes)
    fixed_planned = sum(b.planned_seconds for b in budgets.values()) // 60
    flex_total = planned_target - fixed_planned
    if flex_total < 0:
        raise RuntimeError("planned PM and knife changes already exceed the planned share")
    order = [m.code for m in cfg.machines]
    flex = dict(
        zip(
            order,
            scale_to_sum([cfg.planned_flex_weights[c] for c in order], flex_total, 0),
            strict=True,
        )
    )
    for code in order:
        for ev in _planned_flex(
            cfg, code, flex[code], wet_by_machine[code], shifts_by_machine[code], rng
        ):
            add(ev)

    # --- unplanned filler to the machine budget ------------------------------
    for machine in cfg.machines:
        b = budgets[machine.code]
        remaining = b.total_minutes * 60 - b.planned_seconds - b.unplanned_seconds
        if remaining < 0:
            raise RuntimeError(
                f"{machine.code}: planted and planned downtime exceed the uptime budget by "
                f"{-remaining // 60} minutes"
            )
        for ev in _filler(
            cfg, machine.code, remaining, shifts_by_machine[machine.code], runs_by_shift, rng
        ):
            add(ev)

    for ev in events:
        _dress(cfg, ev, rng)
    return events


# ----------------------------------------------------------------------------


def _new_event(
    cfg: Config,
    machine_code: str,
    cause: str,
    seconds: int,
    shift: Shift,
    run: Run | None,
    placement: str,
    start_time: dt.datetime | None = None,
) -> StopEvent:
    anchor = start_time or shift.start
    return StopEvent(
        event_id="",
        machine_code=machine_code,
        start_time=anchor,
        end_time=anchor + dt.timedelta(seconds=seconds),
        duration_seconds=seconds,
        machine_section=cfg.cause_by_code[cause].section,
        fault_code=None,
        cause_code=cause,
        comment=None,
        true_cause=cause,
        shift=shift,
        run=run,
        placement=placement,
    )


def _weekly_events(
    cfg: Config,
    shifts_by_machine: dict[str, list[Shift]],
    cause_code: str,
    exact_mean: float | None,
    rng: random.Random,
) -> list[StopEvent]:
    cause = cfg.cause_by_code[cause_code]
    out: list[StopEvent] = []
    minutes: list[float] = []
    for code, shifts in shifts_by_machine.items():
        weeks: dict[tuple[int, int], list[Shift]] = defaultdict(list)
        for s in shifts:
            if s.shift_date.weekday() < 5 and s.shift_no in (1, 2):
                iso = s.shift_date.isocalendar()
                weeks[(iso.year, iso.week)].append(s)
        for _, options in sorted(weeks.items()):
            # PM is midday or early in a shift; knife change is any first or second shift.
            pool = (
                [s for s in options if s.shift_no == 1]
                if cause_code.startswith("Prev")
                else options
            )
            shift = rng.choice(pool or options)
            minutes.append(rng.uniform(cause.minutes[0], cause.minutes[1]))
            out.append(_new_event(cfg, code, cause_code, 0, shift, None, "standalone"))
    if exact_mean is not None:
        ints = scale_to_sum(minutes, round(exact_mean * len(minutes)), minimum=cause.minutes[0])
    else:
        ints = [round(m) for m in minutes]
    for ev, m in zip(out, ints, strict=True):
        ev.duration_seconds = m * 60
    return out


def _missplices(
    cfg: Config,
    facts: dict[str, PlannedFact],
    shifts_by_machine: dict[str, list[Shift]],
    runs_by_shift: dict[tuple, list[Run]],
    rng: random.Random,
) -> list[StopEvent]:
    cause = cfg.cause_by_code["Missplice"]
    schedule = cfg.missplice_per_month
    out: list[StopEvent] = []
    pf01 = facts["PF-01"].expected
    summer_2025: list[StopEvent] = []
    for code, shifts in shifts_by_machine.items():
        by_month: dict[str, list[Shift]] = defaultdict(list)
        for s in shifts:
            by_month[month_key(s.shift_date)].append(s)
        overrides = schedule.get(code, {})
        for month, month_shifts in sorted(by_month.items()):
            n = overrides.get(month, schedule["default"][code])
            for _ in range(n):
                shift = rng.choice(month_shifts)
                run = _pick_run(runs_by_shift, shift, rng)
                seconds = rng.randint(cause.minutes[0] * 60, cause.minutes[1] * 60)
                ev = _new_event(cfg, code, "Missplice", seconds, shift, run, "in_run")
                out.append(ev)
                if code == "ATL-C1" and month in ("2025-06", "2025-07", "2025-08"):
                    summer_2025.append(ev)
    assert len(summer_2025) == pf01["events_jun_aug_2025"], len(summer_2025)
    target = round(pf01["mean_minutes_jun_aug_2025"] * 60 * len(summer_2025))
    secs = scale_to_sum([ev.duration_seconds for ev in summer_2025], target, cause.minutes[0] * 60)
    for ev, s in zip(summer_2025, secs, strict=True):
        ev.duration_seconds = s
    return out


def _stacker_jams(
    cfg: Config, facts: dict[str, PlannedFact], runs: list[Run], rng: random.Random
) -> list[StopEvent]:
    cause = cfg.cause_by_code["Stacker jam"]
    pf02 = facts["PF-02"].expected
    chi_runs = [r for r in runs if r.machine_code == "CHI-C1"]
    weights = []
    for r in chi_runs:
        w = 1.0
        if cfg.grade_by_code[r.grade_code].flute == "E":
            w *= 3.0
        if r.cutoff_in < 20:
            w *= 2.0
        weights.append(w)
    picks = rng.choices(chi_runs, weights, k=pf02["events"])
    draws = [rng.uniform(cause.minutes[0] * 60, cause.minutes[1] * 60) for _ in picks]
    secs = scale_to_sum(draws, round(pf02["minutes"] * 60), cause.minutes[0] * 60)
    return [
        _new_event(cfg, "CHI-C1", "Stacker jam", s, r.shift, r, "in_run")
        for r, s in zip(picks, secs, strict=True)
        if r.shift is not None
    ]


def _paired_atlanta_events(cfg: Config, shift_by_key: dict[tuple, Shift]) -> list[StopEvent]:
    out: list[StopEvent] = []
    for cause, items in (
        ("Boiler or steam issue", cfg.boiler_events),
        ("Power outage", cfg.power_outages),
    ):
        for item in items:
            date = (
                item["date"]
                if isinstance(item["date"], dt.date)
                else dt.date.fromisoformat(item["date"])
            )
            start = dt.datetime.combine(date, dt.time.fromisoformat(item["start"]))
            shift_date = (
                date if item["shift_no"] != 3 or start.hour >= 22 else date - dt.timedelta(days=1)
            )
            for code in ("ATL-C1", "ATL-C2"):
                shift = shift_by_key.get((code, shift_date, item["shift_no"]))
                if shift is None:
                    raise RuntimeError(f"no shift for planted event {item} on {code}")
                out.append(
                    _new_event(cfg, code, cause, item["minutes"] * 60, shift, None, "fixed", start)
                )
    return out


def _planned_flex(
    cfg: Config,
    machine_code: str,
    minutes: int,
    wet_runs: list[WetEndRun],
    shifts: list[Shift],
    rng: random.Random,
) -> list[StopEvent]:
    if minutes <= 0:
        return []
    out: list[StopEvent] = []
    remaining = minutes * 60
    change = cfg.cause_by_code["Order change, grade change"]
    candidates = [w for w in wet_runs if w.has_order_change_stop and w.runs]
    rng.shuffle(candidates)
    for w in candidates:
        seconds = rng.randint(change.minutes[0] * 60, change.minutes[1] * 60)
        if seconds > remaining:
            break
        out.append(
            _new_event(cfg, machine_code, change.code, seconds, w.shift, w.runs[0], "before_setup")
        )
        remaining -= seconds

    idle = cfg.cause_by_code["No orders, waiting on schedule"]
    plant = cfg.machine_by_code[machine_code].plant
    weights = [2.0 if plant == "LA" and s.shift_date.year == 2025 else 1.0 for s in shifts]
    while remaining >= idle.minutes[0] * 60:
        seconds = rng.randint(idle.minutes[0] * 60, idle.minutes[1] * 60)
        if remaining - seconds < idle.minutes[0] * 60 and remaining <= (idle.minutes[1] + 10) * 60:
            seconds = remaining
        seconds = min(seconds, remaining)
        shift = rng.choices(shifts, weights)[0]
        out.append(_new_event(cfg, machine_code, idle.code, seconds, shift, None, "standalone"))
        remaining -= seconds
    if remaining and out:
        out[-1].duration_seconds += remaining  # a few minutes on the last event
    return out


def _filler(
    cfg: Config,
    machine_code: str,
    budget_seconds: int,
    shifts: list[Shift],
    runs_by_shift: dict[tuple, list[Run]],
    rng: random.Random,
) -> list[StopEvent]:
    plant = cfg.machine_by_code[machine_code].plant
    causes = [c for c in cfg.causes if c.weights.get(machine_code, 0) > 0 and not c.planned]
    weights = [c.weights[machine_code] for c in causes]
    shift_weights = {c.code: _shift_weights(c, plant, shifts) for c in causes}

    out: list[StopEvent] = []
    remaining = budget_seconds
    while remaining >= 60:
        cause = rng.choices(causes, weights)[0]
        seconds = rng.randint(cause.minutes[0] * 60, cause.minutes[1] * 60)
        seconds = min(seconds, remaining)
        shift = rng.choices(shifts, cum_weights=shift_weights[cause.code])[0]
        run = _pick_run(runs_by_shift, shift, rng)
        out.append(_new_event(cfg, machine_code, cause.code, seconds, shift, run, "in_run"))
        remaining -= seconds
    if remaining and out:
        out[-1].duration_seconds += remaining
    return out


def _shift_weights(cause: Cause, plant: str, shifts: list[Shift]) -> list[float]:
    third = cause.third_shift_multiplier.get(plant, 1.0)
    winter = cause.winter_multiplier.get(plant, 1.0)
    cum: list[float] = []
    total = 0.0
    for s in shifts:
        w = 1.0
        if s.shift_no == 3:
            w *= third
        if is_winter(s.shift_date):
            w *= winter
        total += w
        cum.append(total)
    return cum


def _pick_run(
    runs_by_shift: dict[tuple, list[Run]], shift: Shift, rng: random.Random
) -> Run | None:
    options = runs_by_shift.get(shift.key)
    if not options:
        return None
    return rng.choices(options, [r.run_seconds for r in options])[0]


# ----------------------------------------------------------------------------
# Messiness items 1 to 3, applied as the operator and the control system would


def _dress(cfg: Config, ev: StopEvent, rng: random.Random) -> None:
    mess = cfg.messiness
    cause = cfg.cause_by_code[ev.true_cause]
    plant = cfg.machine_by_code[ev.machine_code].plant

    faults = [f for f in cfg.fault_codes if f.cause == ev.true_cause]
    has_fault = (
        bool(faults) and cause.category == "Maintenance" and rng.random() < mess["fault_code_rate"]
    )
    if has_fault:
        fault = rng.choice(faults)
        ev.fault_code = fault.code
        ev.machine_section = fault.section
    elif faults and ev.true_cause == "Power outage":
        ev.fault_code = faults[0].code

    if rng.random() < mess["other_rate"]:
        ev.cause_code = "Other"
        ev.comment = rng.choice(OTHER_COMMENTS[ev.true_cause])
        return
    if has_fault and rng.random() < mess["fault_only_rate"]:
        ev.cause_code = None
        ev.comment = rng.choice(GENERIC_COMMENTS) or None
        return
    variants = mess["cause_spellings"].get(ev.true_cause, [])
    if variants and rng.random() < mess["variant_rate_by_plant"][plant]:
        ev.cause_code = rng.choice(variants)
    else:
        ev.cause_code = ev.true_cause
    ev.comment = rng.choice(GENERIC_COMMENTS) or None
