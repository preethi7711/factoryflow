"""The GST tax invoice as a PDF (fpdf2 + the bundled DejaVu TTF, so the rupee sign renders).

Generated on request — Render Free has no persistent disk, so nothing is stored. The numbers come
straight off the invoice row (taxable, CGST/SGST or IGST, total), already computed per line in
billing, so the printed lines always sum to the printed total.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.billing.models import Invoice
from app.core.money import format_inr
from app.masters import service as masters

FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans.ttf"
FONT = "DejaVu"


def _money(paise: int) -> str:
    return format_inr(paise)


def render_invoice_pdf(db: Session, invoice: Invoice) -> bytes:
    from fpdf import FPDF  # imported lazily so the rest of billing needs no PDF dependency

    company = masters.get_company(db)
    customer = masters.get_customer(db, invoice.customer_id)
    intra = invoice.supply_type == "INTRA"

    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font(FONT, "", str(FONT_PATH))
    pdf.add_page()

    pdf.set_font(FONT, size=15)
    pdf.cell(0, 9, company.name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, size=9)
    pdf.cell(
        0,
        5,
        f"GSTIN: {company.gstin or '-'}    State code: {company.state_code}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    if company.address:
        pdf.cell(0, 5, company.address, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(FONT, size=12)
    pdf.cell(0, 7, "Tax Invoice", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, size=9)
    meta = (
        f"Invoice no: {invoice.invoice_no}    "
        f"Date: {invoice.invoice_date.isoformat()}    FY: {invoice.fy}"
    )
    pdf.cell(0, 5, meta, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Bill to
    pdf.set_font(FONT, size=10)
    pdf.cell(0, 6, f"Bill to: {customer.name} ({customer.code})", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, size=9)
    bill_to = (
        f"GSTIN: {customer.gstin or '-'}    "
        f"Place of supply: {invoice.place_of_supply_state}    Supply: {invoice.supply_type}"
    )
    pdf.cell(0, 5, bill_to, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Line table header
    widths = [50, 20, 20, 25, 30, 25, 20]
    headers = ["Item", "HSN", "Qty", "Rate", "Taxable", "Tax", "Total"]
    pdf.set_font(FONT, size=9)
    for w, h in zip(widths, headers, strict=True):
        pdf.cell(w, 7, h, border=1)
    pdf.ln(7)
    for line in invoice.lines:
        item = masters.get_item(db, line.item_id)
        tax = line.cgst_paise + line.sgst_paise + line.igst_paise
        total = line.taxable_paise + tax
        cells = [
            (widths[0], item.code),
            (widths[1], line.hsn or "-"),
            (widths[2], f"{line.qty} {line.uom}"),
            (widths[3], _money(line.unit_price_paise)),
            (widths[4], _money(line.taxable_paise)),
            (widths[5], _money(tax)),
            (widths[6], _money(total)),
        ]
        for w, text in cells:
            pdf.cell(w, 7, text, border=1)
        pdf.ln(7)
    pdf.ln(3)

    # Totals
    pdf.set_font(FONT, size=9)
    lines_out = [("Taxable value", invoice.taxable_paise)]
    if intra:
        lines_out += [("CGST", invoice.cgst_paise), ("SGST", invoice.sgst_paise)]
    else:
        lines_out += [("IGST", invoice.igst_paise)]
    lines_out += [("Grand total", invoice.total_paise)]
    for label, paise in lines_out:
        pdf.cell(150, 6, label, border=0, align="R")
        pdf.cell(40, 6, _money(paise), border=0, align="R")
        pdf.ln(6)

    return bytes(pdf.output())
