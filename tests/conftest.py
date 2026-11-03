"""Shared fixtures: the seed-42 raw set, generated once per test session."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.generator import generate

SEED = 42


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The full raw set for seed 42 in a temporary directory (about 20 seconds)."""
    out = tmp_path_factory.mktemp("raw")
    generate(SEED, out)
    return out


@pytest.fixture(scope="session")
def manifest(raw_dir: Path) -> dict:
    return json.loads((raw_dir / "manifest.json").read_text())
