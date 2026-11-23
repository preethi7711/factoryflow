from decimal import Decimal

import pytest

from app.core.units import UnitError, check_qty_scale, from_base, parse_qty, to_base

MURUKKU_PACKS = {"carton": Decimal(20)}


@pytest.mark.parametrize(
    ("qty", "uom", "base", "expected"),
    [
        ("40", "kg", "g", "40000"),  # benchmark flour issue
        ("10.5", "l", "ml", "10500"),  # benchmark oil issue
        ("1.2", "kg", "g", "1200"),  # spice mix
        ("194", "pcs", "pcs", "194"),  # pouches
        ("10.5", "L", "ml", "10500"),  # unit codes are case-insensitive
        ("250", "g", "g", "250"),
    ],
)
def test_to_base(qty: str, uom: str, base: str, expected: str) -> None:
    assert to_base(qty, uom, base) == Decimal(expected)


def test_item_specific_pack_unit() -> None:
    assert to_base("9", "carton", "pkt", MURUKKU_PACKS) == 180


def test_cross_dimension_is_an_error() -> None:
    with pytest.raises(UnitError):
        to_base("1", "kg", "ml")
    with pytest.raises(UnitError):
        to_base("1", "pcs", "pkt")  # a pouch is not a packet


def test_unknown_unit_and_non_base_unit_are_errors() -> None:
    with pytest.raises(UnitError):
        to_base("1", "tonne", "g")
    with pytest.raises(UnitError):
        to_base("1", "g", "kg")  # stock is never stored in kg


def test_quantities_refuse_floats_and_junk() -> None:
    with pytest.raises(TypeError):
        parse_qty(10.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        parse_qty("ten")
    with pytest.raises(ValueError):
        parse_qty("NaN")


def test_from_base_for_display() -> None:
    assert from_base(Decimal(120000), "kg", "g") == 120  # B1 flour closing
    assert from_base(Decimal(19500), "l", "ml") == Decimal("19.5")  # B2 oil closing
    assert from_base(Decimal(188), "carton", "pkt", MURUKKU_PACKS) == Decimal("9.4")


def test_base_quantities_keep_at_most_three_decimals() -> None:
    assert str(check_qty_scale(Decimal("1200.5"))) == "1200.500"  # same scale as the column
    assert check_qty_scale(Decimal("0.001")) == Decimal("0.001")
    with pytest.raises(ValueError):
        check_qty_scale(Decimal("1.2345"))  # Postgres would silently round this to 1.235
