from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.payments import service
from app.payments.schemas import CustomerOutstanding, PaymentCreate, PaymentOut

router = APIRouter(tags=["payments"])

# Spec section 2: the admin records payments; auditor and owner read reports. Production and
# salesmen never see payments.
Cashier = Annotated[AppUser, Depends(require_roles(Role.ADMIN))]
PaymentReader = Annotated[AppUser, Depends(require_roles(Role.ADMIN, Role.AUDITOR, Role.OWNER))]


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(body: PaymentCreate, db: DbSession, user: Cashier) -> PaymentOut:
    return service.record_payment(db, body, user)


@router.get("/customers/{customer_id}/outstanding", response_model=CustomerOutstanding)
def customer_outstanding(
    customer_id: int, db: DbSession, user: PaymentReader
) -> CustomerOutstanding:
    return service.customer_outstanding(db, customer_id)
