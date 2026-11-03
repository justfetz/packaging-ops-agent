"""Record types for the raw feeds.

Field names are the column names in the output files. Every feed is one list
of one dataclass, so the writers and the fact checks share a vocabulary.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Shift:
    """One scheduled machine-shift. The calendar builds these first."""

    machine_code: str
    plant_code: str
    shift_date: dt.date
    shift_no: int
    start: dt.datetime
    scheduled_minutes: int
    is_overtime: bool = False

    @property
    def end(self) -> dt.datetime:
        return self.start + dt.timedelta(minutes=self.scheduled_minutes)

    @property
    def key(self) -> tuple[str, dt.date, int]:
        return (self.machine_code, self.shift_date, self.shift_no)


@dataclass
class WetEndRun:
    """One grade at one web width. Not a raw feed; runs carry its id."""

    setup_id: str
    shift: Shift
    grade_code: str
    roll_width_in: int
    width_reset: bool
    has_order_change_stop: bool
    target_ft: int = 0
    setup_seconds: int = 0  # wet-end change time at crawl before the first run
    runs: list[Run] = field(default_factory=list)

    @property
    def lineal_ft(self) -> int:
        return sum(r.actual_lineal_ft for r in self.runs)


@dataclass
class Run:
    """A dry-end run: one order on one knife. Feed raw__production_runs."""

    run_id: str
    wet_end_setup_id: str
    machine_code: str
    plant_code: str
    order_line_id: str
    grade_code: str
    roll_width_in: int
    knife_position: str
    cutoff_in: float
    sheet_width_in: float
    outs: int
    scheduled_lineal_ft: int
    scheduled_cuts: int
    actual_lineal_ft: int
    actual_cuts: int
    sqft_produced: int
    trim_sqft: int
    shear_waste_sqft: int
    starch_qty: float
    run_start: dt.datetime
    run_end: dt.datetime
    shift_date: dt.date
    shift_no: int
    stops_count: int
    downtime_seconds: int
    new_wet_end_setup: bool
    width_reset: bool
    setup_minutes: float = 0.0  # wet-end change time; on the first run of a setup, else 0
    # generator-only state, not written
    run_seconds: int = 0  # running time at speed, before stops are added
    customer_id: str = ""
    shift: Shift | None = None
    seq_in_setup: int = 0

    @property
    def consumed_sqft(self) -> int:
        return self.sqft_produced + self.trim_sqft + self.shear_waste_sqft


@dataclass
class StopEvent:
    """Feed raw__stop_events (JSON lines)."""

    event_id: str
    machine_code: str
    start_time: dt.datetime
    end_time: dt.datetime
    duration_seconds: int
    machine_section: str | None
    fault_code: str | None
    cause_code: str | None
    comment: str | None
    # generator-only
    true_cause: str = ""
    shift: Shift | None = None
    setup: WetEndRun | None = None  # the setup it precedes, for before_setup events
    run: Run | None = None  # the run it interrupted, set once runs exist
    placement: str = "in_run"  # in_run, before_setup, standalone, fixed


@dataclass
class ShiftSummary:
    """Feed raw__shift_summaries (JSON lines)."""

    summary_id: str
    machine_code: str
    shift_date: dt.date
    shift_no: int
    shift_start: dt.datetime
    shift_end: dt.datetime
    scheduled_minutes: int
    crew_lead_id: str
    crew_lead_name: str
    run_count: int
    total_lineal_ft: int
    total_sqft_produced: int
    total_trim_sqft: int
    total_shear_waste_sqft: int
    total_cuts: int
    stops_count: int
    downtime_seconds: int
    emitted_at: dt.datetime


@dataclass
class OrderLine:
    """Feed raw__order_lines. A line edited after download appears twice."""

    order_id: str
    order_line_id: str
    line_version: int
    customer_id: str
    plant_code: str
    order_date: dt.date
    requested_ship_date: dt.date
    grade_code: str
    qty_sheets: int
    sheet_width_in: float
    sheet_length_in: float
    score_pattern: str
    unitizing: str
    unit_count: int
    roll_width_in: int
    price_per_msf: float
    std_cost_per_msf: float
    shipped_date: dt.date | None
    shipped_qty: int | None
    scheduling_notes: str | None
    updated_at: dt.datetime
    # generator-only
    otif: bool = True

    @property
    def msf(self) -> float:
        qty = self.shipped_qty if self.shipped_qty is not None else self.qty_sheets
        return qty * self.sheet_width_in * self.sheet_length_in / 144 / 1000


@dataclass
class QualityTest:
    """Feed raw__quality_tests. A retest reuses the test_id with a later recorded_at."""

    test_id: str
    plant_code: str
    machine_code: str
    test_type: str
    grade_code: str | None
    wet_end_setup_id: str | None
    run_id: str | None
    order_line_id: str | None
    sampled_at: dt.datetime
    recorded_at: dt.datetime
    measured_value: float
    unit: str
    spec_min: float | None
    spec_max: float | None
    result: str
    comment: str | None
