from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.types import PositiveQty


class OrderLineIn(BaseModel):
    item_id: int
    qty: PositiveQty
    uom: str  # any unit of the item's dimension; 2 cartons of Murukku = 40 pkt


class OrderCreate(BaseModel):
    customer_id: int
    order_date: date
    lines: list[OrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    id: int
    item_id: int
    item_code: str
    qty: Decimal
    uom: str
    unit_price_paise: int  # server-priced from the price list, not the client
    gst_rate_bp: int
    taxable_paise: int  # qty x unit price


class OrderOut(BaseModel):
    id: int
    client_uuid: str
    customer_id: int
    customer_code: str
    salesman_id: int
    order_date: date
    status: str
    taxable_paise: int  # sum of the lines, before tax
    lines: list[OrderLineOut]


class TaxPreview(BaseModel):
    """What the order would be taxed if invoiced now; computed without creating anything."""

    supply_type: str  # INTRA (CGST + SGST) or INTER (IGST), by place of supply
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
