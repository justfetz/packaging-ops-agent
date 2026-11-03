"""The dbt sources match the raw feeds the generator writes.

`dbt/models/sources.yml` defines every raw feed once. On the DuckDB target,
dbt-duckdb replaces each source with the `external_location` expression in
its config, a read_csv or read_json call over the files in RAW_DIR. This test
renders those expressions the same way dbt and dbt-duckdb do (Jinja for
`env_var`, then str.format for `{identifier}`), reads every one with DuckDB,
and checks the row counts against the generator's manifest. If a feed is
added, renamed, or changes extension, this fails before `dbt build` does.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import duckdb
import jinja2
import pytest
import yaml

SOURCES_YML = Path(__file__).resolve().parents[1] / "dbt" / "models" / "sources.yml"


def _source_tables() -> list[dict]:
    sources = yaml.safe_load(SOURCES_YML.read_text())["sources"]
    assert [s["name"] for s in sources] == ["raw"]
    return sources[0]["tables"]


def _external_location(table: dict, raw_dir: Path) -> str:
    """Render the location as dbt (env_var) and dbt-duckdb (newstyle format) would."""
    template = jinja2.Template(table["config"]["external_location"])
    rendered = template.render(env_var=lambda _name, default=None: str(raw_dir))
    return rendered.format_map({"name": table["name"], "identifier": table["identifier"]})


def _manifest_rows_by_feed(manifest: dict) -> Counter[str]:
    rows: Counter[str] = Counter()
    for name, info in manifest["files"].items():
        if name.startswith(("raw__", "ref__")):
            feed = name.split("__")[1].removesuffix(".csv").removesuffix(".jsonl")
            rows[f"{name.split('__')[0]}__{feed}"] += info["rows"]
    return rows


def test_every_feed_has_a_source_and_nothing_else(manifest: dict) -> None:
    feeds = set(_manifest_rows_by_feed(manifest))
    identifiers = {t["identifier"] for t in _source_tables()}
    assert identifiers == feeds


@pytest.mark.parametrize("table", _source_tables(), ids=lambda t: t["name"])
def test_duckdb_reads_every_row_of_the_feed(table: dict, raw_dir: Path, manifest: dict) -> None:
    location = _external_location(table, raw_dir)
    assert str(raw_dir) in location
    [(count,)] = duckdb.sql(f"select count(*) from {location}").fetchall()
    assert count == _manifest_rows_by_feed(manifest)[table["identifier"]]
