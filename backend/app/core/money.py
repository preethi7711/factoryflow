"""Money as integer paise (1 rupee = 100 paise).

Why integers: floats can't store 0.1 exactly, so sums drift by fractions of a paisa and
totals stop matching. An int is exact, and rounding happens only where we call
`round_half_up` on purpose (tax per line, issue value, cost per unit).
"""

from decimal import ROUND_HALF_UP, Decimal

PAISE_PER_RUPEE = 100
BP_PER_UNIT = 10_000  # basis points: 500 bp = 5%


def round_half_up(x: Decimal) -> int:
    """Round to a whole paisa, halves away from zero (2.5 -> 3, -2.5 -> -3).

    Python's round() uses banker's rounding (2.5 -> 2), which is not what invoices expect.
    """
    if not isinstance(x, Decimal):
        raise TypeError(f"round_half_up needs a Decimal, got {type(x).__name__}")
    return int(x.to_integral_value(rounding=ROUND_HALF_UP))


def to_paise(rupees: str | int | Decimal) -> int:
    """Parse a rupee amount ("45", "45.50") into paise. More than 2 decimals is an error."""
    if isinstance(rupees, float | bool):
        raise TypeError("money must not be a float; pass a string like '45.50'")
    amount = Decimal(str(rupees)) * PAISE_PER_RUPEE
    if amount != amount.to_integral_value():
        raise ValueError(f"{rupees!r} has fractions of a paisa")
    return int(amount)


def apply_bp(amount_paise: int, bp: int | Decimal) -> int:
    """amount x rate, rounded half-up to the paisa. apply_bp(750000, 250) == 18750."""
    return round_half_up(Decimal(amount_paise) * Decimal(bp) / BP_PER_UNIT)


def format_inr(paise: int) -> str:
    """Indian digit grouping: 12345678 -> '₹1,23,456.78'."""
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(paise), PAISE_PER_RUPEE)
    digits = str(rupees)
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:  # after the last 3 digits, India groups in pairs
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join([*groups, tail])
    return f"{sign}₹{grouped}.{rem:02d}"
