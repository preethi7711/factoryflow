"""Master data: company, items (+ pack units), BOMs, customers, suppliers.

The price list is item.sale_price_paise (one current price per product): the server
re-prices every order from it, so a salesman's phone can't send its own price.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import QTY, Base


class ItemKind(StrEnum):
    RAW = "RAW"
    PACKAGING = "PACKAGING"
    FG = "FG"  # finished goods


class CompanySettings(Base):
    """Exactly one row. GST type is decided against this state, never a hard-coded '33'."""

    __tablename__ = "company_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(Text)
    invoice_prefix: Mapped[str] = mapped_column(String(10), default="FF")


class Item(Base):
    __tablename__ = "item"
    __table_args__ = (
        CheckConstraint("kind IN ('RAW', 'PACKAGING', 'FG')", name="kind"),
        CheckConstraint("base_uom IN ('g', 'ml', 'pcs', 'pkt')", name="base_uom"),
        CheckConstraint("gst_rate_bp BETWEEN 0 AND 10000", name="gst_rate_bp"),
        CheckConstraint("kind <> 'FG' OR sale_price_paise IS NOT NULL", name="fg_has_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10))
    base_uom: Mapped[str] = mapped_column(String(8))
    hsn: Mapped[str | None] = mapped_column(String(8))
    gst_rate_bp: Mapped[int] = mapped_column(default=0)
    sale_price_paise: Mapped[int | None] = mapped_column(BigInteger)
    pack_size: Mapped[str | None] = mapped_column(String(40))
    variance_tol_bp: Mapped[int] = mapped_column(default=300)
    shelf_life_days: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    units: Mapped[list["ItemUnit"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="ItemUnit.uom"
    )

    def pack_units(self) -> dict[str, Decimal]:
        """Item-specific packs for core.units.to_base, e.g. {"carton": Decimal(20)}."""
        return {u.uom: u.factor for u in self.units}


class ItemUnit(Base):
    """An item-specific pack: 1 <uom> = <factor> base units (Murukku: 1 carton = 20 pkt)."""

    __tablename__ = "item_unit"
    __table_args__ = (
        UniqueConstraint("item_id", "uom"),
        CheckConstraint("factor > 0", name="factor_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    uom: Mapped[str] = mapped_column(String(16))
    factor: Mapped[Decimal] = mapped_column(QTY)

    item: Mapped[Item] = relationship(back_populates="units")


class Bom(Base):
    """Bill of materials for one batch of a finished good, in base units."""

    __tablename__ = "bom"
    __table_args__ = (
        CheckConstraint("output_qty > 0", name="output_positive"),
        # At most one active BOM per product, so a run can never pick the wrong recipe.
        Index(
            "uq_bom_one_active_per_item", "item_id", unique=True, postgresql_where=text("is_active")
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    output_qty: Mapped[Decimal] = mapped_column(QTY)  # expected good output per batch
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[Item] = relationship()
    lines: Mapped[list["BomLine"]] = relationship(
        back_populates="bom", cascade="all, delete-orphan", order_by="BomLine.id"
    )


class BomLine(Base):
    __tablename__ = "bom_line"
    __table_args__ = (
        UniqueConstraint("bom_id", "item_id"),
        CheckConstraint("qty > 0", name="qty_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("bom.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.id"))
    qty: Mapped[Decimal] = mapped_column(QTY)  # per batch, in the ingredient's base unit

    bom: Mapped[Bom] = relationship(back_populates="lines")
    item: Mapped[Item] = relationship()


class Customer(Base):
    __tablename__ = "customer"
    __table_args__ = (CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))  # place of supply for GST
    address: Mapped[str | None] = mapped_column(Text)
    salesman_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))  # assigned rep
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Supplier(Base):
    __tablename__ = "supplier"
    __table_args__ = (CheckConstraint("state_code ~ '^[0-9]{2}$'", name="state_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    gstin: Mapped[str | None] = mapped_column(String(15))
    state_code: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
