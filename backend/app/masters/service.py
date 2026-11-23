from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import service as audit
from app.auth.models import AppUser, Role
from app.auth.service import get_active_user
from app.core.errors import AppError, not_found
from app.core.gst import gstin_warnings
from app.core.units import UnitError, check_qty_scale, to_base
from app.masters.models import (
    Bom,
    BomLine,
    CompanySettings,
    Customer,
    Item,
    ItemKind,
    ItemUnit,
    Supplier,
)
from app.masters.schemas import (
    BomCreate,
    BomLineOut,
    BomOut,
    CustomerCreate,
    CustomerOut,
    ItemCreate,
    ItemOut,
    SupplierCreate,
    SupplierOut,
)


def _ensure_new_code(db: Session, model: type[Item | Customer | Supplier | Bom], code: str) -> None:
    if db.scalar(select(model.id).where(model.code == code)) is not None:
        raise AppError(409, "DUPLICATE_CODE", f"{model.__tablename__} code {code} already exists")


def base_qty(qty: Decimal, uom: str, item: Item) -> Decimal:
    """User input -> the item's base unit, with a clean 422 for an impossible quantity."""
    try:
        return check_qty_scale(to_base(qty, uom, item.base_uom, item.pack_units()))
    except UnitError:
        raise  # has its own handler (422 UNIT_ERROR)
    except ValueError as exc:
        raise AppError(422, "INVALID_QUANTITY", str(exc)) from None


def get_company(db: Session) -> CompanySettings:
    company = db.get(CompanySettings, 1)
    if company is None:
        raise AppError(500, "NOT_CONFIGURED", "company settings are missing; run the seed")
    return company


# ---- items ---------------------------------------------------------------------------


def list_items(db: Session, *, code: str | None = None, kind: str | None = None) -> list[Item]:
    q = select(Item).options(selectinload(Item.units)).order_by(Item.code)
    if code:
        q = q.where(Item.code == code)
    if kind:
        q = q.where(Item.kind == kind)
    return list(db.scalars(q))


