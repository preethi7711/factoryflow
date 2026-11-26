from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.core.errors import AppError
from app.payments import service
from app.payments.schemas import CustomerOutstanding, PaymentCreate, PaymentOut

router = APIRouter(tags=["payments"])

# Spec section 2: the admin records payments; auditor and owner read reports. Production and
# salesmen never see payments.
Cashier = Annotated[AppUser, Depends(require_roles(Role.ADMIN))]
PaymentReader = Annotated[AppUser, Depends(require_roles(Role.ADMIN, Role.AUDITOR, Role.OWNER))]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(
    body: PaymentCreate, db: DbSession, user: Cashier, idempotency_key: IdemKey = None
) -> PaymentOut:
    # Payments can't drift money on their own (over-allocation is capped at the invoice total), but
    # a retry without this key would still post a second receipt and an auditor would see two
    # transactions for one real deposit. Make the key mandatory, the same shape as orders use.
    if not idempotency_key:
        raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED", "send an Idempotency-Key header")
    return service.record_payment(db, idempotency_key, body, user)


@router.get("/customers/{customer_id}/outstanding", response_model=CustomerOutstanding)
def customer_outstanding(
    customer_id: int, db: DbSession, user: PaymentReader
) -> CustomerOutstanding:
    return service.customer_outstanding(db, customer_id)
