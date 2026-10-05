import math

import pytest

from lotuslab.core import classic


def test_day_29_puzzle():
    # full on day 30 with daily doubling -> start at 2^-30 of the pond
    initial = 2.0**-30
    assert classic.days_to_fill(initial, 2.0, 1.0) == 30
    assert classic.day_at_fraction(0.5, initial, 2.0, 1.0) == pytest.approx(29.0)
    assert classic.coverage(29, initial, 2.0, 1.0) == pytest.approx(0.5)


def test_coverage_never_exceeds_capacity_and_is_monotonic():
    s = classic.series(1.0, 1.7, 1000.0, 60)
    assert max(s) == 1000.0
    assert all(b >= a for a, b in zip(s, s[1:]))


def test_initially_full_pond():
    assert classic.days_to_fill(5.0, 2.0, 5.0) == 0
    assert classic.coverage(0, 6.0, 2.0, 5.0) == 5.0


def test_huge_horizon_does_not_overflow():
    assert classic.coverage(10_000, 1e-9, 3.0, 1.0) == 1.0


@pytest.mark.parametrize("args", [(0, 2, 1), (1, 1, 2), (1, 2, -1), (math.nan, 2, 1), (1, math.inf, 1)])
def test_rejects_invalid(args):
    with pytest.raises(ValueError):
        classic.days_to_fill(*args)
