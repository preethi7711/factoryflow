from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.purchasing import service
from app.purchasing.schemas import PurchaseCreate, PurchaseOut

router = APIRouter(prefix="/purchases", tags=["purchasing"])

# Spec section 2: the production supervisor records purchases (goods received).
Buyer = Annotated[AppUser, Depends(require_roles(Role.PRODUCTION))]
Reader = Annotated[
    AppUser, Depends(require_roles(Role.PRODUCTION, Role.ADMIN, Role.AUDITOR, Role.OWNER))
]


@router.post("", response_model=PurchaseOut, status_code=status.HTTP_201_CREATED)
def create_purchase(body: PurchaseCreate, db: DbSession, user: Buyer) -> PurchaseOut:
    return service.create_purchase(db, body, user)


@router.get("/{purchase_id}", response_model=PurchaseOut)
def get_purchase(purchase_id: int, db: DbSession, user: Reader) -> PurchaseOut:
    return service.get_purchase(db, purchase_id)
