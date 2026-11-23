"""Units of measure. Every item stores stock in one base unit (A11): g, ml, pcs or pkt.

Conversion happens once, at the edge (API input), with exact Decimal multiplication.
Converting between dimensions (kg -> ml) is always an error, never a guess.
"""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

# code -> (dimension, how many base units one of it is)
GLOBAL_UNITS: dict[str, tuple[str, Decimal]] = {
    "g": ("mass", Decimal(1)),
    "kg": ("mass", Decimal(1000)),
    "ml": ("volume", Decimal(1)),
    "l": ("volume", Decimal(1000)),
    "pcs": ("count", Decimal(1)),
    "pkt": ("pack", Decimal(1)),
}


# Discrete base units: quantities must be whole numbers (you can't have half a packet).
COUNT_UNITS = frozenset({"pcs", "pkt"})


class UnitError(ValueError):
    """Unknown unit, wrong dimension, or a base unit that isn't one."""


def parse_qty(value: str | int | Decimal) -> Decimal:
    """Quantities arrive as decimal strings ("10.5"). Floats are refused: 10.5 as a float is fine,
    but 0.1 is not exact, and we can't tell which kind we were given."""
    if isinstance(value, float | bool):
        raise TypeError("quantity must not be a float; pass a string like '10.5'")
    try:
        qty = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if not qty.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    return qty


QTY_PLACES = 3  # quantity columns are NUMERIC(18, 3)


def check_qty_scale(qty: Decimal) -> Decimal:
    """Refuse a base-unit quantity with more than 3 decimals (Postgres would silently round it,
    and a silently rounded quantity is a stock error nobody can trace). Returns the value at
    exactly 3 places, so what we hold in memory is what the database stores: 30000 -> 30000.000.
    """
    scaled = qty.quantize(Decimal(1).scaleb(-QTY_PLACES))
    if scaled != qty:
        raise ValueError(f"{qty} has more than {QTY_PLACES} decimal places in the base unit")
    return scaled


def _unit(code: str) -> tuple[str, Decimal]:
    try:
        return GLOBAL_UNITS[code.lower()]
    except KeyError:
        raise UnitError(f"unknown unit {code!r}") from None


def _check_base(base_uom: str) -> str:
    dimension, factor = _unit(base_uom)
    if factor != 1:
        raise UnitError(f"{base_uom!r} is not a base unit (use g, ml, pcs or pkt)")
    return dimension


def to_base(
    qty: str | int | Decimal,
    uom: str,
    base_uom: str,
    pack_units: Mapping[str, Decimal] | None = None,
) -> Decimal:
    """Convert qty in `uom` to the item's base unit.

    pack_units are item-specific packs, e.g. Murukku {"carton": 20} (1 carton = 20 pkt).
    to_base("10.5", "l", "ml") == Decimal("10500.0")
    """
    amount = parse_qty(qty)
    dimension = _check_base(base_uom)
    packs = {k.lower(): Decimal(v) for k, v in (pack_units or {}).items()}
    if uom.lower() in packs:
        return amount * packs[uom.lower()]
    unit_dimension, factor = _unit(uom)
    if unit_dimension != dimension:
        raise UnitError(f"can't convert {uom!r} ({unit_dimension}) to {base_uom!r} ({dimension})")
    return amount * factor


def from_base(
    qty_base: Decimal,
    uom: str,
    base_uom: str,
    pack_units: Mapping[str, Decimal] | None = None,
) -> Decimal:
    """Inverse of to_base, for display: from_base(Decimal(120000), "kg", "g") == 120."""
    one = to_base(1, uom, base_uom, pack_units)
    return qty_base / one
