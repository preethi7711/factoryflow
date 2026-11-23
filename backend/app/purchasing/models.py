"""Purchases (goods received). Each line creates a lot and posts a PURCHASE movement."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import QTY, Base


class Purchase(Base):
    __tablename__ = "purchase"
    __table_args__ = (CheckConstraint("supply_type IN ('INTRA', 'INTER')", name="supply_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"))
    purchase_date: Mapped[date] = mapped_column(Date)
    bill_no: Mapped[str | None] = mapped_column(String(40))  # the supplier's invoice number
    supply_type: Mapped[str] = mapped_column(String(5))  # decides CGST+SGST vs IGST on input tax
    # Totals = sums of the lines (stored, like any posted document's totals).
    taxable_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    cgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    sgst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    igst_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["PurchaseLine"]] = relationship(order_by="PurchaseLine.id")


class PurchaseLine(Base):
    __tablename__ = "purchase_line"
    __table_args__ = (
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("rate_paise >= 0", name="rate_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchase.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)  # base unit
    uom: Mapped[str] = mapped_column(String(8))  # the item's base unit
    entered_qty: Mapped[Decimal] = mapped_column(QTY)  # as typed, e.g. 60 ...
    entered_uom: Mapped[str] = mapped_column(String(16))  # ... kg
    rate_paise: Mapped[int] = mapped_column(BigInteger)  # per entered_uom, before tax (A15)
    value_paise: Mapped[int] = mapped_column(BigInteger)  # taxable value = stock value
    gst_rate_bp: Mapped[int]
    cgst_paise: Mapped[int] = mapped_column(BigInteger)
    sgst_paise: Mapped[int] = mapped_column(BigInteger)
    igst_paise: Mapped[int] = mapped_column(BigInteger)
    lot_id: Mapped[int] = mapped_column(ForeignKey("stock_lot.id"))
