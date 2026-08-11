"""Exact numeric primitives for deterministic answer operators.

All source monetary values are integer rupees.  Intermediate averages and
percentages therefore use rational/decimal arithmetic and apply one explicit
rounding policy at the output boundary.  This avoids binary-float drift and
Python's implicit ties-to-even behavior.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Iterable, Literal


DifferenceMode = Literal["absolute", "left_minus_right", "right_minus_left"]


def round_fraction(value: Fraction) -> int:
    """Round a rational to the nearest integer, with halves away from zero."""
    decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rounded_average(values: Iterable[int]) -> int:
    items = [int(value) for value in values]
    if not items:
        return 0
    return round_fraction(Fraction(sum(items), len(items)))


def percentage(numerator: int, denominator: int, places: int = 2) -> float:
    """Return an exact 0..100 percentage rounded half-up at the boundary."""
    if denominator <= 0:
        return 0.0
    quantum = Decimal(1).scaleb(-places)
    value = (Decimal(int(numerator)) * Decimal(100)) / Decimal(int(denominator))
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))


def difference(left: Fraction, right: Fraction, mode: DifferenceMode) -> Fraction:
    if mode == "left_minus_right":
        return left - right
    if mode == "right_minus_left":
        return right - left
    return abs(left - right)


def mean_median_gap(values: Iterable[int], mode: DifferenceMode = "absolute") -> int:
    """Compute an exact mean/median comparison with explicit direction."""
    items = sorted(int(value) for value in values)
    if not items:
        return 0
    count = len(items)
    mean = Fraction(sum(items), count)
    if count % 2:
        median = Fraction(items[count // 2], 1)
    else:
        median = Fraction(items[count // 2 - 1] + items[count // 2], 2)
    return round_fraction(difference(mean, median, mode))
