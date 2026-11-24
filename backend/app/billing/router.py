from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.billing import service
from app.billing.schemas import (
    CancelCreate,
    CancelResult,
    DispatchCreate,
    InvoiceCreate,
    InvoiceOut,
)
from app.core.db import DbSession

router = APIRouter(tags=["billing"])

# Spec section 2: the admin raises and cancels invoices and dispatches.
Admin = Annotated[AppUser, Depends(require_roles(Role.ADMIN))]
InvoiceReader = Annotated[AppUser, Depends(require_roles(Role.ADMIN, Role.AUDITOR, Role.OWNER))]


@router.post(
    "/orders/{order_id}/invoice", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED
)
def create_invoice(order_id: int, body: InvoiceCreate, db: DbSession, user: Admin) -> InvoiceOut:
    return service.create_invoice(db, order_id, body, user)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(invoice_id: int, db: DbSession, user: InvoiceReader) -> InvoiceOut:
    return service.get_invoice(db, invoice_id)


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, db: DbSession, user: InvoiceReader) -> Response:
    body, name = service.invoice_pdf(db, invoice_id)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{name}.pdf"'},
    )


@router.post("/invoices/{invoice_id}/dispatch", response_model=InvoiceOut)
def dispatch_invoice(
    invoice_id: int, body: DispatchCreate, db: DbSession, user: Admin
) -> InvoiceOut:
    return service.dispatch_invoice(db, invoice_id, body, user)


@router.post("/invoices/{invoice_id}/cancel", response_model=CancelResult)
def cancel_invoice(invoice_id: int, body: CancelCreate, db: DbSession, user: Admin) -> CancelResult:
    return service.cancel_invoice(db, invoice_id, body, user)
