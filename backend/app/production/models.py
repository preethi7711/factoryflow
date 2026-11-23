"""Production runs: planned vs actual consumption, output, overheads.

Actual consumption is NOT stored here: it is read from the ledger (the run's ISSUE movements),
so the run and the ledger can never disagree. The run stores what only it knows: the plan,
the declared good output and damaged quantities (info only; they are part of the issue).

source_line_id of a run's movements: ISSUE -> run_consumption.id, OUTPUT -> production_run.id,
COST_ADJUST -> run_overhead.id.
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


class RunStatus(StrEnum):
    DRAFT = "DRAFT"  # started: raw materials issued
    COMPLETED = "COMPLETED"  # output posted; only overheads may still be added


class OverheadKind(StrEnum):
    LABOUR = "LABOUR"
    GAS_POWER = "GAS_POWER"
    OTHER = "OTHER"


class ProductionRun(Base):
    __tablename__ = "production_run"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'COMPLETED')", name="status"),
        CheckConstraint("batches > 0", name="batches_positive"),
        CheckConstraint(
            "status <> 'COMPLETED' OR (good_qty > 0 AND output_lot_id IS NOT NULL)",
            name="completed_has_output",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("bom.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))  # the finished good
    batches: Mapped[Decimal] = mapped_column(QTY)
    run_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10))
    planned_qty: Mapped[Decimal] = mapped_column(QTY)  # expected good output = BOM output x batches
    good_qty: Mapped[Decimal | None] = mapped_column(QTY)
    output_lot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_lot.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lines: Mapped[list["RunConsumption"]] = relationship(order_by="RunConsumption.id")
    overheads: Mapped[list["RunOverhead"]] = relationship(order_by="RunOverhead.id")

    @property
    def run_no(self) -> str:
        return f"RUN-{self.id:04d}"  # also the output lot number


class RunConsumption(Base):
    """One BOM line of a run: the plan, plus damaged quantity for information."""

    __tablename__ = "run_consumption"
    __table_args__ = (
        UniqueConstraint("run_id", "item_id"),
        CheckConstraint("planned_qty > 0", name="planned_positive"),
        CheckConstraint("damaged_qty >= 0", name="damaged_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("production_run.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    planned_qty: Mapped[Decimal] = mapped_column(QTY)  # BOM qty x batches, base unit
    damaged_qty: Mapped[Decimal] = mapped_column(QTY, default=Decimal(0))  # part of the issue


class RunOverhead(Base):
    __tablename__ = "run_overhead"
    __table_args__ = (
        CheckConstraint("kind IN ('LABOUR', 'GAS_POWER', 'OTHER')", name="kind"),
        CheckConstraint("amount_paise > 0", name="amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("production_run.id"))
    kind: Mapped[str] = mapped_column(String(12))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
