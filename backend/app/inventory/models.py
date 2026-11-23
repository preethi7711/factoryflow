"""The stock ledger (docs/architecture.md section 3). Rules: .claude/skills/stock-ledger.

- stock_movement is append-only (DB trigger). Balance = SUM(qty), value = SUM(value_paise).
  There is no balance column anywhere.
- Every movement names its source document (source_type, source_id, source_line_id).
- (lot_id, item_id) is a composite foreign key, so a movement can't point at another item's lot.
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
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import QTY, Base


class MovementType(StrEnum):
    OPENING = "OPENING"
    PURCHASE = "PURCHASE"
    ISSUE = "ISSUE"
    OUTPUT = "OUTPUT"
    SCRAP = "SCRAP"
    DISPATCH = "DISPATCH"
    ADJUST = "ADJUST"
    COST_ADJUST = "COST_ADJUST"  # value only (qty 0), e.g. overheads added to a run's FG lot
    REVERSAL = "REVERSAL"


class SourceType(StrEnum):
    """The document behind a movement. Each is a table (P4/P5 add theirs)."""

    STOCK_ADJUSTMENT = "stock_adjustment"
    PURCHASE = "purchase"
    PRODUCTION_RUN = "production_run"
    DISPATCH = "dispatch"
    CREDIT_NOTE = "credit_note"


# Quantity sign must match the movement type. Checked in Python first, enforced here as well.
SIGN_RULE = (
    "(movement_type IN ('OPENING', 'PURCHASE', 'OUTPUT') AND qty > 0)"
    " OR (movement_type IN ('ISSUE', 'SCRAP', 'DISPATCH') AND qty < 0)"
    " OR (movement_type = 'COST_ADJUST' AND qty = 0)"
    " OR (movement_type = 'ADJUST' AND qty <> 0)"
    " OR movement_type = 'REVERSAL'"
)


class StockAdjustment(Base):
    """Source document for opening stock and stock-take corrections."""

    __tablename__ = "stock_adjustment"
    __table_args__ = (CheckConstraint("kind IN ('OPENING', 'ADJUST')", name="kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    adj_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lines: Mapped[list["StockAdjustmentLine"]] = relationship(order_by="StockAdjustmentLine.id")


class StockAdjustmentLine(Base):
    __tablename__ = "stock_adjustment_line"

    id: Mapped[int] = mapped_column(primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(ForeignKey("stock_adjustment.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lot.id"))  # None: FIFO lots
    qty: Mapped[Decimal] = mapped_column(QTY)  # signed, base unit
    value_paise: Mapped[int | None] = mapped_column(BigInteger)  # given for inflows only


class StockLot(Base):
    """A batch: where it came from and when it expires. For traceability; cost is WAC per item."""

    __tablename__ = "stock_lot"
    __table_args__ = (
        UniqueConstraint("item_id", "lot_no"),
        UniqueConstraint("id", "item_id"),  # target of stock_movement's composite foreign key
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    lot_no: Mapped[str] = mapped_column(String(40))
    mfg_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # FIFO order
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StockMovement(Base):
    __tablename__ = "stock_movement"
    __table_args__ = (
        ForeignKeyConstraint(["lot_id", "item_id"], ["stock_lot.id", "stock_lot.item_id"]),
        CheckConstraint(
            "movement_type IN (" + ", ".join(f"'{t.value}'" for t in MovementType) + ")",
            name="movement_type",
        ),
        CheckConstraint(SIGN_RULE, name="sign_matches_type"),
        Index("ix_stock_movement_item_date", "item_id", "movement_date"),
        Index("ix_stock_movement_lot", "lot_id"),
        Index("ix_stock_movement_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    lot_id: Mapped[int]
    qty: Mapped[Decimal] = mapped_column(QTY)  # signed, base unit
    value_paise: Mapped[int] = mapped_column(BigInteger)  # signed
    movement_type: Mapped[str] = mapped_column(String(12))
    movement_date: Mapped[date] = mapped_column(Date)  # business date of the source document
    source_type: Mapped[str] = mapped_column(String(30))
    source_id: Mapped[int] = mapped_column(BigInteger)
    source_line_id: Mapped[int] = mapped_column(BigInteger)
    reverses_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("stock_movement.id"),
        unique=True,  # a movement is reversed once
    )
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    posted_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
