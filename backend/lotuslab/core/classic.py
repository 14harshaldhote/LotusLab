"""The classic lotus puzzle: coverage doubles daily; full on day N, half on day N-1.

Kept as a reference model so the weather-driven simulation can be compared against
the textbook exponential intuition.
"""

from __future__ import annotations

import math


def coverage(day: int | float, initial: float, multiplier: float, capacity: float) -> float:
    """C_d = min(A, C_0 * r^d)."""
    if day < 0:
        raise ValueError("day must be >= 0")
    if initial >= capacity:
        return capacity
    # work in logs so very long horizons never overflow a float
    log_c = math.log(initial) + day * math.log(multiplier)
    return capacity if log_c >= math.log(capacity) else math.exp(log_c)


def days_to_fill(initial: float, multiplier: float, capacity: float) -> int:
    """Smallest integer day d with C_0 r^d >= A: ceil(ln(A/C0) / ln r)."""
    _check(initial, multiplier, capacity)
    if initial >= capacity:
        return 0
    exact = math.log(capacity / initial) / math.log(multiplier)
    d = math.ceil(exact - 1e-12)  # guard against 29.999999999 style float noise
    return d


def day_at_fraction(fraction: float, initial: float, multiplier: float, capacity: float) -> float:
    """Continuous day at which coverage first reaches ``fraction`` of the pond."""
    _check(initial, multiplier, capacity)
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    target = fraction * capacity
    if initial >= target:
        return 0.0
    return math.log(target / initial) / math.log(multiplier)


def series(initial: float, multiplier: float, capacity: float, days: int) -> list[float]:
    return [coverage(d, initial, multiplier, capacity) for d in range(days + 1)]


def _check(initial: float, multiplier: float, capacity: float) -> None:
    for name, v in (("initial", initial), ("multiplier", multiplier), ("capacity", capacity)):
        if not math.isfinite(v):
            raise ValueError(f"{name} must be finite")
    if initial <= 0 or capacity <= 0:
        raise ValueError("initial and capacity must be > 0")
    if multiplier <= 1:
        raise ValueError("multiplier must be > 1")
