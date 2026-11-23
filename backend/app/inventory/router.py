from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.inventory import service
from app.inventory.schemas import ReconcileOut, StockBalanceOut
from app.masters import service as masters

router = APIRouter(prefix="/stock", tags=["stock"])

StockReader = Annotated[
    AppUser, Depends(require_roles(Role.ADMIN, Role.PRODUCTION, Role.AUDITOR, Role.OWNER))
]
Checker = Annotated[AppUser, Depends(require_roles(Role.ADMIN, Role.AUDITOR, Role.OWNER))]


@router.get("/balance/{item_id}", response_model=StockBalanceOut)
def stock_balance(
    item_id: int, db: DbSession, user: StockReader, as_of: date | None = None
) -> StockBalanceOut:
    item = masters.get_item(db, item_id)
    qty, value = service.balance(db, item.id, as_of=as_of)
    return StockBalanceOut(
        item_id=item.id, item_code=item.code, qty=qty, uom=item.base_uom, value_paise=value
    )


@router.get("/reconcile", response_model=ReconcileOut)
def reconcile(db: DbSession, user: Checker) -> ReconcileOut:
    problems = service.reconcile(db)
    return ReconcileOut(ok=not problems, problems=problems)
