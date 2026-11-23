from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class InvoiceCreate(BaseModel):
    invoice_date: date


class DispatchCreate(BaseModel):
    dispatch_date: date


class CancelCreate(BaseModel):
    cn_date: date
    reason: str | None = Field(default=None, max_length=200)


class InvoiceLineOut(BaseModel):
    id: int
    item_id: int
    item_code: str
    hsn: str | None
    qty: Decimal
    uom: str
    unit_price_paise: int
    gst_rate_bp: int
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int


class InvoiceOut(BaseModel):
    id: int
    invoice_no: str
    order_id: int
    customer_id: int
    customer_code: str
    customer_gstin: str | None
    fy: str
    seq: int
    invoice_date: date
    place_of_supply_state: str
    supply_type: str  # INTRA or INTER
    status: str
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int
    lines: list[InvoiceLineOut]


class CreditNoteOut(BaseModel):
    id: int
    cn_no: str | None
    invoice_id: int
    cn_date: date
    reason: str | None
    taxable_paise: int
    cgst_paise: int
    sgst_paise: int
    igst_paise: int
    total_paise: int


class CancelResult(BaseModel):
    invoice: InvoiceOut
    credit_note: CreditNoteOut
