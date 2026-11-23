"""Planned vs actual, in basis points (A1, A2).

planned = BOM qty per batch x batches. variance = (actual - planned) / planned.
Flag when |variance| > tolerance, **strictly** (A2): exactly 3.00% is not flagged.

The flag uses the exact numbers, not the rounded bp. Otherwise 3.004% would round to
300 bp and slip under a 300 bp tolerance.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.money import BP_PER_UNIT, round_half_up

DEFAULT_TOLERANCE_BP = 300  # 3.00%, configurable per item (item.variance_tol_bp)


@dataclass(frozen=True)
class Variance:
    planned: Decimal
    actual: Decimal
    variance_bp: int  # rounded half-up, for display: -600 = -6.00%
    flagged: bool


def planned_qty(per_batch: Decimal, batches: Decimal) -> Decimal:
    return per_batch * batches


def variance(
    planned: Decimal, actual: Decimal, tolerance_bp: int = DEFAULT_TOLERANCE_BP
) -> Variance:
    if planned <= 0:
        raise ValueError("planned quantity must be positive to compute a variance")
    diff = actual - planned
    bp = round_half_up(diff * BP_PER_UNIT / planned)
    flagged = abs(diff) * BP_PER_UNIT > tolerance_bp * planned
    return Variance(planned, actual, bp, flagged)