def get_item(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise not_found("item", item_id)
    return item


def lock_items(db: Session, item_ids: Iterable[int]) -> dict[int, Item]:
    """SELECT ... FOR UPDATE on the item rows, always in id order.

    Two transactions posting stock for the same item then wait for each other instead of
    both reading the old balance, and the fixed order means they can't deadlock.
    """
    ids = sorted(set(item_ids))
    rows = db.scalars(select(Item).where(Item.id.in_(ids)).order_by(Item.id).with_for_update())
    found = {item.id: item for item in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise not_found("item", missing[0])
    return found


def create_item(db: Session, data: ItemCreate, user: AppUser) -> Item:
    _ensure_new_code(db, Item, data.code)
    item = Item(
        code=data.code,
        name=data.name,
        kind=data.kind.value,
        base_uom=data.base_uom,
        hsn=data.hsn,
        gst_rate_bp=data.gst_rate_bp,
        sale_price_paise=data.sale_price_paise,
        pack_size=data.pack_size,
        variance_tol_bp=data.variance_tol_bp,
        shelf_life_days=data.shelf_life_days,
        units=[ItemUnit(uom=u.uom, factor=check_qty_scale(u.factor)) for u in data.units],
    )
    db.add(item)
    db.flush()
    after = ItemOut.model_validate(item).model_dump(mode="json")
    audit.record(
        db, entity="item", entity_id=item.id, action="CREATE", user_id=user.id, after=after
    )
    db.commit()
    return item


def price_list(db: Session) -> list[Item]:
    return list(db.scalars(select(Item).where(Item.kind == ItemKind.FG).order_by(Item.code)))


# ---- customers and suppliers ---------------------------------------------------------


def list_customers(db: Session, *, code: str | None = None) -> list[Customer]:
    q = select(Customer).order_by(Customer.code)
    if code:
        q = q.where(Customer.code == code)
    return list(db.scalars(q))


def create_customer(db: Session, data: CustomerCreate, user: AppUser) -> tuple[Customer, list[str]]:
    _ensure_new_code(db, Customer, data.code)
    if data.salesman_id is not None:
        rep = get_active_user(db, data.salesman_id)
        if rep is None or rep.role != Role.SALESMAN:
            raise AppError(422, "INVALID_SALESMAN", f"user {data.salesman_id} is not a salesman")
    customer = Customer(**data.model_dump())
    db.add(customer)
    db.flush()
    after = CustomerOut.model_validate(customer).model_dump(mode="json")
    audit.record(
        db, entity="customer", entity_id=customer.id, action="CREATE", user_id=user.id, after=after
    )
    db.commit()
    return customer, gstin_warnings(data.gstin, data.state_code)


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise not_found("supplier", supplier_id)
    return supplier


def list_suppliers(db: Session, *, code: str | None = None) -> list[Supplier]:
    q = select(Supplier).order_by(Supplier.code)
    if code:
        q = q.where(Supplier.code == code)
    return list(db.scalars(q))


def create_supplier(db: Session, data: SupplierCreate, user: AppUser) -> tuple[Supplier, list[str]]:
    _ensure_new_code(db, Supplier, data.code)
    supplier = Supplier(**data.model_dump())
    db.add(supplier)
    db.flush()
    after = SupplierOut.model_validate(supplier).model_dump(mode="json")
    audit.record(
        db, entity="supplier", entity_id=supplier.id, action="CREATE", user_id=user.id, after=after
    )
    db.commit()
    return supplier, gstin_warnings(data.gstin, data.state_code)


# ---- BOMs ----------------------------------------------------------------------------


def _bom_out(bom: Bom) -> BomOut:
    return BomOut(
        id=bom.id,
        code=bom.code,
        item_id=bom.item_id,
        item_code=bom.item.code,
        output_qty=bom.output_qty,
        output_uom=bom.item.base_uom,
        is_active=bom.is_active,
        lines=[
            BomLineOut(
                item_id=line.item_id, item_code=line.item.code, qty=line.qty, uom=line.item.base_uom
            )
            for line in bom.lines
        ],
    )


def get_bom(db: Session, bom_id: int) -> Bom:
    """The BOM with its product and lines loaded (each line's ingredient too)."""
    q = (
        select(Bom)
        .where(Bom.id == bom_id)
        .options(selectinload(Bom.item), selectinload(Bom.lines).selectinload(BomLine.item))
    )
    bom = db.scalar(q)
    if bom is None:
        raise not_found("BOM", bom_id)
    return bom


def list_boms(db: Session, *, item_id: int | None = None) -> list[BomOut]:
    """Active BOMs only: an inactive recipe must never be picked for a new run."""
    q = (
        select(Bom)
        .where(Bom.is_active)
        .options(selectinload(Bom.item), selectinload(Bom.lines).selectinload(BomLine.item))
        .order_by(Bom.code)
    )
    if item_id is not None:
        q = q.where(Bom.item_id == item_id)
    return [_bom_out(bom) for bom in db.scalars(q)]


def create_bom(db: Session, data: BomCreate, user: AppUser) -> BomOut:
    _ensure_new_code(db, Bom, data.code)
    product = get_item(db, data.item_id)
    if product.kind != ItemKind.FG:
        raise AppError(422, "NOT_A_FINISHED_GOOD", f"{product.code} is not a finished good")
    if db.scalar(select(Bom.id).where(Bom.item_id == product.id, Bom.is_active)) is not None:
        raise AppError(409, "BOM_EXISTS", f"{product.code} already has an active BOM")
    lines: list[BomLine] = []
    for line in data.lines:
        ingredient = get_item(db, line.item_id)
        if ingredient.kind == ItemKind.FG:
            raise AppError(422, "INVALID_BOM_LINE", f"{ingredient.code} is a finished good")
        if any(existing.item_id == ingredient.id for existing in lines):
            raise AppError(422, "INVALID_BOM_LINE", f"{ingredient.code} is listed twice")
        lines.append(BomLine(item_id=ingredient.id, qty=base_qty(line.qty, line.uom, ingredient)))
    bom = Bom(
        code=data.code,
        item_id=product.id,
        output_qty=base_qty(data.output_qty, data.output_uom, product),
        lines=lines,
    )
    db.add(bom)
    db.flush()
    out = _bom_out(bom)
    audit.record(
        db,
        entity="bom",
        entity_id=bom.id,
        action="CREATE",
        user_id=user.id,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out
