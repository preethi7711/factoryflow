from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.core.errors import AppError
from app.sales import service
from app.sales.schemas import OrderCreate, OrderOut, TaxPreview

router = APIRouter(prefix="/orders", tags=["sales"])

# Spec section 2: a salesman places and reads their own orders; the admin approves.
Placer = Annotated[AppUser, Depends(require_roles(Role.SALESMAN, Role.ADMIN))]
OrderReader = Annotated[
    AppUser, Depends(require_roles(Role.SALESMAN, Role.ADMIN, Role.AUDITOR, Role.OWNER))
]
Approver = Annotated[AppUser, Depends(require_roles(Role.ADMIN))]

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderCreate, db: DbSession, user: Placer, idempotency_key: IdempotencyKey = None
) -> OrderOut:
    # The order's client_uuid is this key (UNIQUE), so an offline queue that sends the same
    # order twice lands it once. We require it rather than inventing one server-side.
    if not idempotency_key:
        raise AppError(400, "IDEMPOTENCY_KEY_REQUIRED", "send an Idempotency-Key header")
    return service.create_order(db, idempotency_key, body, user)


@router.get("", response_model=list[OrderOut])
def list_orders(db: DbSession, user: OrderReader) -> list[OrderOut]:
    return service.list_orders(db, user)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: DbSession, user: OrderReader) -> OrderOut:
    return service.get_order(db, order_id, user)


@router.post("/{order_id}/approve", response_model=OrderOut)
def approve_order(order_id: int, db: DbSession, user: Approver) -> OrderOut:
    return service.approve_order(db, order_id, user)


@router.get("/{order_id}/tax-preview", response_model=TaxPreview)
def tax_preview(order_id: int, db: DbSession, user: OrderReader) -> TaxPreview:
    return service.tax_preview(db, order_id, user)
