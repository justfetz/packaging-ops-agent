"""Load data/config.yaml and data/planted_facts.yaml into typed objects.

The YAML files are the single source of the spec's numbers. This module only
reshapes them so the rest of the generator can use attribute access and does
not repeat string keys everywhere.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = DATA_DIR / "config.yaml"
DEFAULT_FACTS = DATA_DIR / "planted_facts.yaml"


@dataclass(frozen=True)
class ShiftDef:
    shift_no: int
    start: dt.time
    minutes: int


@dataclass(frozen=True)
class Plant:
    code: str
    name: str
    city: str
    state: str
    timezone: str
    commissioned_year: int
    data_start: dt.date
    market: str
    character: str
    wet_end_runs_per_shift: float
    wet_end_run_length_ft: int
    width_resets_per_shift: float
    orders_per_wet_end_run: float
    waste_pct_by_shift: dict[int, float]
    order_change_stop_fraction: float


@dataclass(frozen=True)
class Machine:
    code: str
    plant: str
    width_in: int
    commissioned_year: int
    nominal_speed_fpm: int
    capability: str
    weak_spot: str
    roll_widths_in: list[int]
    uptime_pct: float
    grade_mix: dict[str, float]
    speed_factor: float
    short_cutoff_fraction: float = 0.0


@dataclass(frozen=True)
class Grade:
    code: str
    flute: str
    recipe: str
    test_basis: str
    test_target: int
    caliper_in: float
    speed_factor: float
    price_per_msf: float
    cost_per_msf: float
    starch_lb_per_msf: float
    runs_mainly_at: str
    notes: str


@dataclass(frozen=True)
class Customer:
    id: str
    name: str
    segment: str
    home_plant: str
    share: float
    contract: str
    escalator: bool
    margin_pct: float
    lead_days: tuple[int, int]


@dataclass(frozen=True)
class Cause:
    code: str
    category: str
    planned: bool
    minutes: tuple[int, int]
    section: str | None
    planted: bool = False
    weights: dict[str, float] = field(default_factory=dict)
    third_shift_multiplier: dict[str, float] = field(default_factory=dict)
    winter_multiplier: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class FaultCode:
    code: str
    section: str | None
    description: str
    cause: str


@dataclass(frozen=True)
class PlannedFact:
    id: str
    fact: str
    tables: list[str]
    definition: str
    expected: dict[str, Any]
    tolerance: dict[str, float]


class Config:
    """Typed view over config.yaml. Raw dict stays available as `.raw`."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        company = raw["company"]
        self.company_name: str = company["name"]
        self.period_start: dt.date = _date(company["period_start"])
        self.period_end: dt.date = _date(company["period_end"])

        cal = raw["calendar"]
        self.shift_defs = [
            ShiftDef(s["shift_no"], dt.time.fromisoformat(s["start"]), s["minutes"])
            for s in cal["shifts"]
        ]
        self.overtime = cal["overtime_saturdays"]
        self.holidays = {_date(d) for d in cal["holidays"]}

        self.plants = [
            Plant(
                **{
                    **p,
                    "data_start": _date(p["data_start"]),
                    "waste_pct_by_shift": {
                        int(k): float(v) for k, v in p["waste_pct_by_shift"].items()
                    },
                }
            )
            for p in raw["plants"]
        ]
        self.machines = [Machine(**m) for m in raw["machines"]]
        self.grades = [Grade(**g) for g in raw["grades"]]
        self.customers = [
            Customer(**{**c, "lead_days": (c["lead_days"][0], c["lead_days"][1])})
            for c in raw["customers"]
        ]
        self.causes = [
            Cause(**{**c, "minutes": (c["minutes"][0], c["minutes"][1])})
            for c in raw["downtime_causes"]
        ]
        self.fault_codes = [FaultCode(**f) for f in raw["fault_codes"]]
        self.messiness: dict[str, Any] = raw["messiness"]
        self.quality: dict[str, Any] = raw["quality"]
        self.otif: dict[str, Any] = raw["otif"]
        self.cost_increases: list[dict[str, Any]] = raw["cost_increases"]
        self.price_lag_months: int = raw["price_lag_months"]
        self.anchor_price_lag_months: int = raw["anchor_price_lag_months"]
        self.planned_flex_weights: dict[str, float] = raw["planned_flex_weights"]
        self.missplice_per_month: dict[str, Any] = raw["missplice_per_month"]
        self.boiler_events: list[dict[str, Any]] = raw["boiler_events"]
        self.power_outages: list[dict[str, Any]] = raw["power_outages"]

        self.plant_by_code = {p.code: p for p in self.plants}
        self.machine_by_code = {m.code: m for m in self.machines}
        self.grade_by_code = {g.code: g for g in self.grades}
        self.customer_by_id = {c.id: c for c in self.customers}
        self.cause_by_code = {c.code: c for c in self.causes}

    def machines_at(self, plant_code: str) -> list[Machine]:
        return [m for m in self.machines if m.plant == plant_code]

    def customers_at(self, plant_code: str) -> list[Customer]:
        return [c for c in self.customers if c.home_plant == plant_code]


def _date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with path.open() as handle:
        return Config(yaml.safe_load(handle))


def load_facts(path: Path = DEFAULT_FACTS) -> dict[str, PlannedFact]:
    with path.open() as handle:
        items = yaml.safe_load(handle)
    facts = {}
    for item in items:
        facts[item["id"]] = PlannedFact(
            id=item["id"],
            fact=item["fact"],
            tables=item["tables"],
            definition=item["definition"],
            expected=item["expected"],
            tolerance=item.get("tolerance", {}),
        )
    return facts
