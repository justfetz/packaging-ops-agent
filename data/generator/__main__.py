"""CLI: `uv run python -m data.generator generate --seed 42 --out ./data/raw`.

`check` recomputes every planted fact from the files in --out and prints the
measured value next to the expected one. Both are what `make generate` and
`make check-facts` call.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import generate
from .config import DEFAULT_CONFIG, DEFAULT_FACTS, load_config, load_facts
from .facts import compare_facts, measure_facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m data.generator", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="write the raw feeds")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--out", type=Path, default=Path("data/raw"))
    gen.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    gen.add_argument("--facts", type=Path, default=DEFAULT_FACTS)

    chk = sub.add_parser("check", help="recompute the planted facts from generated files")
    chk.add_argument("--out", type=Path, default=Path("data/raw"))
    chk.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    chk.add_argument("--facts", type=Path, default=DEFAULT_FACTS)

    args = parser.parse_args(argv)
    if args.command == "generate":
        started = time.perf_counter()
        manifest = generate(args.seed, args.out, args.config, args.facts)
        elapsed = time.perf_counter() - started
        print(
            f"wrote {len(manifest['files'])} files, {manifest['total_rows']:,} rows, "
            f"{manifest['total_bytes'] / 1e6:.1f} MB to {args.out} in {elapsed:.1f}s"
        )
        print(f"checksum {manifest['checksum']}")
        return 0

    cfg = load_config(args.config)
    facts = load_facts(args.facts)
    measured = measure_facts(cfg, args.out)
    failures = 0
    for fact_id, rows in compare_facts(facts, measured).items():
        for name, expected, got, ok in rows:
            failures += 0 if ok else 1
            mark = "ok  " if ok else "FAIL"
            print(f"{mark} {fact_id} {name:<34} expected {expected!s:<12} got {got}")
    print(f"{failures} failing measures" if failures else "all planted facts hold")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
