"""Customer payments and how they are allocated to invoices (docs/architecture.md section 3).

A payment is money received from a customer; its allocations say which invoices it pays. Outstanding
is never stored: it is invoice.total - SUM(allocations) over non-cancelled invoices, read on demand.
Payments move money, not stock, so nothing here touches the ledger.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (CheckConstraint("amount_paise > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    payment_date: Mapped[date] = mapped_column(Date)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str | None] = mapped_column(String(60))  # cheque/UPI ref, optional
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    allocations: Mapped[list["PaymentAllocation"]] = relationship(order_by="PaymentAllocation.id")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocation"
    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id"),  # one line per invoice within a payment
        CheckConstraint("amount_paise > 0", name="amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payment.id"))
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoice.id"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
