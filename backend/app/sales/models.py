"""Sales orders and the idempotency guard (docs/architecture.md sections 1, 5).

An order is priced once by the server from the price list (masters.Item.sale_price_paise),
so a salesman's phone can never set its own price. The order carries a `client_uuid` (the
Idempotency-Key the phone sent); it is UNIQUE, so the same order queued twice offline lands once.

No stock moves when an order is placed or approved. Stock leaves only on dispatch (billing),
through inventory.post_movements(). Approval reserves finished goods logically (the stock-cover
check), not physically.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import QTY, Base


class OrderStatus(StrEnum):
    PENDING = "PENDING"  # placed by a salesman, awaiting admin approval
    APPROVED = "APPROVED"  # stock-cover checked; may be invoiced
    INVOICED = "INVOICED"  # a GST invoice exists; stock still on hand
    DISPATCHED = "DISPATCHED"  # goods shipped; DISPATCH movements posted
    CANCELLED = "CANCELLED"  # invoice cancelled with a credit note


# Orders that have reserved finished goods but not yet shipped them. Their quantity is still
# physically in stock, so the stock-cover check must subtract it from what a new order may take.
RESERVED_STATUSES = (OrderStatus.APPROVED.value, OrderStatus.INVOICED.value)


class SalesOrder(Base):
    __tablename__ = "sales_order"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'INVOICED', 'DISPATCHED', 'CANCELLED')",
            name="status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_uuid: Mapped[str] = mapped_column(String(64), unique=True)  # the Idempotency-Key
    customer_id: Mapped[int] = mapped_column(ForeignKey("customer.id"))
    salesman_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))  # who placed it (RBAC)
    order_date: Mapped[date] = mapped_column()
    status: Mapped[str] = mapped_column(String(12), default=OrderStatus.PENDING.value)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["OrderLine"]] = relationship(order_by="OrderLine.id")


class OrderLine(Base):
    __tablename__ = "order_line"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "item_id"
        ),  # one line per product, so reserving is unambiguous
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("unit_price_paise >= 0", name="price_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_order.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)  # base unit (pkt for finished goods)
    uom: Mapped[str] = mapped_column(String(8))  # the item's base unit
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)  # from the price list at order time
    gst_rate_bp: Mapped[int]  # captured with the price, so the invoice is reproducible


class IdempotencyKey(Base):
    """One row per accepted Idempotency-Key, so a replayed request returns the first result
    instead of creating a second document (docs/architecture.md section 5).

    Same key + same body -> the stored response is replayed. Same key + different body -> 409.
    Written in the same transaction as the document it guards, so a replay can never return a
    response for a document whose transaction rolled back.
    """

    __tablename__ = "idempotency_key"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    route: Mapped[str] = mapped_column(String(80))  # e.g. "POST /orders"
    request_hash: Mapped[str] = mapped_column(String(64))  # sha256 of the canonical request body
    status_code: Mapped[int]
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
