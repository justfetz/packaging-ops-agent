"""Tests for the synthetic data generator.

The full set is generated once per test session into a temporary directory
(about 20 seconds). Every planted fact is recomputed from the written files,
the checksum pins the bytes for seed 42, and the messiness rules are checked
to be present at their configured rates.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import pytest

from data.generator import generate
from data.generator.config import load_config, load_facts
from data.generator.facts import CauseNormaliser, compare_facts, measure_facts

SEED = 42
# Same seed, same bytes. Any change to the generator or its config changes this
# value; update it from `make generate` and say why in the PR.
EXPECTED_CHECKSUM = "7ca613b708c65e4cd7206d6418768e1efea0addae68f158d73ba91e3324f0ec0"
MAX_BYTES = 50_000_000


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("raw")
    generate(SEED, out)
    return out


@pytest.fixture(scope="session")
def manifest(raw_dir: Path) -> dict:
    return json.loads((raw_dir / "manifest.json").read_text())


@pytest.fixture(scope="session")
def measured(raw_dir: Path) -> dict[str, dict]:
    return measure_facts(load_config(), raw_dir)


def _csv_rows(raw_dir: Path, feed: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(raw_dir.glob(f"{feed}__*.csv")):
        with path.open(newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def _jsonl_rows(raw_dir: Path, feed: str) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(raw_dir.glob(f"{feed}__*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text().splitlines())
    return rows


# ----------------------------------------------------------------------------


def test_checksum_is_stable_for_seed_42(manifest: dict) -> None:
    assert manifest["seed"] == SEED
    assert manifest["checksum"] == EXPECTED_CHECKSUM


def test_raw_set_is_small(manifest: dict) -> None:
    assert manifest["total_bytes"] < MAX_BYTES
    assert 100_000 < manifest["total_rows"] < 1_000_000


def test_layout_is_flat_with_month_in_filename(raw_dir: Path) -> None:
    names = sorted(p.name for p in raw_dir.iterdir())
    assert all("/" not in n for n in names)
    assert "raw__production_runs__2025-07.csv" in names
    assert "raw__stop_events__2026-01.jsonl" in names
    assert "ref__board_grades.csv" in names
    assert not any(p.is_dir() for p in raw_dir.iterdir())


@pytest.mark.parametrize("fact_id", [f"PF-{n:02d}" for n in range(1, 21)])
def test_planted_fact(fact_id: str, measured: dict[str, dict]) -> None:
    facts = load_facts()
    rows = compare_facts(facts, measured)[fact_id]
    failures = [(name, expected, got) for name, expected, got, ok in rows if not ok]
    assert not failures, f"{facts[fact_id].fact}\n{failures}"


def test_same_seed_same_bytes(raw_dir: Path, manifest: dict, tmp_path: Path) -> None:
    """A second run with the same seed writes byte-identical files; another seed does not.

    The planted facts need the full two-year period (1,840 stacker jams do not
    fit in a short window), so this runs the real generator again. About 20s.
    """
    again = generate(SEED, tmp_path / "again")
    assert again["checksum"] == manifest["checksum"]
    assert again["files"] == manifest["files"]
    for name in manifest["files"]:
        assert (tmp_path / "again" / name).read_bytes() == (raw_dir / name).read_bytes()


# ----------------------------------------------------------------------------
# Messiness, one check per item in docs/domain-spec.md section 11


def test_cause_codes_drift_and_other_is_resolvable(raw_dir: Path) -> None:
    cfg = load_config()
    events = _jsonl_rows(raw_dir, "raw__stop_events")
    spellings = Counter(e["cause_code"] for e in events)
    assert spellings["Other"] / len(events) == pytest.approx(0.08, abs=0.01)
    assert spellings["mis-splice"] + spellings["splice miss"] + spellings["SPLICE"] > 0
    assert spellings[None] > 0, "some events carry a fault code and no operator cause"
    normaliser = CauseNormaliser(cfg)
    canonical = Counter(normaliser.resolve(e) for e in events)  # raises if unrecoverable
    assert set(canonical) <= {c.code for c in cfg.causes}
    assert all(e["cause_code"] or e["fault_code"] for e in events)


def test_shift_summaries_are_resent(raw_dir: Path) -> None:
    rows = _jsonl_rows(raw_dir, "raw__shift_summaries")
    keys = Counter((r["machine_code"], r["shift_date"], r["shift_no"]) for r in rows)
    dup_share = sum(1 for k, n in keys.items() if n > 1) / len(keys)
    assert 0.03 <= dup_share <= 0.05


def test_quality_retests_share_the_test_id(raw_dir: Path) -> None:
    rows = _csv_rows(raw_dir, "raw__quality_tests")
    by_id = Counter(r["test_id"] for r in rows)
    retested = sum(1 for n in by_id.values() if n > 1)
    assert retested / len(by_id) == pytest.approx(0.04, abs=0.01)


def test_la_starch_switches_from_kilograms_to_pounds(raw_dir: Path) -> None:
    runs = [r for r in _csv_rows(raw_dir, "raw__production_runs") if r["plant_code"] == "LA"]
    before = [r for r in runs if r["run_start"] < "2025-10-01" and r["grade_code"] == "32ECT-C"]
    after = [r for r in runs if r["run_start"] >= "2025-10-01" and r["grade_code"] == "32ECT-C"]

    def rate(group: list[dict[str, str]]) -> float:
        return sum(float(r["starch_qty"]) for r in group) / sum(
            int(r["sqft_produced"]) for r in group
        )

    assert rate(before) == pytest.approx(rate(after) * 0.4536, rel=0.08)


def test_some_runs_end_before_they_start(raw_dir: Path) -> None:
    runs = _csv_rows(raw_dir, "raw__production_runs")
    broken = [r for r in runs if r["run_end"] < r["run_start"]]
    assert len(broken) == load_config().messiness["clock_reset_runs"]
    assert {r["plant_code"] for r in broken} <= {"ATL", "PA"}


def test_order_lines_are_edited_after_download(raw_dir: Path) -> None:
    rows = _csv_rows(raw_dir, "raw__order_lines")
    by_id = Counter(r["order_line_id"] for r in rows)
    edited = sum(1 for n in by_id.values() if n > 1)
    assert edited / len(by_id) == pytest.approx(0.03, abs=0.01)
    versions = [r for r in rows if by_id[r["order_line_id"]] > 1]
    assert {r["line_version"] for r in versions} == {"1", "2"}


def test_roll_width_disagrees_between_feeds(raw_dir: Path) -> None:
    runs = {
        r["order_line_id"]: r["roll_width_in"] for r in _csv_rows(raw_dir, "raw__production_runs")
    }
    lines = _csv_rows(raw_dir, "raw__order_lines")
    disagree = sum(
        1 for x in lines if runs.get(x["order_line_id"]) not in (None, x["roll_width_in"])
    )
    assert disagree / len(lines) == pytest.approx(0.01, abs=0.005)


def test_unaccounted_time_per_shift(raw_dir: Path) -> None:
    """Item 9: micro-stops are not logged, so shifts carry some unaccounted time.

    Unaccounted = scheduled minutes - run wall time (running plus the stops
    inside runs) - stops between runs. The generator spreads feet so this
    averages about 50 minutes at Atlanta, PA, and LA. Chicago is higher by
    construction: PF-11 pins its speeds and PF-07/PF-08 pin its feet, so 16
    short setups of 9,200 feet cannot fill a shift. The odd shift runs over,
    as the one holding the 212-minute boiler stop does.
    """
    runs = _csv_rows(raw_dir, "raw__production_runs")
    stops = _jsonl_rows(raw_dir, "raw__stop_events")
    summaries = _jsonl_rows(raw_dir, "raw__shift_summaries")
    windows: dict[str, list[tuple[dt.datetime, dt.datetime]]] = {}
    wall: Counter[tuple[str, str, int]] = Counter()
    for r in runs:
        start = dt.datetime.fromisoformat(r["run_start"])
        end = dt.datetime.fromisoformat(r["run_end"])
        if end > start:
            wall[(r["machine_code"], r["shift_date"], int(r["shift_no"]))] += (
                end - start
            ).total_seconds() / 60
            windows.setdefault(r["machine_code"], []).append((start, end))
    between: Counter[tuple[str, str, int]] = Counter()
    shifts = {
        (s["machine_code"], s["shift_date"], s["shift_no"]): (
            dt.datetime.fromisoformat(s["shift_start"]),
            dt.datetime.fromisoformat(s["shift_end"]),
        )
        for s in summaries
    }
    for e in stops:
        start = dt.datetime.fromisoformat(e["start_time"])
        if any(a <= start < b for a, b in windows[e["machine_code"]]):
            continue
        for key, (s0, s1) in shifts.items():
            if key[0] == e["machine_code"] and s0 <= start < s1:
                between[key] += e["duration_seconds"] / 60
                break
    by_plant: dict[str, list[float]] = {}
    for key, (s0, s1) in shifts.items():
        scheduled = (s1 - s0).total_seconds() / 60
        by_plant.setdefault(key[0].split("-")[0], []).append(scheduled - wall[key] - between[key])
    means = {p: sum(v) / len(v) for p, v in by_plant.items()}
    assert means["ATL"] < 60 and means["PA"] < 60 and means["LA"] < 60, means
    assert means["CHI"] < 150, means
    for plant, values in by_plant.items():
        assert sum(1 for v in values if v < 0) / len(values) < 0.2, plant
