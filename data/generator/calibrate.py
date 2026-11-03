"""Numeric helpers that make a random draw hit an exact target.

The generator draws plausible values first and then nudges a group so its
total, mean, count, or ratio equals the planted value. Each helper is pure and
deterministic given its inputs; randomness, where needed, comes from the
caller's `random.Random`.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def scale_to_sum(values: Sequence[float], target: int, minimum: int = 1) -> list[int]:
    """Scale positive values so the integer results sum exactly to target.

    Proportional scaling, floor to int, then hand out the remainder one unit at
    a time to the largest fractional parts. Every result is at least `minimum`.
    """
    if not values:
        return []
    total = float(sum(values))
    if total <= 0:
        base = [target // len(values)] * len(values)
        for i in range(target - sum(base)):
            base[i] += 1
        return base
    scaled = [max(minimum, v * target / total) for v in values]
    floors = [int(s) for s in scaled]
    remainder = target - sum(floors)
    order = sorted(range(len(values)), key=lambda i: (floors[i] - scaled[i], i))
    step = 1 if remainder > 0 else -1
    idx = 0
    while remainder != 0:
        i = order[idx % len(order)]
        if step < 0 and floors[i] <= minimum:
            idx += 1
            continue
        floors[i] += step
        remainder -= step
        idx += 1
    return floors


def distribute_count(
    rng: random.Random,
    buckets: int,
    total: int,
    low: int | Sequence[int],
    high: int | Sequence[int],
    weights: Sequence[float] | None = None,
) -> list[int]:
    """Spread `total` items across buckets, each within its [low, high] bounds.

    Starts from a weighted proportional split and then moves single units at
    random until the sum is exact, so the per-bucket spread looks natural while
    the total is exact. Raises if the bounds make the total impossible.
    """
    if buckets == 0:
        return []
    lows = list(low) if isinstance(low, Sequence) else [low] * buckets
    highs = list(high) if isinstance(high, Sequence) else [high] * buckets
    if not sum(lows) <= total <= sum(highs):
        raise ValueError(f"cannot place {total} items in {buckets} buckets within the bounds")
    w = list(weights) if weights is not None else [1.0] * buckets
    wsum = sum(w) or 1.0
    counts = [min(highs[i], max(lows[i], round(total * w[i] / wsum))) for i in range(buckets)]
    diff = total - sum(counts)
    guard = 0
    while diff != 0:
        i = rng.randrange(buckets)
        if diff > 0 and counts[i] < highs[i]:
            counts[i] += 1
            diff -= 1
        elif diff < 0 and counts[i] > lows[i]:
            counts[i] -= 1
            diff += 1
        guard += 1
        if guard > 200 * buckets + 10000:
            raise RuntimeError("distribute_count did not converge")
    return counts


def exact_count_flags(rng: random.Random, n: int, rate_pct: float) -> list[bool]:
    """Return n flags with exactly round(n * rate) True, in random positions."""
    k = min(n, max(0, round(n * rate_pct / 100.0)))
    flags = [True] * k + [False] * (n - k)
    rng.shuffle(flags)
    return flags


def set_ratio_by_scaling[T](
    items: Sequence[T],
    numer: Callable[[T], float],
    denom_fixed: Callable[[T], float],
    setter: Callable[[T, float], None],
    target_ratio: float,
) -> None:
    """Scale the numerator parts so sum(numer) / (sum(numer) + sum(fixed)) == target.

    Used for waste: waste / (good + waste). The fixed part (good sqft) stays;
    the waste parts are scaled proportionally and rounded, with the rounding
    residual absorbed by the largest item.
    """
    if not items:
        return
    fixed = sum(denom_fixed(it) for it in items)
    current = sum(numer(it) for it in items)
    if current <= 0 or fixed <= 0:
        return
    want = target_ratio / (1.0 - target_ratio) * fixed
    factor = want / current
    new_values = [numer(it) * factor for it in items]
    rounded = [round(v) for v in new_values]
    residual = round(want) - sum(rounded)
    largest = max(range(len(items)), key=lambda i: rounded[i])
    rounded[largest] += residual
    for it, v in zip(items, rounded, strict=True):
        setter(it, max(0, v))


def scale_group_mean(values: Sequence[float], target_mean: float) -> list[float]:
    """Scale values so their mean is exactly target_mean (floats, no rounding)."""
    if not values:
        return []
    current = sum(values) / len(values)
    if current == 0:
        return [target_mean] * len(values)
    factor = target_mean / current
    return [v * factor for v in values]
