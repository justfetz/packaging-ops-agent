"""Order lines behind every dry-end run, with shipping, price, and cost.

Every production run is one order line (one order can hold up to three lines
for the same customer). Lines carry the commercial facts: OTIF by plant
(PF-12), the paper cost increases and the Atlanta anchor's price lag (PF-13),
the LA anchor's share of shipped sheets (PF-14), and the margin by customer
(PF-19). The standard cost table is a reference feed of its own.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict

from .calibrate import distribute_count
from .config import Config, Customer, PlannedFact
from .model import OrderLine, Run
from .shifts import month_key, quarter_key

ANCHOR_ATL = "C001"
ANCHOR_LA = "C023"
SCORE_PATTERNS = ["none", "standard", "male-female", "tele-twin"]
SCORE_WEIGHTS = {"LA": [0.10, 0.60, 0.25, 0.05], "default": [0.45, 0.40, 0.12, 0.03]}
NOTES = [
    None,
    None,
    None,
    None,
    "rush",
    "hold for full truck",
    "call before delivery",
    "no partials",
]


def build_orders(
    cfg: Config, facts: dict[str, PlannedFact], runs: list[Run], rng: random.Random
) -> list[OrderLine]:
    lines: list[OrderLine] = []
    run_by_line: dict[int, Run] = {}
    price_factor = _price_factors(cfg, rng)

    by_plant: dict[str, list[Run]] = defaultdict(list)
    for r in runs:
        by_plant[r.plant_code].append(r)

    order_counter = 0
    for plant in cfg.plants:
        plant_runs = sorted(by_plant[plant.code], key=lambda r: (r.run_start, r.run_id))
        customers = cfg.customers_at(plant.code)
        weights = [c.share for c in customers]
        current: Customer | None = None
        order_lines = 0
        for r in plant_runs:
            customer = rng.choices(customers, weights)[0]
            if customer is not current or order_lines >= 3 or rng.random() < 0.4:
                order_counter += 1
                current = customer
                order_lines = 0
            order_lines += 1
            r.customer_id = customer.id
            line = _line(cfg, r, customer, order_counter, price_factor, rng)
            lines.append(line)
            run_by_line[id(line)] = r

    _calibrate_otif(cfg, facts, lines, rng)
    _calibrate_la_share(facts, lines, run_by_line)
    _calibrate_margins(cfg, facts, lines)
    _number(lines)
    for line in lines:
        run_by_line[id(line)].order_line_id = line.order_line_id
    return lines


# ----------------------------------------------------------------------------


def _line(
    cfg: Config,
    r: Run,
    customer: Customer,
    order_no: int,
    price_factor: dict[tuple[str, str], float],
    rng: random.Random,
) -> OrderLine:
    plant = r.plant_code
    run_date = r.run_start.date()
    ship_ready = run_date + dt.timedelta(days=rng.randint(1, 2))
    requested = ship_ready + dt.timedelta(days=rng.randint(0, 2))
    lead = rng.randint(customer.lead_days[0], customer.lead_days[1])
    order_date = requested - dt.timedelta(days=lead)
    qty = r.scheduled_cuts * r.outs
    pattern = rng.choices(SCORE_PATTERNS, SCORE_WEIGHTS.get(plant, SCORE_WEIGHTS["default"]))[0]
    unit = rng.choice([20, 25, 30, 40, 50, 60])
    price = cfg.grade_by_code[r.grade_code].price_per_msf
    price *= price_factor[(customer.id, r.grade_code)]
    price *= _price_index(cfg, customer, ship_ready) * rng.gauss(1.0, 0.015)
    cost = cfg.grade_by_code[r.grade_code].cost_per_msf * _cost_index(cfg, ship_ready)
    cost *= rng.gauss(1.0, 0.03)
    return OrderLine(
        order_id=f"ORD-{order_no:06d}",
        order_line_id="",
        line_version=1,
        customer_id=customer.id,
        plant_code=plant,
        order_date=order_date,
        requested_ship_date=requested,
        grade_code=r.grade_code,
        qty_sheets=qty,
        sheet_width_in=r.sheet_width_in,
        sheet_length_in=r.cutoff_in,
        score_pattern=pattern,
        unitizing="banded" if rng.random() < 0.5 else "palletized",
        unit_count=unit,
        roll_width_in=r.roll_width_in,
        price_per_msf=round(price, 2),
        std_cost_per_msf=round(cost, 2),
        shipped_date=ship_ready,
        shipped_qty=qty,
        scheduling_notes=rng.choice(NOTES),
        updated_at=dt.datetime.combine(order_date, dt.time(rng.randint(8, 16), rng.randint(0, 59))),
    )


def _price_factors(cfg: Config, rng: random.Random) -> dict[tuple[str, str], float]:
    """A negotiated level per customer and grade, fixed for the whole period."""
    out: dict[tuple[str, str], float] = {}
    for c in cfg.customers:
        base = 0.88 if c.id == ANCHOR_ATL else rng.uniform(0.95, 1.08)
        for g in cfg.grades:
            out[(c.id, g.code)] = base * rng.uniform(0.97, 1.03)
    return out


def _cost_index(cfg: Config, day: dt.date) -> float:
    index = 1.0
    for inc in cfg.cost_increases:
        if month_key(day) >= str(inc["month"]):
            index *= 1 + inc["pct"] / 100.0
    return index


def _price_index(cfg: Config, customer: Customer, day: dt.date) -> float:
    lag = cfg.anchor_price_lag_months if customer.id == ANCHOR_ATL else cfg.price_lag_months
    index = 1.0
    for inc in cfg.cost_increases:
        year, month = (int(x) for x in str(inc["month"]).split("-"))
        month += lag
        year, month = year + (month - 1) // 12, (month - 1) % 12 + 1
        if month_key(day) >= f"{year:04d}-{month:02d}":
            index *= 1 + inc["pct"] / 100.0
    return index


def standard_cost_rows(cfg: Config) -> list[dict[str, object]]:
    """The reference feed ref__standard_cost: grade by month, cost per MSF."""
    rows = []
    day = cfg.period_start.replace(day=1)
    while day <= cfg.period_end:
        for g in cfg.grades:
            rows.append(
                {
                    "grade_code": g.code,
                    "month": day,
                    "cost_per_msf": round(g.cost_per_msf * _cost_index(cfg, day), 2),
                }
            )
        day = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return rows


# ----------------------------------------------------------------------------
# Calibrations


def _calibrate_otif(
    cfg: Config, facts: dict[str, PlannedFact], lines: list[OrderLine], rng: random.Random
) -> None:
    pf12 = facts["PF-12"].expected
    rates = dict(cfg.otif["plant_pct"])
    rates["CHI"], rates["PA"] = pf12["CHI"], pf12["PA"]
    by_plant: dict[str, list[OrderLine]] = defaultdict(list)
    for line in lines:
        by_plant[line.plant_code].append(line)
    total_hits = round(pf12["companywide_pct"] / 100.0 * len(lines))
    hits = {p: round(rates[p] / 100.0 * len(by_plant[p])) for p in ("CHI", "PA")}
    free = [p for p in by_plant if p not in hits]
    remaining = total_hits - sum(hits.values())
    sizes = [len(by_plant[p]) for p in free]
    split = distribute_count(
        rng,
        len(free),
        remaining,
        0,
        sizes,
        [rates[p] * n for p, n in zip(free, sizes, strict=True)],
    )
    hits.update(dict(zip(free, split, strict=True)))

    late_share = cfg.otif["late_share_of_misses"]
    for plant, plant_lines in by_plant.items():
        flags = [True] * hits[plant] + [False] * (len(plant_lines) - hits[plant])
        rng.shuffle(flags)
        for line, ok in zip(plant_lines, flags, strict=True):
            line.otif = ok
            assert line.shipped_qty is not None and line.shipped_date is not None
            if ok:
                line.shipped_qty = round(line.qty_sheets * rng.uniform(0.93, 1.07))
                continue
            miss = rng.random()
            late = miss < late_share or miss > 0.85
            short = miss >= late_share
            if late:
                line.shipped_date = line.requested_ship_date + dt.timedelta(days=rng.randint(1, 6))
            if short:
                ratio = rng.uniform(0.72, 0.88) if rng.random() < 0.8 else rng.uniform(1.12, 1.25)
                line.shipped_qty = round(line.qty_sheets * ratio)
            else:
                line.shipped_qty = round(line.qty_sheets * rng.uniform(0.93, 1.07))


def _calibrate_la_share(
    facts: dict[str, PlannedFact], lines: list[OrderLine], run_by_line: dict[int, Run]
) -> None:
    """Scale the LA anchor's quantities so its share of shipped sheets is exact (PF-14)."""
    share = facts["PF-14"].expected["share_pct"] / 100.0
    la = [line for line in lines if line.plant_code == "LA"]
    anchor = [line for line in la if line.customer_id == ANCHOR_LA]
    others = sum(line.shipped_qty or 0 for line in la if line.customer_id != ANCHOR_LA)
    current = sum(line.shipped_qty or 0 for line in anchor)
    want = round(share / (1 - share) * others)
    factor = want / current
    for line in anchor:
        assert line.shipped_qty is not None
        line.shipped_qty = max(50, round(line.shipped_qty * factor))
        line.qty_sheets = max(50, round(line.qty_sheets * factor))
    largest = max(anchor, key=lambda line: line.shipped_qty or 0)
    residual = want - sum(line.shipped_qty or 0 for line in anchor)
    assert largest.shipped_qty is not None
    largest.shipped_qty += residual
    largest.qty_sheets += residual
    for line in anchor:
        run = run_by_line[id(line)]
        run.scheduled_cuts = -(-line.qty_sheets // run.outs)
        run.scheduled_lineal_ft = round(run.scheduled_cuts * run.cutoff_in / 12)


def _revenue(line: OrderLine) -> float:
    return line.msf * line.price_per_msf


def _scale_costs(group: list[OrderLine], target_cost: float) -> None:
    current = sum(line.msf * line.std_cost_per_msf for line in group)
    factor = target_cost / current
    for line in group:
        line.std_cost_per_msf = round(line.std_cost_per_msf * factor, 2)


def _calibrate_margins(cfg: Config, facts: dict[str, PlannedFact], lines: list[OrderLine]) -> None:
    pf13 = facts["PF-13"].expected
    pf19 = facts["PF-19"].expected
    by_customer: dict[str, list[OrderLine]] = defaultdict(list)
    for line in lines:
        by_customer[line.customer_id].append(line)
    for customer in cfg.customers:
        group = by_customer[customer.id]
        margin = customer.margin_pct
        if customer.id == pf19["highest_customer"]:
            margin = pf19["highest_margin_pct"]
        if customer.id == pf19["lowest_customer"]:
            margin = pf19["lowest_margin_pct"]
        revenue = sum(_revenue(line) for line in group)
        if customer.id != ANCHOR_ATL:
            _scale_costs(group, revenue * (1 - margin / 100.0))
            continue
        # The Atlanta anchor: Q1 and Q2 2025 are pinned, the rest makes the period exact.
        q1 = [
            line for line in group if quarter_key(line.shipped_date or line.order_date) == "2025Q1"
        ]
        q2 = [
            line for line in group if quarter_key(line.shipped_date or line.order_date) == "2025Q2"
        ]
        rest = [line for line in group if line not in q1 and line not in q2]
        _scale_costs(
            q1, sum(_revenue(line) for line in q1) * (1 - pf13["anchor_margin_q1_2025_pct"] / 100.0)
        )
        _scale_costs(
            q2, sum(_revenue(line) for line in q2) * (1 - pf13["anchor_margin_q2_2025_pct"] / 100.0)
        )
        pinned_cost = sum(line.msf * line.std_cost_per_msf for line in [*q1, *q2])
        _scale_costs(rest, revenue * (1 - margin / 100.0) - pinned_cost)


def _number(lines: list[OrderLine]) -> None:
    lines.sort(key=lambda line: (line.order_date, line.order_id, line.updated_at))
    order_ids: dict[str, str] = {}
    for n, line in enumerate(lines, start=1):
        if line.order_id not in order_ids:
            order_ids[line.order_id] = f"ORD-{len(order_ids) + 1:06d}"
        line.order_id = order_ids[line.order_id]
        line.order_line_id = f"OL-{n:06d}"
