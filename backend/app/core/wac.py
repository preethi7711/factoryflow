"""Moving weighted average cost (A6), plus cost per unit.

An item's stock has a quantity (base units) and a value (paise), both sums of the ledger.
Average cost = value / qty. A receipt adds qty and value; an issue takes qty at the average.

Why WAC and not FIFO cost: flour from two purchases sits in the same bin and is fungible.
WAC gives one cost per item, which is simple to explain and audit. Lots still exist, but
only for traceability (batch, expiry), not for cost.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import round_half_up


class InsufficientStockError(ValueError):
    def __init__(self, requested: Decimal, available: Decimal) -> None:
        super().__init__(f"requested {requested}, only {available} available")
        self.requested = requested
        self.available = available


def receipt_value(qty: Decimal, rate_paise: int) -> int:
    """Value of a receipt line, in the unit the rate is quoted in: 60 kg x 4500 paise/kg = 270000.

    Value is computed before converting qty to base units, because the per-gram rate
    (4.5 paise) is not a whole number of paise.
    """
    return round_half_up(qty * rate_paise)


def issue_value(qty: Decimal, bal_qty: Decimal, bal_value: int) -> int:
    """Value taken out by issuing qty from a balance, at the current average cost.

    Anti-drift rule: an issue that empties the stock takes **all** the remaining value,
    so rounding leftovers can't pile up as value sitting on zero quantity.
    """
    if qty <= 0:
        raise ValueError("issue quantity must be positive")
    if qty > bal_qty:
        raise InsufficientStockError(qty, bal_qty)
    if qty == bal_qty:
        return bal_value
    return round_half_up(qty * bal_value / bal_qty)


@dataclass(frozen=True)
class Balance:
    """A running balance, for reasoning and tests. The real balance is always SUM(ledger)."""

    qty: Decimal = Decimal(0)
    value_paise: int = 0

    def receive(self, qty: Decimal, value_paise: int) -> "Balance":
        return Balance(self.qty + qty, self.value_paise + value_paise)

    def issue(self, qty: Decimal) -> tuple[int, "Balance"]:
        value = issue_value(qty, self.qty, self.value_paise)
        return value, Balance(self.qty - qty, self.value_paise - value)


def cost_per_unit_paise(total_paise: int, good_qty: Decimal) -> int:
    """(materials + overheads) / good output, half-up: 585500 / 188 = 3114.36 -> 3114 (B13)."""
    if good_qty <= 0:
        raise ValueError("good output must be positive to cost it")
    return round_half_up(Decimal(total_paise) / good_qty)
