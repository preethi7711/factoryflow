from decimal import Decimal

import pytest

from app.core.money import apply_bp, format_inr, round_half_up, to_paise


@pytest.mark.parametrize(
    ("x", "expected"),
    [("2.5", 3), ("-2.5", -3), ("2.4999", 2), ("0.5", 1), ("31.1436", 31), ("18750", 18750)],
)
def test_round_half_up(x: str, expected: int) -> None:
    assert round_half_up(Decimal(x)) == expected


def test_round_half_up_refuses_float() -> None:
    with pytest.raises(TypeError):
        round_half_up(2.5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("rupees", "paise"), [("45", 4500), ("45.5", 4550), ("2.50", 250), (7, 700)]
)
def test_to_paise(rupees, paise: int) -> None:
    assert to_paise(rupees) == paise


def test_to_paise_rejects_fractions_of_a_paisa_and_floats() -> None:
    with pytest.raises(ValueError):
        to_paise("7.555")
    with pytest.raises(TypeError):
        to_paise(7.5)  # type: ignore[arg-type]


def test_apply_bp_half_rate_on_benchmark_invoice() -> None:
    assert apply_bp(750000, 250) == 18750  # B10: 2.5% of Rs 7,500


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (787500, "₹7,875.00"),
        (387500, "₹3,875.00"),
        (5, "₹0.05"),
        (12345678, "₹1,23,456.78"),
        (1000000000, "₹1,00,00,000.00"),
        (-387500, "-₹3,875.00"),
    ],
)
def test_format_inr_uses_indian_grouping(paise: int, text: str) -> None:
    assert format_inr(paise) == text
