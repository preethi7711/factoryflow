"""Billing: GST invoices, gapless FY numbering, dispatch and credit notes (gst-rules skill).

A GST invoice is raised from an approved order. Its number FF/<FY>/<seq> is gapless per financial
year, guarded by a row-locked invoice_sequence. Tax is CGST+SGST (intra-state) or IGST (inter),
computed and stored per line so the printed lines always sum to the printed total.

Dispatch is where finished goods leave stock: it posts DISPATCH movements through
inventory.post_movements(). A posted invoice is never deleted; it is cancelled with a credit note,
whose REVERSAL movements mirror the dispatch exactly (invariant 7).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import QTY, Base


class InvoiceStatus(StrEnum):
    ISSUED = "ISSUED"  # raised; goods still on hand
    DISPATCHED = "DISPATCHED"  # goods shipped; DISPATCH movements posted
    CANCELLED = "CANCELLED"  # cancelled with a credit note


class InvoiceSequence(Base):
    """One row per financial year, holding the last sequence number issued. Locked FOR UPDATE
    while an invoice is being numbered, so numbering is gapless even under concurrency."""

    __tablename__ = "invoice_sequence"

    fy: Mapped[str] = mapped_column(String(7), primary_key=True)  # e.g. "2026-27"
    last_seq: Mapped[int] = mapped_column(default=0)


class Invoice(Base):
    __tablename__ = "invoice"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_invoice_order"),  # one invoice per order
        UniqueConstraint("invoice_no", name="uq_invoice_no"),
        UniqueConstraint("fy", "seq", name="uq_invoice_fy_seq"),
        CheckConstraint("supply_type IN ('INTRA', 'INTER')", name="supply_type"),
        CheckConstraint("status IN ('ISSUED', 'DISPATCHED', 'CANCELLED')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    fy: Mapped[str] = mapped_column(String(7))
    seq: Mapped[int]
    invoice_no: Mapped[str] = mapped_column(String(30))
    invoice_date: Mapped[date] = mapped_column(Date)
    place_of_supply_state: Mapped[str] = mapped_column(String(2))  # the customer's state
    supply_type: Mapped[str] = mapped_column(String(5))  # INTRA (CGST+SGST) or INTER (IGST)
    taxable_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(12), default=InvoiceStatus.ISSUED.value)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["InvoiceLine"]] = relationship(order_by="InvoiceLine.id")


class InvoiceLine(Base):
    __tablename__ = "invoice_line"
    __table_args__ = (
        UniqueConstraint("invoice_id", "item_id"),
        CheckConstraint("qty > 0", name="qty_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    hsn: Mapped[str | None] = mapped_column(String(8))  # snapshot from the item, for the PDF
    qty: Mapped[Decimal] = mapped_column(QTY)  # base unit
    uom: Mapped[str] = mapped_column(String(8))
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    gst_rate_bp: Mapped[int]
    taxable_paise: Mapped[int] = mapped_column(BigInteger)  # qty x unit price
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0)


class Dispatch(Base):
    """Goods leaving for one invoice. Each line posts a DISPATCH movement through inventory."""

    __tablename__ = "dispatch"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    dispatch_date: Mapped[date] = mapped_column(Date)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["DispatchLine"]] = relationship(order_by="DispatchLine.id")


class DispatchLine(Base):
    __tablename__ = "dispatch_line"
    __table_args__ = (CheckConstraint("qty > 0", name="qty_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_id: Mapped[int] = mapped_column(ForeignKey("dispatch.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)  # base unit, positive (the quantity shipped)


class CreditNote(Base):
    """Cancels an invoice (A12: the invoice number stays used). Its REVERSAL movements undo the
    dispatch exactly, so finished goods and their value return to where they were."""

    __tablename__ = "credit_note"
    __table_args__ = (UniqueConstraint("invoice_id", name="uq_credit_note_invoice"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    cn_no: Mapped[str | None] = mapped_column(String(30))  # CN/<FY>/<id>, written just after insert
    cn_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    taxable_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["CreditNoteLine"]] = relationship(order_by="CreditNoteLine.id")


class CreditNoteLine(Base):
    __tablename__ = "credit_note_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    credit_note_id: Mapped[int] = mapped_column(ForeignKey("credit_note.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)  # base unit, positive (credited quantity)
    taxable_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
