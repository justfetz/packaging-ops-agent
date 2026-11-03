"""Write the feeds as flat files with the month in the name, plus a manifest.

Layout is flat on purpose: the session proxy cannot read an object under a
"folder" back by name (CLAUDE.md), so `raw__production_runs__2025-07.csv`
rather than `raw/production_runs/2025-07.csv`. Files are partitioned by the
arrival timestamp of the record, which is how late-arriving records land in a
later month's file.

Everything written here is deterministic: fixed column order, fixed number
formatting, newline-only line endings, and a manifest with no timestamps.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config
from .model import OrderLine, QualityTest, Run, ShiftSummary, StopEvent
from .orders import standard_cost_rows

RUN_COLUMNS = [
    "run_id",
    "wet_end_setup_id",
    "machine_code",
    "plant_code",
    "order_line_id",
    "grade_code",
    "roll_width_in",
    "knife_position",
    "cutoff_in",
    "sheet_width_in",
    "outs",
    "scheduled_lineal_ft",
    "scheduled_cuts",
    "actual_lineal_ft",
    "actual_cuts",
    "sqft_produced",
    "trim_sqft",
    "shear_waste_sqft",
    "starch_qty",
    "run_start",
    "run_end",
    "shift_date",
    "shift_no",
    "stops_count",
    "downtime_seconds",
    "new_wet_end_setup",
    "width_reset",
    "setup_minutes",
]
STOP_COLUMNS = [
    "event_id",
    "machine_code",
    "start_time",
    "end_time",
    "duration_seconds",
    "machine_section",
    "fault_code",
    "cause_code",
    "comment",
]
SUMMARY_COLUMNS = [
    "summary_id",
    "machine_code",
    "shift_date",
    "shift_no",
    "shift_start",
    "shift_end",
    "scheduled_minutes",
    "crew_lead_id",
    "crew_lead_name",
    "run_count",
    "total_lineal_ft",
    "total_sqft_produced",
    "total_trim_sqft",
    "total_shear_waste_sqft",
    "total_cuts",
    "stops_count",
    "downtime_seconds",
    "emitted_at",
]
LINE_COLUMNS = [
    "order_id",
    "order_line_id",
    "line_version",
    "customer_id",
    "plant_code",
    "order_date",
    "requested_ship_date",
    "grade_code",
    "qty_sheets",
    "sheet_width_in",
    "sheet_length_in",
    "score_pattern",
    "unitizing",
    "unit_count",
    "roll_width_in",
    "price_per_msf",
    "std_cost_per_msf",
    "shipped_date",
    "shipped_qty",
    "scheduling_notes",
    "updated_at",
]
TEST_COLUMNS = [
    "test_id",
    "plant_code",
    "machine_code",
    "test_type",
    "grade_code",
    "run_id",
    "order_line_id",
    "sampled_at",
    "recorded_at",
    "measured_value",
    "spec_min",
    "spec_max",
    "result",
    "comment",
]
DECIMALS = {
    "cutoff_in": 2,
    "sheet_width_in": 3,
    "sheet_length_in": 2,
    "starch_qty": 1,
    "setup_minutes": 1,
    "price_per_msf": 2,
    "std_cost_per_msf": 2,
    "cost_per_msf": 2,
    "measured_value": 3,
    "spec_min": 3,
    "spec_max": 3,
}


@dataclass
class Written:
    name: str
    rows: int
    size: int
    sha256: str


def fmt(column: str, value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float):
        text = f"{value:.{DECIMALS.get(column, 3)}f}"
        if "." in text:  # drop trailing zeros but keep one decimal, so 6.000 is 6.0
            text = text.rstrip("0")
            text = text + "0" if text.endswith(".") else text
        return text
    return value


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> Written:
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([fmt(c, row.get(c)) for c in columns])
            count += 1
    return _written(path, count)


def write_jsonl(path: Path, columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> Written:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            record = {c: _json_value(c, row.get(c)) for c in columns}
            handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=True))
            handle.write("\n")
            count += 1
    return _written(path, count)


def _json_value(column: str, value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return round(value, DECIMALS.get(column, 3))
    return fmt(column, value)


def _written(path: Path, rows: int) -> Written:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return Written(path.name, rows, path.stat().st_size, digest)


def _by_month(rows: list[dict[str, Any]], column: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        stamp = row[column]
        out[f"{stamp.year:04d}-{stamp.month:02d}"].append(row)
    return out


def _records(items: Iterable[Any], columns: Sequence[str]) -> list[dict[str, Any]]:
    return [{c: getattr(item, c) for c in columns} for item in items]


def write_all(
    cfg: Config,
    out_dir: Path,
    seed: int,
    runs: list[Run],
    events: list[StopEvent],
    summaries: list[ShiftSummary],
    lines: list[OrderLine],
    tests: list[QualityTest],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("raw__*"):
        stale.unlink()
    for stale in out_dir.glob("ref__*"):
        stale.unlink()
    written: list[Written] = []

    feeds: list[tuple[str, str, Sequence[str], list[dict[str, Any]], str, Any]] = [
        (
            "production_runs",
            "run_start",
            RUN_COLUMNS,
            _records(runs, RUN_COLUMNS),
            "csv",
            write_csv,
        ),
        (
            "stop_events",
            "start_time",
            STOP_COLUMNS,
            _records(events, STOP_COLUMNS),
            "jsonl",
            write_jsonl,
        ),
        (
            "shift_summaries",
            "emitted_at",
            SUMMARY_COLUMNS,
            _records(summaries, SUMMARY_COLUMNS),
            "jsonl",
            write_jsonl,
        ),
        (
            "order_lines",
            "updated_at",
            LINE_COLUMNS,
            _records(lines, LINE_COLUMNS),
            "csv",
            write_csv,
        ),
        (
            "quality_tests",
            "recorded_at",
            TEST_COLUMNS,
            _records(tests, TEST_COLUMNS),
            "csv",
            write_csv,
        ),
    ]
    for feed, stamp, columns, rows, ext, writer in feeds:
        rows.sort(key=lambda r: (r[stamp], r[columns[0]]))
        for month, month_rows in sorted(_by_month(rows, stamp).items()):
            written.append(writer(out_dir / f"raw__{feed}__{month}.{ext}", columns, month_rows))

    written.extend(write_reference(cfg, out_dir))

    manifest = {
        "seed": seed,
        "company": cfg.company_name,
        "period": [cfg.period_start.isoformat(), cfg.period_end.isoformat()],
        "files": {
            w.name: {"rows": w.rows, "bytes": w.size, "sha256": w.sha256}
            for w in sorted(written, key=lambda w: w.name)
        },
    }
    combined = hashlib.sha256()
    for name, info in manifest["files"].items():
        combined.update(f"{name}:{info['sha256']}\n".encode())
    manifest["checksum"] = combined.hexdigest()
    manifest["total_bytes"] = sum(w.size for w in written)
    manifest["total_rows"] = sum(w.rows for w in written)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def write_reference(cfg: Config, out_dir: Path) -> list[Written]:
    out = []
    out.append(
        write_csv(
            out_dir / "ref__plants.csv",
            [
                "plant_code",
                "plant_name",
                "city",
                "state",
                "timezone",
                "commissioned_year",
                "data_start",
                "market",
                "character",
            ],
            [
                {
                    "plant_code": p.code,
                    "plant_name": p.name,
                    "city": p.city,
                    "state": p.state,
                    "timezone": p.timezone,
                    "commissioned_year": p.commissioned_year,
                    "data_start": p.data_start,
                    "market": p.market,
                    "character": p.character,
                }
                for p in cfg.plants
            ],
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__machines.csv",
            [
                "machine_code",
                "plant_code",
                "width_in",
                "commissioned_year",
                "nominal_speed_fpm",
                "capability",
                "known_weak_spot",
            ],
            [
                {
                    "machine_code": m.code,
                    "plant_code": m.plant,
                    "width_in": m.width_in,
                    "commissioned_year": m.commissioned_year,
                    "nominal_speed_fpm": m.nominal_speed_fpm,
                    "capability": m.capability,
                    "known_weak_spot": m.weak_spot,
                }
                for m in cfg.machines
            ],
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__customers.csv",
            [
                "customer_id",
                "customer_name",
                "segment",
                "home_plant",
                "contract_type",
                "price_escalator",
            ],
            [
                {
                    "customer_id": c.id,
                    "customer_name": c.name,
                    "segment": c.segment,
                    "home_plant": c.home_plant,
                    "contract_type": c.contract,
                    "price_escalator": c.escalator,
                }
                for c in cfg.customers
            ],
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__board_grades.csv",
            [
                "grade_code",
                "flute",
                "recipe_lb",
                "test_basis",
                "test_target",
                "caliper_in",
                "list_price_per_msf",
                "runs_mainly_at",
                "notes",
            ],
            [
                {
                    "grade_code": g.code,
                    "flute": g.flute,
                    "recipe_lb": g.recipe,
                    "test_basis": g.test_basis,
                    "test_target": g.test_target,
                    "caliper_in": g.caliper_in,
                    "list_price_per_msf": g.price_per_msf,
                    "runs_mainly_at": g.runs_mainly_at,
                    "notes": g.notes,
                }
                for g in cfg.grades
            ],
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__standard_cost.csv",
            ["grade_code", "month", "cost_per_msf"],
            standard_cost_rows(cfg),
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__downtime_causes.csv",
            [
                "cause_code",
                "category",
                "planned",
                "typical_min_minutes",
                "typical_max_minutes",
                "machine_section",
            ],
            [
                {
                    "cause_code": c.code,
                    "category": c.category,
                    "planned": c.planned,
                    "typical_min_minutes": c.minutes[0],
                    "typical_max_minutes": c.minutes[1],
                    "machine_section": c.section,
                }
                for c in cfg.causes
            ],
        )
    )
    out.append(
        write_csv(
            out_dir / "ref__fault_codes.csv",
            ["fault_code", "machine_section", "description", "cause_code"],
            [
                {
                    "fault_code": f.code,
                    "machine_section": f.section,
                    "description": f.description,
                    "cause_code": f.cause,
                }
                for f in cfg.fault_codes
            ],
        )
    )
    return out
