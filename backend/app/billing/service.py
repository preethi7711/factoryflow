"""Billing: raise a GST invoice from an approved order, dispatch it, or cancel it.

Each public function is one transaction. Dispatch is the only one that moves stock, and it does so
only through inventory.post_movements(); cancellation undoes it through inventory.post_reversals().
Billing never writes the sales tables; it reads and transitions orders through sales.service.
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import AppUser
from app.billing.models import (
    CreditNote,
    CreditNoteLine,
    Dispatch,
    DispatchLine,
    Invoice,
    InvoiceLine,
    InvoiceSequence,
    InvoiceStatus,
)
from app.billing.schemas import (
    CancelCreate,
    CancelResult,
    CreditNoteOut,
    DispatchCreate,
    InvoiceCreate,
    InvoiceLineOut,
    InvoiceOut,
)
from app.core import gst
from app.core.errors import AppError, not_found
from app.inventory import service as inventory
from app.inventory.models import MovementType, SourceType, StockMovement
from app.inventory.service import MovementLine, ReversalLine
from app.masters import service as masters
from app.sales import service as sales
from app.sales.models import OrderStatus

# ---- reading / shaping ---------------------------------------------------------------


def _invoice_out(db: Session, invoice: Invoice) -> InvoiceOut:
    customer = masters.get_customer(db, invoice.customer_id)
    return InvoiceOut(
        id=invoice.id,
        invoice_no=invoice.invoice_no,
        order_id=invoice.order_id,
        customer_id=invoice.customer_id,
        customer_code=customer.code,
        customer_gstin=customer.gstin,
        fy=invoice.fy,
        seq=invoice.seq,
        invoice_date=invoice.invoice_date,
        place_of_supply_state=invoice.place_of_supply_state,
        supply_type=invoice.supply_type,
        status=invoice.status,
        taxable_paise=invoice.taxable_paise,
        cgst_paise=invoice.cgst_paise,
        sgst_paise=invoice.sgst_paise,
        igst_paise=invoice.igst_paise,
        total_paise=invoice.total_paise,
        lines=[
            InvoiceLineOut(
                id=line.id,
                item_id=line.item_id,
                item_code=masters.get_item(db, line.item_id).code,
                hsn=line.hsn,
                qty=line.qty,
                uom=line.uom,
                unit_price_paise=line.unit_price_paise,
                gst_rate_bp=line.gst_rate_bp,
                taxable_paise=line.taxable_paise,
                cgst_paise=line.cgst_paise,
                sgst_paise=line.sgst_paise,
                igst_paise=line.igst_paise,
            )
            for line in invoice.lines
        ],
    )


def _credit_note_out(cn: CreditNote) -> CreditNoteOut:
    return CreditNoteOut(
        id=cn.id,
        cn_no=cn.cn_no,
        invoice_id=cn.invoice_id,
        cn_date=cn.cn_date,
        reason=cn.reason,
        taxable_paise=cn.taxable_paise,
        cgst_paise=cn.cgst_paise,
        sgst_paise=cn.sgst_paise,
        igst_paise=cn.igst_paise,
        total_paise=cn.total_paise,
    )


def _get_invoice(db: Session, invoice_id: int, *, lock: bool = False) -> Invoice:
    q = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        q = q.with_for_update()
    invoice = db.scalar(q)
    if invoice is None:
        raise not_found("invoice", invoice_id)
    return invoice


def get_invoice(db: Session, invoice_id: int) -> InvoiceOut:
    return _invoice_out(db, _get_invoice(db, invoice_id))


# ---- FY numbering --------------------------------------------------------------------


def _next_seq(db: Session, fy: str) -> int:
    """The next gapless sequence number for a financial year. The fy row is created if missing,
    then locked FOR UPDATE and bumped: concurrent invoices serialise here, and a rolled-back
    invoice rolls back its bump, so the series never skips a number."""
    db.execute(
        text(
            "INSERT INTO invoice_sequence (fy, last_seq) VALUES (:fy, 0)"
            " ON CONFLICT (fy) DO NOTHING"
        ),
        {"fy": fy},
    )
    row = db.scalar(select(InvoiceSequence).where(InvoiceSequence.fy == fy).with_for_update())
    assert row is not None  # just inserted-or-existing
    row.last_seq += 1
    db.flush()
    return row.last_seq


# ---- writing -------------------------------------------------------------------------


def create_invoice(db: Session, order_id: int, data: InvoiceCreate, user: AppUser) -> InvoiceOut:
    """Raise a GST invoice from an approved order. Tax is computed per line by place of supply;
    the number FF/<FY>/<seq> is gapless per financial year. No stock moves (that is dispatch)."""
    order = sales.load_order(db, order_id, lock=True)
    if order.status != OrderStatus.APPROVED.value:
        raise AppError(
            409, "ORDER_NOT_APPROVED", f"order {order_id} is {order.status}, not APPROVED"
        )
    customer = masters.get_customer(db, order.customer_id)
    company = masters.get_company(db)
    supply = gst.supply_type(company.state_code, customer.state_code)
    fy = gst.financial_year(data.invoice_date)
    seq = _next_seq(db, fy)
    invoice = Invoice(
        order_id=order.id,
        customer_id=customer.id,
        fy=fy,
        seq=seq,
        invoice_no=gst.invoice_no(fy, seq, company.invoice_prefix),
        invoice_date=data.invoice_date,
        place_of_supply_state=customer.state_code,
        supply_type=supply.value,
        status=InvoiceStatus.ISSUED.value,
        created_by=user.id,
    )
    db.add(invoice)
    db.flush()
    taxes: list[gst.LineTax] = []
    for line in order.lines:
        item = masters.get_item(db, line.item_id)
        taxable = gst.line_taxable_paise(line.qty, line.unit_price_paise)
        tax = gst.line_tax(taxable, line.gst_rate_bp, supply)
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                item_id=item.id,
                hsn=item.hsn,
                qty=line.qty,
                uom=line.uom,
                unit_price_paise=line.unit_price_paise,
                gst_rate_bp=line.gst_rate_bp,
                taxable_paise=taxable,
                cgst_paise=tax.cgst_paise,
                sgst_paise=tax.sgst_paise,
                igst_paise=tax.igst_paise,
            )
        )
        taxes.append(tax)
    totals = gst.invoice_totals(taxes)
    invoice.taxable_paise = totals.taxable_paise
    invoice.cgst_paise = totals.cgst_paise
    invoice.sgst_paise = totals.sgst_paise
    invoice.igst_paise = totals.igst_paise
    invoice.total_paise = totals.total_paise
    db.flush()
    sales.set_status(db, order, OrderStatus.INVOICED, user)
    db.refresh(invoice)  # load the lines just added
    out = _invoice_out(db, invoice)
    audit.record(
        db,
        entity="invoice",
        entity_id=invoice.id,
        action="ISSUE",
        user_id=user.id,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


def dispatch_invoice(
    db: Session, invoice_id: int, data: DispatchCreate, user: AppUser
) -> InvoiceOut:
    """Ship the goods: one DISPATCH movement per line, posted through inventory (FIFO lots, valued
    at WAC). Finished-goods stock drops here. A second dispatch of the same invoice is refused."""
    invoice = _get_invoice(db, invoice_id, lock=True)
    if invoice.status == InvoiceStatus.CANCELLED.value:
        raise AppError(409, "INVOICE_CANCELLED", f"invoice {invoice_id} has been cancelled")
    if invoice.status == InvoiceStatus.DISPATCHED.value:
        raise AppError(409, "ALREADY_DISPATCHED", f"invoice {invoice_id} is already dispatched")
    order = sales.load_order(db, invoice.order_id, lock=True)
    before = _invoice_out(db, invoice).model_dump(mode="json")
    dispatch = Dispatch(invoice_id=invoice.id, dispatch_date=data.dispatch_date, created_by=user.id)
    db.add(dispatch)
    db.flush()
    movements: list[MovementLine] = []
    for line in invoice.lines:
        dispatch_line = DispatchLine(dispatch_id=dispatch.id, item_id=line.item_id, qty=line.qty)
        db.add(dispatch_line)
        db.flush()
        movements.append(
            MovementLine(
                line.item_id, -line.qty, MovementType.DISPATCH, source_line_id=dispatch_line.id
            )
        )
    inventory.post_movements(
        db,
        source_type=SourceType.DISPATCH,
        source_id=dispatch.id,
        movement_date=data.dispatch_date,
        user_id=user.id,
        lines=movements,
    )
    invoice.status = InvoiceStatus.DISPATCHED.value
    sales.set_status(db, order, OrderStatus.DISPATCHED, user)
    db.flush()
    out = _invoice_out(db, invoice)
    audit.record(
        db,
        entity="invoice",
        entity_id=invoice.id,
        action="DISPATCH",
        user_id=user.id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


def cancel_invoice(db: Session, invoice_id: int, data: CancelCreate, user: AppUser) -> CancelResult:
    """Cancel an invoice with a credit note (the invoice number stays used, A12). If the invoice
    was dispatched, the credit note's REVERSAL movements add the goods back at the exact value
    they left, so stock and WAC return to where they were."""
    invoice = _get_invoice(db, invoice_id, lock=True)
    if invoice.status == InvoiceStatus.CANCELLED.value:
        raise AppError(409, "ALREADY_CANCELLED", f"invoice {invoice_id} is already cancelled")
    order = sales.load_order(db, invoice.order_id, lock=True)
    before = _invoice_out(db, invoice).model_dump(mode="json")
    cn = CreditNote(
        invoice_id=invoice.id,
        cn_date=data.cn_date,
        reason=data.reason,
        taxable_paise=invoice.taxable_paise,
        cgst_paise=invoice.cgst_paise,
        sgst_paise=invoice.sgst_paise,
        igst_paise=invoice.igst_paise,
        total_paise=invoice.total_paise,
        created_by=user.id,
    )
    db.add(cn)
    db.flush()
    cn.cn_no = f"CN/{invoice.fy}/{cn.id:04d}"
    cn_line_of_item: dict[int, int] = {}
    for line in invoice.lines:
        cn_line = CreditNoteLine(
            credit_note_id=cn.id,
            item_id=line.item_id,
            qty=line.qty,
            taxable_paise=line.taxable_paise,
            cgst_paise=line.cgst_paise,
            sgst_paise=line.sgst_paise,
            igst_paise=line.igst_paise,
        )
        db.add(cn_line)
        db.flush()
        cn_line_of_item[line.item_id] = cn_line.id

    if invoice.status == InvoiceStatus.DISPATCHED.value:
        dispatch_ids = list(
            db.scalars(select(Dispatch.id).where(Dispatch.invoice_id == invoice.id))
        )
        dispatched = db.scalars(
            select(StockMovement).where(
                StockMovement.source_type == SourceType.DISPATCH.value,
                StockMovement.source_id.in_(dispatch_ids),
                StockMovement.movement_type == MovementType.DISPATCH.value,
            )
        )
        reversals = [
            ReversalLine(original_id=m.id, source_line_id=cn_line_of_item[m.item_id])
            for m in dispatched
        ]
        inventory.post_reversals(
            db,
            source_type=SourceType.CREDIT_NOTE,
            source_id=cn.id,
            movement_date=data.cn_date,
            user_id=user.id,
            lines=reversals,
        )

    invoice.status = InvoiceStatus.CANCELLED.value
    sales.set_status(db, order, OrderStatus.CANCELLED, user)
    db.flush()
    out = _invoice_out(db, invoice)
    audit.record(
        db,
        entity="invoice",
        entity_id=invoice.id,
        action="CANCEL",
        user_id=user.id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return CancelResult(invoice=out, credit_note=_credit_note_out(cn))
