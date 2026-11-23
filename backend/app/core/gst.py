"""GST arithmetic and invoice numbering (pure; rules in .claude/skills/gst-rules).

- Place of supply = customer's state. Same state as the company -> INTRA (CGST + SGST, half
  the rate each). Different state -> INTER (IGST, full rate). Never both.
- Tax is computed and rounded **per line**, then summed. Never recomputed on the invoice total,
  so the printed lines always add up to the printed total.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.core.money import apply_bp


class SupplyType(StrEnum):
    INTRA = "INTRA"
    INTER = "INTER"


def _state_code(code: str) -> str:
    if len(code) != 2 or not code.isdigit():
        raise ValueError(f"state code must be 2 digits (e.g. '33' for Tamil Nadu), got {code!r}")
    return code


def supply_type(company_state: str, place_of_supply: str) -> SupplyType:
    same = _state_code(company_state) == _state_code(place_of_supply)
    return SupplyType.INTRA if same else SupplyType.INTER


@dataclass(frozen=True)
class LineTax:
    taxable_paise: int
    cgst_paise: int = 0
    sgst_paise: int = 0
    igst_paise: int = 0

    @property
    def tax_paise(self) -> int:
        return self.cgst_paise + self.sgst_paise + self.igst_paise

    @property
    def total_paise(self) -> int:
        return self.taxable_paise + self.tax_paise


def line_taxable_paise(qty: Decimal, price_paise: int) -> int:
    """qty x price. Exact for whole packets; a fraction of a paisa means bad input, not rounding."""
    amount = qty * price_paise
    if amount != amount.to_integral_value():
        raise ValueError(f"{qty} x {price_paise} paise is not a whole number of paise")
    return int(amount)


def line_tax(taxable_paise: int, rate_bp: int, supply: SupplyType) -> LineTax:
    """Tax one invoice line. rate_bp: 500 = 5%."""
    if rate_bp < 0:
        raise ValueError("GST rate can't be negative")
    if supply is SupplyType.INTRA:
        half = apply_bp(
            taxable_paise, Decimal(rate_bp) / 2
        )  # CGST and SGST each round on their own
        return LineTax(taxable_paise, cgst_paise=half, sgst_paise=half)
    return LineTax(taxable_paise, igst_paise=apply_bp(taxable_paise, rate_bp))


def invoice_totals(lines: Iterable[LineTax]) -> LineTax:
    """Sum of the lines, column by column."""
    rows = list(lines)
    return LineTax(
        taxable_paise=sum(r.taxable_paise for r in rows),
        cgst_paise=sum(r.cgst_paise for r in rows),
        sgst_paise=sum(r.sgst_paise for r in rows),
        igst_paise=sum(r.igst_paise for r in rows),
    )


def financial_year(d: date) -> str:
    """Indian FY runs 1 April to 31 March: 2026-11-03 -> '2026-27', 2027-03-31 -> '2026-27'."""
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def invoice_no(fy: str, seq: int, prefix: str = "FF") -> str:
    """invoice_no('2026-27', 1) == 'FF/2026-27/0001'. seq is gapless per FY (billing locks it)."""
    if seq < 1:
        raise ValueError("invoice sequence starts at 1")
    return f"{prefix}/{fy}/{seq:04d}"


def gstin_warnings(gstin: str | None, state_code: str) -> list[str]:
    """Soft checks only (warn, don't block): 15 characters, first 2 digits = state code."""
    if not gstin:
        return []
    warnings = []
    if len(gstin) != 15:
        warnings.append(f"GSTIN should be 15 characters, got {len(gstin)}")
    if gstin[:2] != state_code:
        warnings.append(
            f"GSTIN starts with {gstin[:2]!r} but the customer's state is {state_code!r}"
        )
    return warnings
