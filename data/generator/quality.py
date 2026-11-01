"""Quality tests: lab records per wet-end setup, per shift, and per order.

Frequencies follow the spec's table, read at the grain the generator has:

- per wet-end setup: ECT (Mullen for the Mullen grades), and moisture at
  Chicago, where board comes off trailers in winter;
- per machine-shift: caliper once, moisture once outside Chicago, pin adhesion
  twice (start and after the break);
- per order: warp on double wall and E flute, score quality where scored;
- ring crush on incoming paper, once per plant per weekday.

Failure rates are exact per calibrated group: LA score quality by quarter
(PF-04), Chicago moisture by season (PF-05), Atlanta pin adhesion (PF-20).
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict

from .calibrate import exact_count_flags
from .config import Config, Grade, PlannedFact
from .model import OrderLine, QualityTest, Run, WetEndRun
from .shifts import is_summer, is_winter, quarter_key

FAIL_COMMENTS = {
    "ECT": ["below grade, held for retest", "low ECT, checked liner"],
    "Mullen": ["burst below spec", "low Mullen, checked medium"],
    "moisture": ["board too wet, warp risk", "moisture high off the trailer"],
    "caliper": ["crushed flute", "caliper low at the operator side"],
    "pin_adhesion": ["weak bond, glue line light", "pins pulled, humid"],
    "warp": ["up warp over limit", "down warp, rejected"],
    "score": ["score cracked", "score line off, slitter drift"],
    "ring_crush": ["component below spec", "soft medium"],
}
RING_CRUSH_SPEC = {23: 44.0, 26: 50.0, 30: 60.0, 33: 68.0, 35: 72.0, 42: 90.0, 69: 150.0}


def build_quality(
    cfg: Config,
    facts: dict[str, PlannedFact],
    wet_runs: list[WetEndRun],
    runs: list[Run],
    lines: list[OrderLine],
    rng: random.Random,
) -> list[QualityTest]:
    line_by_id = {line.order_line_id: line for line in lines}
    tests: list[QualityTest] = []

    def test(**kwargs: object) -> QualityTest:
        t = QualityTest(
            test_id="",
            measured_value=0.0,
            unit="",
            spec_min=None,
            spec_max=None,
            result="pass",
            comment=None,
            recorded_at=dt.datetime(2000, 1, 1),
            **kwargs,  # type: ignore[arg-type]
        )
        tests.append(t)
        return t

    # Per setup
    for w in wet_runs:
        if not w.runs:
            continue
        first = w.runs[0]
        grade = cfg.grade_by_code[w.grade_code]
        base = {
            "plant_code": first.plant_code,
            "machine_code": first.machine_code,
            "grade_code": w.grade_code,
            "wet_end_setup_id": w.setup_id,
            "run_id": first.run_id,
            "order_line_id": None,
        }
        at = first.run_start + dt.timedelta(minutes=rng.randint(5, 25))
        strength = "Mullen" if grade.test_basis == "Mullen" else "ECT"
        test(test_type=strength, sampled_at=at, **base)
        if first.plant_code == "CHI":  # board off winter trailers: moisture checked every setup
            moisture_at = at + dt.timedelta(minutes=rng.randint(0, 10))
            test(test_type="moisture", sampled_at=moisture_at, **base)

    # Per shift
    by_shift: dict[tuple, list[WetEndRun]] = defaultdict(list)
    for w in wet_runs:
        if w.runs:
            by_shift[w.shift.key].append(w)
    for key in sorted(by_shift, key=lambda k: (k[1], k[2], k[0])):
        setups = by_shift[key]
        shift = setups[0].shift
        # Pin adhesion twice a shift, at the start and after the midday break.
        for test_type, lo, hi in (
            ("caliper", 30, 120),
            ("moisture", 20, 100),
            ("pin_adhesion", 15, 90),
            ("pin_adhesion", 250, 330),
        ):
            if test_type == "moisture" and shift.plant_code == "CHI":
                continue
            at = shift.start + dt.timedelta(minutes=rng.randint(lo, hi))
            w = min(setups, key=lambda s: abs((s.runs[0].run_start - at).total_seconds()))
            test(
                test_type=test_type,
                sampled_at=at,
                plant_code=shift.plant_code,
                machine_code=shift.machine_code,
                grade_code=w.grade_code,
                wet_end_setup_id=w.setup_id,
                run_id=w.runs[0].run_id,
                order_line_id=None,
            )

    # Per order
    for r in runs:
        grade = cfg.grade_by_code[r.grade_code]
        line = line_by_id.get(r.order_line_id)
        base = {
            "plant_code": r.plant_code,
            "machine_code": r.machine_code,
            "grade_code": r.grade_code,
            "wet_end_setup_id": r.wet_end_setup_id,
            "run_id": r.run_id,
            "order_line_id": r.order_line_id,
        }
        end = max(r.run_start, r.run_end)
        if grade.flute in ("BC", "E") and rng.random() < 0.3:
            test(
                test_type="warp", sampled_at=end + dt.timedelta(minutes=rng.randint(5, 60)), **base
            )
        scored = line is not None and line.score_pattern != "none"
        if scored and rng.random() < (0.65 if r.plant_code == "LA" else 0.18):
            test(
                test_type="score", sampled_at=end + dt.timedelta(minutes=rng.randint(5, 60)), **base
            )

    # Ring crush at receiving
    day = cfg.period_start
    while day <= cfg.period_end:
        if day.weekday() < 5 and day not in cfg.holidays:
            for plant in cfg.plants:
                if day < plant.data_start:
                    continue
                at = dt.datetime.combine(day, dt.time(rng.randint(7, 9), rng.randint(0, 59)))
                test(
                    test_type="ring_crush",
                    sampled_at=at,
                    plant_code=plant.code,
                    machine_code=None,
                    grade_code=None,
                    wet_end_setup_id=None,
                    run_id=None,
                    order_line_id=None,
                )
        day += dt.timedelta(days=1)

    _assign_results(cfg, facts, tests, rng)
    tests.sort(key=lambda t: (t.sampled_at, t.plant_code, t.test_type, t.run_id or ""))
    for n, t in enumerate(tests, start=1):
        t.test_id = f"QT-{n:07d}"
        t.recorded_at = t.sampled_at + dt.timedelta(minutes=rng.randint(10, 90))
    return tests


# ----------------------------------------------------------------------------


def _group(cfg: Config, facts: dict[str, PlannedFact], t: QualityTest) -> tuple[str, float]:
    """Calibration group and its failure rate in percent for one test."""
    q = cfg.quality
    base = q["base_fail_pct"]
    day = t.sampled_at.date()
    if t.test_type == "score" and t.plant_code == "LA":
        quarter = quarter_key(day)
        pf04 = facts["PF-04"].expected
        rate = {"2025Q3": pf04["q3_2025_pct"], "2026Q3": pf04["q3_2026_pct"]}.get(quarter)
        if rate is None:
            rate = q["la_score_by_quarter"].get(quarter, base["score"])
        return f"score/LA/{quarter}", rate
    if t.test_type == "moisture" and t.plant_code == "CHI":
        m = q["chicago_moisture_by_month"]
        pf05 = facts["PF-05"].expected
        if is_winter(day) and (day >= dt.date(2025, 12, 1)):
            return "moisture/CHI/winter", pf05["winter_pct"]
        if is_winter(day):
            return "moisture/CHI/winter_2024", m["winter_2024"]
        if is_summer(day) and day.year == 2025:
            return "moisture/CHI/summer", pf05["summer_pct"]
        if is_summer(day):
            return "moisture/CHI/summer_2026", m["summer_2026"]
        return "moisture/CHI/default", m["default"]
    if t.test_type == "pin_adhesion" and t.plant_code == "ATL":
        p = q["atlanta_pin_adhesion"]
        pf20 = facts["PF-20"].expected
        if day.year == 2025 and is_summer(day):
            return "pin/ATL/summer_2025", pf20["summer_2025_pct"]
        if day.year == 2025:
            return "pin/ATL/rest_2025", pf20["rest_of_2025_pct"]
        if is_summer(day):
            return "pin/ATL/summer_2026", p["summer_2026"]
        return "pin/ATL/other", p["other"]
    if t.test_type == "warp" and t.plant_code == "CHI" and is_winter(day):
        return "warp/CHI/winter", q["chicago_warp_winter_pct"]
    if t.test_type == "ECT" and t.plant_code == "LA" and day.year == 2025:
        return "ECT/LA/2025", base["ECT"] * 2
    return f"{t.test_type}/{t.plant_code}", base[t.test_type]


def _assign_results(
    cfg: Config, facts: dict[str, PlannedFact], tests: list[QualityTest], rng: random.Random
) -> None:
    groups: dict[str, tuple[float, list[QualityTest]]] = {}
    for t in tests:
        key, rate = _group(cfg, facts, t)
        groups.setdefault(key, (rate, []))[1].append(t)
    for _key, (rate, members) in sorted(groups.items()):
        for t, fail in zip(members, exact_count_flags(rng, len(members), rate), strict=True):
            grade = cfg.grade_by_code[t.grade_code] if t.grade_code else None
            _measure(t, grade, fail, rng)
            if fail:
                t.result = "fail"
                t.comment = rng.choice(FAIL_COMMENTS[t.test_type])


def _measure(t: QualityTest, grade: Grade | None, fail: bool, rng: random.Random) -> None:
    kind = t.test_type
    if kind in ("ECT", "Mullen"):
        assert grade is not None
        target = float(grade.test_target)
        t.unit = "lbf/in" if kind == "ECT" else "psi"
        t.spec_min = target
        t.measured_value = round(
            target * (rng.uniform(0.86, 0.985) if fail else rng.uniform(1.02, 1.15)), 1
        )
    elif kind == "moisture":
        t.unit, t.spec_min, t.spec_max = "%", 5.5, 9.0
        t.measured_value = round(rng.uniform(9.2, 12.5) if fail else rng.uniform(6.0, 8.6), 1)
    elif kind == "caliper":
        assert grade is not None
        t.unit = "in"
        t.spec_min, t.spec_max = (
            round(grade.caliper_in * 0.92, 3),
            round(grade.caliper_in * 1.08, 3),
        )
        factor = rng.uniform(0.84, 0.91) if fail else rng.uniform(0.95, 1.05)
        t.measured_value = round(grade.caliper_in * factor, 3)
    elif kind == "pin_adhesion":
        t.unit, t.spec_min = "lbf", 45.0
        t.measured_value = round(rng.uniform(30.0, 44.0) if fail else rng.uniform(50.0, 75.0), 1)
    elif kind == "warp":
        t.unit, t.spec_max = "in/ft", 0.25
        t.measured_value = round(rng.uniform(0.27, 0.6) if fail else rng.uniform(0.02, 0.2), 3)
    elif kind == "score":
        t.unit, t.spec_max = "% cracked", 3.0
        t.measured_value = round(rng.uniform(3.5, 12.0) if fail else rng.uniform(0.0, 2.5), 1)
    elif kind == "ring_crush":
        weight = rng.choice(list(RING_CRUSH_SPEC))
        spec = RING_CRUSH_SPEC[weight]
        t.unit, t.spec_min = "lbf", spec
        t.comment = f"{weight} lb component"
        t.measured_value = round(
            spec * (rng.uniform(0.85, 0.98) if fail else rng.uniform(1.02, 1.25)), 1
        )
    else:
        raise ValueError(kind)
