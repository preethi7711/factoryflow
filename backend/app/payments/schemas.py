from datetime import date

from pydantic import BaseModel, Field

from app.core.types import Paise


class PaymentAllocationIn(BaseModel):
    invoice_id: int
    amount_paise: Paise = Field(gt=0)


class PaymentCreate(BaseModel):
    customer_id: int
    payment_date: date
    amount_paise: Paise = Field(gt=0)
    reference: str | None = Field(default=None, max_length=60)
    allocations: list[PaymentAllocationIn] = Field(min_length=1)


class AllocationOut(BaseModel):
    invoice_id: int
    invoice_no: str
    amount_paise: int


class PaymentOut(BaseModel):
    id: int
    customer_id: int
    payment_date: date
    amount_paise: int
    reference: str | None
    allocations: list[AllocationOut]


class InvoiceOutstanding(BaseModel):
    invoice_id: int
    invoice_no: str
    total_paise: int
    paid_paise: int
    outstanding_paise: int


class CustomerOutstanding(BaseModel):
    customer_id: int
    outstanding_paise: int  # sum over non-cancelled invoices of total - paid
    invoices: list[InvoiceOutstanding]  # per-invoice breakdown (those still owing)
