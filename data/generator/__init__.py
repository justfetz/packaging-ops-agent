"""Seeded synthetic data generator for Ironwood Container.

`generate(seed, out_dir)` runs the whole pipeline and writes the raw feeds.
Each stage gets its own `random.Random` seeded from the run seed and the stage
name, so a change inside one stage does not reshuffle the others. Downtime is
sized and given a shift before the feet are spread, so a shift's production
fits around its stops; the stops are attached to runs afterwards. Same seed,
same bytes.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from . import mess
from .config import DEFAULT_CONFIG, DEFAULT_FACTS, load_config, load_facts
from .downtime import attach_stops, build_downtime, stop_seconds_by_shift
from .orders import build_orders
from .production import build_runs, build_wet_end_runs
from .quality import build_quality
from .shifts import build_shifts
from .timeline import lay_out
from .writers import write_all

__version__ = "0.1.0"


def generate(
    seed: int,
    out_dir: Path,
    config_path: Path = DEFAULT_CONFIG,
    facts_path: Path = DEFAULT_FACTS,
) -> dict[str, Any]:
    cfg = load_config(config_path)
    facts = load_facts(facts_path)

    def rng(stage: str) -> random.Random:
        return random.Random(f"{seed}:{stage}")

    shifts = build_shifts(cfg, rng("shifts"))
    production_rng, downtime_rng = rng("production"), rng("downtime")
    wet_runs = build_wet_end_runs(cfg, facts, shifts, production_rng)
    events = build_downtime(cfg, facts, shifts, wet_runs, downtime_rng)
    runs = build_runs(cfg, facts, wet_runs, stop_seconds_by_shift(events), production_rng)
    attach_stops(cfg, events, runs, downtime_rng)
    summaries = lay_out(cfg, facts, shifts, wet_runs, events, rng("timeline"))

    runs.sort(key=lambda r: (r.run_start, r.machine_code, r.wet_end_setup_id, r.seq_in_setup))
    for n, r in enumerate(runs, start=1):
        r.run_id = f"RUN-{n:06d}"
    events.sort(key=lambda e: (e.start_time, e.machine_code, e.duration_seconds, e.true_cause))
    for n, e in enumerate(events, start=1):
        e.event_id = f"STP-{n:06d}"
    summaries.sort(key=lambda s: (s.shift_start, s.machine_code))
    for n, s in enumerate(summaries, start=1):
        s.summary_id = f"SS-{n:06d}"

    lines = build_orders(cfg, facts, runs, rng("orders"))
    tests = build_quality(cfg, facts, wet_runs, runs, lines, rng("quality"))

    messy = rng("mess")
    mess.resend_shift_summaries(cfg, summaries, messy)
    mess.add_retests(cfg, tests, messy)
    mess.la_starch_in_kilograms(cfg, runs)
    mess.clock_reset_runs(cfg, runs, messy)
    mess.edit_order_lines(cfg, lines, messy)
    mess.disagree_roll_width(cfg, lines, messy)

    return write_all(cfg, out_dir, seed, runs, events, summaries, lines, tests)
