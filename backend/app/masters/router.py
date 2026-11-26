from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.masters import service
from app.masters.models import Item, ItemKind
from app.masters.schemas import (
    BomCreate,
    BomOut,
    CustomerCreate,
    CustomerCreated,
    CustomerOut,
    CustomerUpdate,
    CustomerUpdated,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    PriceListRow,
    SupplierCreate,
    SupplierCreated,
    SupplierOut,
    SupplierUpdate,
    SupplierUpdated,
)

router = APIRouter(tags=["masters"])

# Who may call what (spec section 2). Production never sees sales data such as customers.
MasterReader = Annotated[
    AppUser, Depends(require_roles(Role.ADMIN, Role.PRODUCTION, Role.AUDITOR, Role.OWNER))
]
SalesReader = Annotated[
    AppUser, Depends(require_roles(Role.SALESMAN, Role.ADMIN, Role.AUDITOR, Role.OWNER))
]
Admin = Annotated[AppUser, Depends(require_roles(Role.ADMIN))]


@router.get("/items", response_model=list[ItemOut])
def list_items(
    db: DbSession,
    user: MasterReader,
    code: str | None = None,
    kind: ItemKind | None = None,
    include_inactive: bool = False,
) -> list[Item]:
    return service.list_items(db, code=code, kind=kind, include_inactive=include_inactive)


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemCreate, db: DbSession, user: Admin) -> Item:
    return service.create_item(db, body, user)


@router.patch("/items/{item_id}", response_model=ItemOut)
def update_item(item_id: int, body: ItemUpdate, db: DbSession, user: Admin) -> Item:
    return service.update_item(db, item_id, body, user)


@router.get("/price-list", response_model=list[PriceListRow])
def price_list(db: DbSession, user: SalesReader) -> list[PriceListRow]:
    return [
        PriceListRow(
            item_id=i.id,
            code=i.code,
            name=i.name,
            pack_size=i.pack_size,
            hsn=i.hsn,
            gst_rate_bp=i.gst_rate_bp,
            sale_price_paise=i.sale_price_paise or 0,
            uom=i.base_uom,
        )
        for i in service.price_list(db)
    ]


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    db: DbSession, user: SalesReader, code: str | None = None, include_inactive: bool = False
) -> list:
    return service.list_customers(db, code=code, include_inactive=include_inactive)


@router.post("/customers", response_model=CustomerCreated, status_code=status.HTTP_201_CREATED)
def create_customer(body: CustomerCreate, db: DbSession, user: Admin) -> CustomerCreated:
    customer, warnings = service.create_customer(db, body, user)
    return CustomerCreated(**CustomerOut.model_validate(customer).model_dump(), warnings=warnings)


@router.patch("/customers/{customer_id}", response_model=CustomerUpdated)
def update_customer(
    customer_id: int, body: CustomerUpdate, db: DbSession, user: Admin
) -> CustomerUpdated:
    customer, warnings = service.update_customer(db, customer_id, body, user)
    return CustomerUpdated(**CustomerOut.model_validate(customer).model_dump(), warnings=warnings)


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    db: DbSession, user: MasterReader, code: str | None = None, include_inactive: bool = False
) -> list:
    return service.list_suppliers(db, code=code, include_inactive=include_inactive)


@router.post("/suppliers", response_model=SupplierCreated, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierCreate, db: DbSession, user: Admin) -> SupplierCreated:
    supplier, warnings = service.create_supplier(db, body, user)
    return SupplierCreated(**SupplierOut.model_validate(supplier).model_dump(), warnings=warnings)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierUpdated)
def update_supplier(
    supplier_id: int, body: SupplierUpdate, db: DbSession, user: Admin
) -> SupplierUpdated:
    supplier, warnings = service.update_supplier(db, supplier_id, body, user)
    return SupplierUpdated(**SupplierOut.model_validate(supplier).model_dump(), warnings=warnings)


@router.get("/boms", response_model=list[BomOut])
def list_boms(db: DbSession, user: MasterReader, item_id: int | None = None) -> list[BomOut]:
    return service.list_boms(db, item_id=item_id)


@router.post("/boms", response_model=BomOut, status_code=status.HTTP_201_CREATED)
def create_bom(body: BomCreate, db: DbSession, user: Admin) -> BomOut:
    return service.create_bom(db, body, user)
