from datetime import date
from decimal import Decimal

import pytest

from app.core.gst import (
    LineTax,
    SupplyType,
    financial_year,
    gstin_warnings,
    invoice_no,
    invoice_totals,
    line_tax,
    line_taxable_paise,
    supply_type,
)

TN, KA = "33", "29"


def test_place_of_supply_decides_supply_type() -> None:
    assert supply_type(TN, TN) is SupplyType.INTRA  # Retailer A, Tamil Nadu
    assert supply_type(TN, KA) is SupplyType.INTER  # Distributor B, Karnataka
    with pytest.raises(ValueError):
        supply_type("TN", KA)


def test_b10_retailer_a_invoice() -> None:
    taxable = line_taxable_paise(Decimal(150), 5000)
    t = line_tax(taxable, 500, SupplyType.INTRA)
    assert (t.taxable_paise, t.cgst_paise, t.sgst_paise, t.igst_paise) == (750000, 18750, 18750, 0)
    assert t.total_paise == 787500


def test_b12b_distributor_b_preview() -> None:
    t = line_tax(line_taxable_paise(Decimal(120), 5000), 500, SupplyType.INTER)
    assert (t.taxable_paise, t.cgst_paise, t.sgst_paise, t.igst_paise) == (600000, 0, 0, 30000)
    assert t.total_paise == 630000


def test_odd_paise_each_half_rounds_separately() -> None:
    # 5% of 1010 paise = 50.5. Intra: 25.25 -> 25 twice = 50. Inter: 50.5 -> 51.
    assert line_tax(1010, 500, SupplyType.INTRA).tax_paise == 50
    assert line_tax(1010, 500, SupplyType.INTER).tax_paise == 51


@pytest.mark.parametrize(
    ("rate_bp", "intra_each", "inter"),
    [(0, 0, 0), (500, 250, 500), (1200, 600, 1200), (1800, 900, 1800)],
)
def test_rates(rate_bp: int, intra_each: int, inter: int) -> None:
    intra = line_tax(10000, rate_bp, SupplyType.INTRA)
    assert (intra.cgst_paise, intra.sgst_paise, intra.igst_paise) == (intra_each, intra_each, 0)
    assert line_tax(10000, rate_bp, SupplyType.INTER).igst_paise == inter


def test_fractional_taxable_is_an_error() -> None:
    with pytest.raises(ValueError):
        line_taxable_paise(Decimal("1.5"), 4999)


def test_totals_are_sums_of_rounded_lines_not_tax_on_total() -> None:
    lines = [line_tax(1010, 500, SupplyType.INTER) for _ in range(2)]
    total = invoice_totals(lines)
    assert total == LineTax(taxable_paise=2020, igst_paise=102)  # 51 + 51, not 5% of 2020 (101)


@pytest.mark.parametrize(
    ("d", "fy"),
    [
        (date(2026, 4, 1), "2026-27"),
        (date(2026, 11, 3), "2026-27"),
        (date(2027, 3, 31), "2026-27"),
        (date(2026, 3, 31), "2025-26"),
        (date(2099, 12, 1), "2099-00"),
    ],
)
def test_financial_year(d: date, fy: str) -> None:
    assert financial_year(d) == fy


def test_invoice_no_b10b() -> None:
    assert invoice_no("2026-27", 1) == "FF/2026-27/0001"
    assert invoice_no("2026-27", 12345) == "FF/2026-27/12345"
    with pytest.raises(ValueError):
        invoice_no("2026-27", 0)


def test_gstin_warnings_are_soft() -> None:
    assert gstin_warnings(None, TN) == []
    assert gstin_warnings("33ABCDE1234F1Z5", TN) == []
    assert len(gstin_warnings("29ABCDE1234F1Z5", TN)) == 1
    assert len(gstin_warnings("33ABC", TN)) == 1
