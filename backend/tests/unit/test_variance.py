"""Variance against the benchmark run (spec B8, B9, B9b, A4). Quantities in base units."""

from decimal import Decimal

import pytest

from app.core.variance import planned_qty, variance

D = Decimal


@pytest.mark.parametrize(
    ("name", "planned", "actual", "bp", "flagged"),
    [
        ("B8 yield", D(200), D(188), -600, True),
        ("B9 oil", D(10000), D(10500), 500, True),
        ("B9b pouches at exactly -3.00%", D(200), D(194), -300, False),
        ("A4 cartons", D(10), D(9), -1000, True),
        ("flour on standard", D(40000), D(40000), 0, False),
        ("spice on standard", D(1200), D(1200), 0, False),
    ],
)
def test_benchmark_variances(name: str, planned, actual, bp: int, flagged: bool) -> None:
    v = variance(planned, actual)
    assert (v.variance_bp, v.flagged) == (bp, flagged), name


def test_flag_uses_exact_value_not_rounded_bp() -> None:
    v = variance(D(100000), D(103004))  # +3.004%: rounds to 300 bp but is over 3%
    assert v.variance_bp == 300
    assert v.flagged is True


def test_tolerance_is_per_item() -> None:
    assert variance(D(200), D(188), tolerance_bp=700).flagged is False


def test_planned_qty_scales_with_batches() -> None:
    assert planned_qty(D(40000), D(1)) == 40000
    assert planned_qty(D(40000), D("1.5")) == 60000


def test_zero_planned_is_an_error() -> None:
    with pytest.raises(ValueError):
        variance(D(0), D(5))
