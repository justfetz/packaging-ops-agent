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
EXPECTED_CHECKSUM = "64dcfbee944864d6cd1353fc8604c509bd9e0cce4c3c9acc10a9845a73b5b392"
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


@pytest.mark.parametrize("fact_id", [f"PF-{n:02d}" for n in range(1, 22)])
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


def test_wet_end_change_time_is_explicit(raw_dir: Path) -> None:
    """Spec section 5: a wet-end change takes 5 to 10 minutes at crawl speed.

    `setup_minutes` sits on the first run of every setup and is 0 on the runs
    that follow. The plant mean per change is between 5 and 10 minutes, with
    Chicago highest, and no change is quicker than the configured floor.
    """
    cfg = load_config()
    runs = _csv_rows(raw_dir, "raw__production_runs")
    per_change: dict[str, list[float]] = {}
    for r in runs:
        minutes = float(r["setup_minutes"])
        if r["new_wet_end_setup"] == "true":
            per_change.setdefault(r["plant_code"], []).append(minutes)
        else:
            assert minutes == 0.0, r["run_id"]
    floor = cfg.wet_end_changes["floor_minutes"][0]
    means = {p: sum(v) / len(v) for p, v in per_change.items()}
    assert set(means) == {"ATL", "CHI", "PA", "LA"}
    for plant, values in per_change.items():
        assert 5.0 <= means[plant] <= 10.0, means
        assert min(values) >= floor, plant
    assert max(means, key=lambda p: means[p]) == "CHI", means


def test_shift_time_reconciles_once_changes_are_counted(raw_dir: Path) -> None:
    """Item 9: what is left after runs, stops, and change time is minutes, not an hour.

    Unaccounted = scheduled - run wall time (running plus the stops inside
    runs) - stops between runs - setup_minutes. The timeline hands a shift's
    idle time to its changes, so the mean is near zero at every plant. A shift
    that holds more stops than its feet were balanced for runs late; the next
    shift starts late and absorbs it. Those are a few percent of shifts.
    """
    runs = _csv_rows(raw_dir, "raw__production_runs")
    stops = _jsonl_rows(raw_dir, "raw__stop_events")
    summaries = _jsonl_rows(raw_dir, "raw__shift_summaries")
    windows: dict[str, list[tuple[dt.datetime, dt.datetime]]] = {}
    wall: Counter[tuple[str, str, int]] = Counter()
    setup: Counter[tuple[str, str, int]] = Counter()
    for r in runs:
        key = (r["machine_code"], r["shift_date"], int(r["shift_no"]))
        start = dt.datetime.fromisoformat(r["run_start"])
        end = dt.datetime.fromisoformat(r["run_end"])
        setup[key] += float(r["setup_minutes"])
        if end > start:
            wall[key] += (end - start).total_seconds() / 60
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
        left = scheduled - wall[key] - between[key] - setup[key]
        by_plant.setdefault(key[0].split("-")[0], []).append(left)
    means = {p: sum(v) / len(v) for p, v in by_plant.items()}
    assert all(-1.0 < m < 5.0 for m in means.values()), means
    late = {p: sum(1 for v in values if v < -1.0) / len(values) for p, values in by_plant.items()}
    assert all(share < 0.1 for share in late.values()), late
