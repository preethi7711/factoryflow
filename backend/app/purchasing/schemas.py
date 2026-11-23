from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.types import BasisPoints, Paise, PositiveQty


class PurchaseLineIn(BaseModel):
    item_id: int
    qty: PositiveQty
    uom: str  # any unit of the item's dimension: 60 kg of flour, stored as 60000 g
    rate_paise: Paise  # per `uom`, before tax (A15)
    gst_rate_bp: BasisPoints | None = None  # input GST rate; defaults to the item's rate
    expiry_date: date | None = None


class PurchaseCreate(BaseModel):
    supplier_id: int
    purchase_date: date
    bill_no: str | None = Field(default=None, max_length=40)
    lines: list[PurchaseLineIn] = Field(min_length=1)


class PurchaseLineOut(BaseModel):
    id: int
    item_id: int
    item_code: str
    qty: Decimal
    uom: str
    entered_qty: Decimal
    entered_uom: str
    rate_paise: int
    value_paise: int
    gst_rate_bp: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    lot_id: int
    lot_no: str


class PurchaseOut(BaseModel):
    id: int
    supplier_id: int
    supplier_code: str
    purchase_date: date
    bill_no: str | None
    supply_type: str
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    lines: list[PurchaseLineOut]
