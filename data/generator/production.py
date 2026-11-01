"""Wet-end runs and dry-end runs for every machine-shift.

Order of work, each step calibrated to its planted fact where one exists:

1. Wet-end runs per shift (PF-08) and width resets per shift (PF-09), with a
   grade from the machine's mix and a web width that follows the step-down rule.
2. Wet-end run lengths with an exact plant mean (PF-07), then the 32 ECT C
   share of all lineal feet (PF-10) adjusted inside each plant so the plant
   totals do not move.
3. Dry-end runs: the orders inside each wet-end run, alternating knives, with
   cutoff, sheet width, outs, cuts, consumed board, trim, and shear waste.
4. Waste calibration: Atlanta by shift and ATL-C2 by cutoff (PF-06, PF-16).
5. Derived speed (PF-11 on CHI-C1) and starch use (PF-15 at LA).

Run times are set later by the timeline, once the downtime is known.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from collections import defaultdict

from .calibrate import distribute_count, scale_group_mean, scale_to_sum
from .config import Config, Machine, PlannedFact, Plant
from .model import Run, Shift, WetEndRun
from .shifts import quarter_key

RUNS_PER_SHIFT_BOUNDS = {"ATL": (4, 12), "CHI": (10, 23), "PA": (5, 14), "LA": (4, 16)}
ORDER_COUNT_WEIGHTS = {1: 1.0, 2: 1.0, 3: 0.6, 4: 0.3, 5: 0.15}
SPECIALTY_FLUTES = {"BC", "E"}
EPOCH = dt.datetime(2000, 1, 1)


def build_production(
    cfg: Config, facts: dict[str, PlannedFact], shifts: list[Shift], rng: random.Random
) -> tuple[list[WetEndRun], list[Run]]:
    by_plant: dict[str, list[Shift]] = defaultdict(list)
    for s in shifts:
        by_plant[s.plant_code].append(s)

    wet_runs: list[WetEndRun] = []
    for plant in cfg.plants:
        plant_shifts = sorted(by_plant[plant.code], key=lambda s: (s.start, s.machine_code))
        wet_runs.extend(_wet_end_runs_for_plant(cfg, facts, plant, plant_shifts, rng))

    _assign_lengths(cfg, facts, wet_runs, rng)
    runs = _split_into_dry_end_runs(cfg, wet_runs, rng)
    _calibrate_waste(cfg, facts, runs)
    _assign_speeds(cfg, facts, runs, rng)
    _assign_starch(cfg, facts, runs, rng)
    return wet_runs, runs


# ----------------------------------------------------------------------------
# 1. Wet-end run sequence per shift


def _wet_end_runs_for_plant(
    cfg: Config,
    facts: dict[str, PlannedFact],
    plant: Plant,
    plant_shifts: list[Shift],
    rng: random.Random,
) -> list[WetEndRun]:
    n_shifts = len(plant_shifts)
    runs_target = facts["PF-08"].expected.get(plant.code, plant.wet_end_runs_per_shift)
    resets_target = facts["PF-09"].expected.get(plant.code, plant.width_resets_per_shift)
    low, high = RUNS_PER_SHIFT_BOUNDS[plant.code]

    weights = []
    for s in plant_shifts:
        w = rng.uniform(0.7, 1.3)
        if plant.code == "LA":
            months_in = (s.shift_date.year - 2025) * 12 + s.shift_date.month - 7
            w *= min(1.0, 0.55 + 0.1 * months_in)  # ramp through 2025
        if s.shift_no == 3:
            w *= 0.95
        weights.append(w)
    counts = distribute_count(rng, n_shifts, round(runs_target * n_shifts), low, high, weights)
    resets = distribute_count(
        rng, n_shifts, round(resets_target * n_shifts), 0, [c // 2 for c in counts], counts
    )

    out: list[WetEndRun] = []
    last_by_machine: dict[str, tuple[str, int]] = {}
    for shift, n, r in zip(plant_shifts, counts, resets, strict=True):
        machine = cfg.machine_by_code[shift.machine_code]
        prev = last_by_machine.get(machine.code)
        sequence = _setup_sequence(cfg, machine, plant, n, r, prev, rng)
        for i, (grade, width, is_reset) in enumerate(sequence):
            out.append(
                WetEndRun(
                    setup_id="",
                    shift=shift,
                    grade_code=grade,
                    roll_width_in=width,
                    width_reset=is_reset,
                    has_order_change_stop=_hard_transition(cfg, sequence, i, prev, plant, rng),
                )
            )
        last_by_machine[machine.code] = (sequence[-1][0], sequence[-1][1])
    return out


def _setup_sequence(
    cfg: Config,
    machine: Machine,
    plant: Plant,
    n: int,
    resets: int,
    prev: tuple[str, int] | None,
    rng: random.Random,
) -> list[tuple[str, int, bool]]:
    """Grades and widths for n wet-end runs with exactly `resets` width resets.

    Widths step down through the machine's roll widths; a reset jumps back up.
    Consecutive runs never share both grade and width, including across the
    shift boundary, so a Silver layer deriving setups by grouping gets the same
    answer as the setup id.
    """
    widths = machine.roll_widths_in
    grades = list(machine.grade_mix.keys())
    weights = list(machine.grade_mix.values())
    # Reset positions are never adjacent, so there is always a step down between
    # two resets and a reset always has somewhere wider to go.
    if resets:
        picked = sorted(rng.sample(range(1, n - resets + 1), resets))
        reset_positions = {p + k for k, p in enumerate(picked)}
    else:
        reset_positions = set()

    seq: list[tuple[str, int, bool]] = []
    idx = 0
    prev_grade, prev_width = prev if prev else (None, None)
    for i in range(n):
        grade = rng.choices(grades, weights)[0]
        if i == 0:
            candidates = [1, 2] if 1 in reset_positions else [0, 0, 0, 0, 1]
            candidates = [
                c for c in candidates if not (grade == prev_grade and widths[c] == prev_width)
            ]
            idx = rng.choice(candidates) if candidates else 2
            is_reset = False
        elif i in reset_positions:
            idx = rng.randrange(0, idx)  # strictly wider than the previous run
            is_reset = True
        else:
            next_is_reset = (i + 1) in reset_positions
            same_grade = grade == prev_grade
            if idx == len(widths) - 1:
                step = 0
                if same_grade:
                    grade = _other_grade(grades, weights, grade, rng)
            elif same_grade or (next_is_reset and idx == 0):
                step = 1
            else:
                step = 1 if rng.random() < 0.7 else 0
            idx += step
            is_reset = False
        seq.append((grade, widths[idx], is_reset))
        prev_grade, prev_width = grade, widths[idx]
    return seq


def _other_grade(grades: list[str], weights: list[float], avoid: str, rng: random.Random) -> str:
    for _ in range(20):
        g = rng.choices(grades, weights)[0]
        if g != avoid:
            return g
    return next(g for g in grades if g != avoid)


def _hard_transition(
    cfg: Config,
    seq: list[tuple[str, int, bool]],
    i: int,
    prev: tuple[str, int] | None,
    plant: Plant,
    rng: random.Random,
) -> bool:
    """A planned order-change stop happens on a share of hard grade transitions."""
    prev_grade = seq[i - 1][0] if i > 0 else (prev[0] if prev else None)
    if prev_grade is None:
        return False
    before = cfg.grade_by_code[prev_grade].flute in SPECIALTY_FLUTES
    after = cfg.grade_by_code[seq[i][0]].flute in SPECIALTY_FLUTES
    chance = plant.order_change_stop_fraction * (2.5 if before != after else 0.6)
    return rng.random() < chance


# ----------------------------------------------------------------------------
# 2. Lengths


def _assign_lengths(
    cfg: Config, facts: dict[str, PlannedFact], wet_runs: list[WetEndRun], rng: random.Random
) -> None:
    by_plant: dict[str, list[WetEndRun]] = defaultdict(list)
    for w in wet_runs:
        by_plant[w.shift.plant_code].append(w)

    # Exact plant means (PF-07).
    lengths: dict[int, int] = {}
    for plant in cfg.plants:
        group = by_plant[plant.code]
        mean = facts["PF-07"].expected[plant.code]
        draws = []
        for w in group:
            flute = cfg.grade_by_code[w.grade_code].flute
            factor = 0.6 if flute in SPECIALTY_FLUTES else 1.0
            draws.append(rng.lognormvariate(math.log(mean * factor), 0.35))
        draws = _balance_shifts(cfg, group, draws)
        for w, ft in zip(group, scale_to_sum(draws, mean * len(group), minimum=800), strict=True):
            lengths[id(w)] = ft

    # 32 ECT C share of all feet (PF-10), adjusted inside each plant.
    share = facts["PF-10"].expected["share_pct"] / 100.0
    total = sum(lengths.values())
    vol = [w for w in wet_runs if w.grade_code == "32ECT-C"]
    vol_total = sum(lengths[id(w)] for w in vol)
    want_vol = round(share * total)
    factor = want_vol / vol_total
    vol_by_plant = {
        p.code: [w for w in by_plant[p.code] if w.grade_code == "32ECT-C"] for p in cfg.plants
    }
    new_vol_by_plant = {
        code: round(sum(lengths[id(w)] for w in group) * factor)
        for code, group in vol_by_plant.items()
    }
    largest = max(new_vol_by_plant, key=lambda c: new_vol_by_plant[c])
    new_vol_by_plant[largest] += want_vol - sum(new_vol_by_plant.values())
    for plant in cfg.plants:
        group = by_plant[plant.code]
        plant_total = sum(lengths[id(w)] for w in group)
        vol_group = vol_by_plant[plant.code]
        rest = [w for w in group if w.grade_code != "32ECT-C"]
        new_vol = new_vol_by_plant[plant.code]
        for w, ft in zip(
            vol_group, scale_to_sum([lengths[id(w)] for w in vol_group], new_vol, 800), strict=True
        ):
            lengths[id(w)] = ft
        for w, ft in zip(
            rest,
            scale_to_sum([lengths[id(w)] for w in rest], plant_total - new_vol, 800),
            strict=True,
        ):
            lengths[id(w)] = ft

    for w in wet_runs:
        w.target_ft = lengths[id(w)]


def _estimated_fpm(cfg: Config, w: WetEndRun) -> float:
    machine = cfg.machine_by_code[w.shift.machine_code]
    grade = cfg.grade_by_code[w.grade_code]
    speed = machine.nominal_speed_fpm * machine.speed_factor * grade.speed_factor
    if w.shift.plant_code == "LA":
        months_in = (w.shift.shift_date.year - 2025) * 12 + w.shift.shift_date.month - 7
        speed *= min(1.0, 0.82 + 0.03 * months_in)
    return speed


def _balance_shifts(cfg: Config, group: list[WetEndRun], draws: list[float]) -> list[float]:
    """Rescale each shift's setups so running time tracks the time available.

    Available = scheduled minutes x machine uptime - the configured unaccounted
    slack. The plant total is restored afterwards by scale_to_sum, so this only
    moves feet between shifts; the per-plant mean (PF-07) does not change.
    """
    slack = cfg.raw["calendar"]["unaccounted_minutes_per_shift"]
    by_shift: dict[tuple, list[int]] = defaultdict(list)
    for i, w in enumerate(group):
        by_shift[w.shift.key].append(i)
    out = list(draws)
    for indices in by_shift.values():
        w0 = group[indices[0]]
        machine = cfg.machine_by_code[w0.shift.machine_code]
        available = (w0.shift.scheduled_minutes * machine.uptime_pct / 100.0 - slack) * 60
        estimated = sum(draws[i] / _estimated_fpm(cfg, group[i]) * 60 for i in indices)
        factor = available / estimated if estimated > 0 else 1.0
        for i in indices:
            out[i] = draws[i] * factor
    return out


# ----------------------------------------------------------------------------
# 3. Dry-end runs


def _split_into_dry_end_runs(
    cfg: Config, wet_runs: list[WetEndRun], rng: random.Random
) -> list[Run]:
    runs: list[Run] = []
    weights_by_plant = {p.code: _order_count_weights(p.orders_per_wet_end_run) for p in cfg.plants}
    for setup_counter, w in enumerate(wet_runs, start=1):
        w.setup_id = f"WE-{setup_counter:06d}"
        plant = cfg.plant_by_code[w.shift.plant_code]
        machine = cfg.machine_by_code[w.shift.machine_code]
        grade = cfg.grade_by_code[w.grade_code]
        target_ft = w.target_ft

        counts, weights = weights_by_plant[plant.code]
        n_orders = rng.choices(counts, weights)[0]
        n_orders = max(1, min(n_orders, target_ft // 800))
        cuts = sorted(rng.random() for _ in range(n_orders - 1))
        parts = [b - a for a, b in zip([0.0, *cuts], [*cuts, 1.0], strict=True)]
        feet = scale_to_sum([max(p, 0.08) for p in parts], target_ft, minimum=400)

        for i, ft in enumerate(feet):
            cutoff = _cutoff_in(machine, plant, grade.flute, rng)
            trim_in = round(rng.uniform(0.5, 3.0) * 4) / 4
            outs = rng.choices([1, 2, 3], [0.35, 0.45, 0.20])[0]
            sheet_width = math.floor((w.roll_width_in - trim_in) / outs * 8) / 8
            consumed = round(ft * w.roll_width_in / 12)
            trim = round(ft * trim_in / 12)
            shear_pct = plant.waste_pct_by_shift[w.shift.shift_no] / 100.0 * rng.uniform(0.5, 1.5)
            shear = round(consumed * shear_pct)
            actual_cuts = round(ft * 12 / cutoff)
            overrun = rng.gauss(0.01, 0.035)
            qty = max(100, round(actual_cuts * outs / (1 + overrun) / 50.0) * 50)
            sched_cuts = math.ceil(qty / outs)
            sched_ft = round(sched_cuts * cutoff / 12)
            runs.append(
                Run(
                    run_id="",
                    wet_end_setup_id=w.setup_id,
                    machine_code=machine.code,
                    plant_code=plant.code,
                    order_line_id="",
                    grade_code=grade.code,
                    roll_width_in=w.roll_width_in,
                    knife_position="upper" if i % 2 == 0 else "lower",
                    cutoff_in=cutoff,
                    sheet_width_in=sheet_width,
                    outs=outs,
                    scheduled_lineal_ft=sched_ft,
                    scheduled_cuts=sched_cuts,
                    actual_lineal_ft=ft,
                    actual_cuts=actual_cuts,
                    sqft_produced=consumed - trim - shear,
                    trim_sqft=trim,
                    shear_waste_sqft=shear,
                    starch_qty=0.0,
                    run_start=EPOCH,
                    run_end=EPOCH,
                    shift_date=w.shift.shift_date,
                    shift_no=w.shift.shift_no,
                    stops_count=0,
                    downtime_seconds=0,
                    new_wet_end_setup=i == 0,
                    width_reset=w.width_reset and i == 0,
                    shift=w.shift,
                    seq_in_setup=i,
                )
            )
            w.runs.append(runs[-1])
    return runs


def _order_count_weights(mean: float) -> tuple[list[int], list[float]]:
    """Weights over 1..5 orders per wet-end run whose mean is close to `mean`."""
    counts = list(ORDER_COUNT_WEIGHTS.keys())
    base = list(ORDER_COUNT_WEIGHTS.values())
    # Tilt the base weights geometrically until the mean lands near the target.
    best = base
    best_err = float("inf")
    for k in range(-40, 41):
        tilt = 1.12**k
        w = [b * tilt**c for b, c in zip(base, counts, strict=True)]
        m = sum(c * x for c, x in zip(counts, w, strict=True)) / sum(w)
        if abs(m - mean) < best_err:
            best, best_err = w, abs(m - mean)
    return counts, best


def _cutoff_in(machine: Machine, plant: Plant, flute: str, rng: random.Random) -> float:
    if machine.short_cutoff_fraction and rng.random() < machine.short_cutoff_fraction:
        return round(rng.uniform(14.0, 20.75) * 4) / 4
    low, high = {"ATL": (16.0, 60.0), "CHI": (12.0, 40.0), "PA": (20.0, 60.0), "LA": (16.0, 48.0)}[
        plant.code
    ]
    if machine.code == "ATL-C2":
        low = 21.0
    if flute == "E":
        high = min(high, 30.0)
    return round(rng.uniform(low, high) * 4) / 4


# ----------------------------------------------------------------------------
# 4. Waste calibration


def _scale_shear_to_ratio(group: list[Run], target_pct: float, shear: dict[int, float]) -> None:
    consumed = sum(r.consumed_sqft for r in group)
    trim = sum(r.trim_sqft for r in group)
    want_shear = target_pct / 100.0 * consumed - trim
    current = sum(shear[id(r)] for r in group)
    if current <= 0 or want_shear <= 0:
        return
    factor = want_shear / current
    for r in group:
        shear[id(r)] *= factor


def _calibrate_waste(cfg: Config, facts: dict[str, PlannedFact], runs: list[Run]) -> None:
    """Hit the shift and cutoff waste targets by scaling shear waste.

    Consumed board is fixed, trim is physical, so waste % = (trim + shear) /
    consumed is set by shear alone. Atlanta has overlapping constraints (plant
    by shift, ATL-C2 by cutoff), solved by iterative proportional fitting.
    """
    shear: dict[int, float] = {id(r): float(r.shear_waste_sqft) for r in runs}
    pf06 = facts["PF-06"].expected
    pf16 = facts["PF-16"].expected

    constraints: list[tuple[list[Run], float]] = []
    for plant in cfg.plants:
        for shift_no, pct in plant.waste_pct_by_shift.items():
            group = [r for r in runs if r.plant_code == plant.code and r.shift_no == shift_no]
            if plant.code == "ATL":
                pct = {1: pf06["atl_shift1_pct"], 3: pf06["atl_shift3_pct"]}.get(shift_no, pct)
            constraints.append((group, pct))
    short = [r for r in runs if r.machine_code == "ATL-C2" and r.cutoff_in < 21]
    long_ = [r for r in runs if r.machine_code == "ATL-C2" and r.cutoff_in >= 21]
    constraints.append((short, pf16["short_cutoff_pct"]))
    constraints.append((long_, pf16["long_cutoff_pct"]))

    for _ in range(60):
        for group, pct in constraints:
            _scale_shear_to_ratio(group, pct, shear)

    for r in runs:
        consumed = r.consumed_sqft
        r.shear_waste_sqft = max(0, round(shear[id(r)]))
        r.sqft_produced = consumed - r.trim_sqft - r.shear_waste_sqft


# ----------------------------------------------------------------------------
# 5. Speed and starch


def _assign_speeds(
    cfg: Config, facts: dict[str, PlannedFact], runs: list[Run], rng: random.Random
) -> None:
    fpm: dict[int, float] = {}
    for r in runs:
        machine = cfg.machine_by_code[r.machine_code]
        grade = cfg.grade_by_code[r.grade_code]
        speed = machine.nominal_speed_fpm * machine.speed_factor * grade.speed_factor
        if r.plant_code == "LA":
            months_in = (r.shift_date.year - 2025) * 12 + r.shift_date.month - 7
            speed *= min(1.0, 0.82 + 0.03 * months_in)
        if r.shift_no == 3 and r.plant_code == "ATL":
            speed *= 0.97
        fpm[id(r)] = speed * rng.gauss(1.0, 0.06)

    pf11 = facts["PF-11"].expected
    targets = (("71ECT-BC", pf11["fpm_71ect_bc"]), ("32ECT-C", pf11["fpm_32ect_c"]))
    for grade_code, target in targets:
        group = [r for r in runs if r.machine_code == "CHI-C1" and r.grade_code == grade_code]
        for r, v in zip(group, scale_group_mean([fpm[id(r)] for r in group], target), strict=True):
            fpm[id(r)] = v

    def _seconds(r: Run) -> int:
        return max(20, round(r.actual_lineal_ft / fpm[id(r)] * 60))

    # Whole seconds move the realised mean a little; nudge the group and redo.
    for _ in range(4):
        for grade_code, target in targets:
            group = [r for r in runs if r.machine_code == "CHI-C1" and r.grade_code == grade_code]
            realised = sum(r.actual_lineal_ft / (_seconds(r) / 60) for r in group) / len(group)
            for r in group:
                fpm[id(r)] *= target / realised

    for r in runs:
        r.run_seconds = _seconds(r)


def _assign_starch(
    cfg: Config, facts: dict[str, PlannedFact], runs: list[Run], rng: random.Random
) -> None:
    """Starch in pounds per run; LA 44ECT-C-MR calibrated by quarter (PF-15).

    Values are left in pounds here. The messiness pass converts the first three
    LA months to kilograms.
    """
    pf15 = facts["PF-15"].expected
    by_quarter: dict[str, float] = dict(cfg.quality["starch_mr_lb_per_msf_by_quarter"])
    by_quarter["2025Q3"] = pf15["q3_2025_lb_per_msf"]
    by_quarter["2026Q3"] = pf15["q3_2026_lb_per_msf"]

    groups: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        grade = cfg.grade_by_code[r.grade_code]
        msf = r.sqft_produced / 1000.0
        r.starch_qty = msf * grade.starch_lb_per_msf * rng.gauss(1.0, 0.08)
        if r.machine_code == "LA-C1" and r.grade_code == "44ECT-C-MR":
            groups[quarter_key(r.shift_date)].append(r)
    for quarter, group in groups.items():
        target = by_quarter.get(quarter)
        if target is None:
            continue
        msf_total = sum(r.sqft_produced for r in group) / 1000.0
        current = sum(r.starch_qty for r in group)
        factor = target * msf_total / current
        for r in group:
            r.starch_qty *= factor
    for r in runs:
        r.starch_qty = round(r.starch_qty, 1)
