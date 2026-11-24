"""Imports every module's models, so SQLAlchemy and Alembic see all tables at once."""

from app.audit.models import AuditLog
from app.auth.models import AppUser
from app.billing.models import (
    CreditNote,
    CreditNoteLine,
    Dispatch,
    DispatchLine,
    Invoice,
    InvoiceLine,
    InvoiceSequence,
)
from app.inventory.models import StockAdjustment, StockAdjustmentLine, StockLot, StockMovement
from app.masters.models import Bom, BomLine, CompanySettings, Customer, Item, ItemUnit, Supplier
from app.payments.models import Payment, PaymentAllocation
from app.production.models import ProductionRun, RunConsumption, RunOverhead
from app.purchasing.models import Purchase, PurchaseLine
from app.sales.models import IdempotencyKey, OrderLine, SalesOrder

__all__ = [
    "ProductionRun",
    "Purchase",
    "PurchaseLine",
    "RunConsumption",
    "RunOverhead",
    "AppUser",
    "AuditLog",
    "Bom",
    "BomLine",
    "CompanySettings",
    "CreditNote",
    "CreditNoteLine",
    "Customer",
    "Dispatch",
    "DispatchLine",
    "IdempotencyKey",
    "Invoice",
    "InvoiceLine",
    "InvoiceSequence",
    "Item",
    "ItemUnit",
    "OrderLine",
    "Payment",
    "PaymentAllocation",
    "SalesOrder",
    "StockAdjustment",
    "StockAdjustmentLine",
    "StockLot",
    "StockMovement",
    "Supplier",
]
