"""Sales orders: idempotent placement, admin approval with a stock-cover check, and a tax preview.

Stock never moves here. Placing an order records intent; approving it reserves finished goods
logically (checks there is cover) but posts nothing. The goods leave only on dispatch (billing).

One transaction per public write: the order, its idempotency row and its audit row commit together.
"""

import hashlib
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import AppUser, Role
from app.core import gst
from app.core.clock import now_ist
from app.core.errors import AppError, not_found
from app.core.wac import InsufficientStockError
from app.inventory import service as inventory
from app.masters import service as masters
from app.masters.models import ItemKind
from app.sales.models import (
    RESERVED_STATUSES,
    IdempotencyKey,
    OrderLine,
    OrderStatus,
    SalesOrder,
)
from app.sales.schemas import OrderCreate, OrderLineOut, OrderOut, TaxPreview

ORDER_ROUTE = "POST /orders"


# ---- reading / shaping ---------------------------------------------------------------


def _out(db: Session, order: SalesOrder) -> OrderOut:
    lines: list[OrderLineOut] = []
    taxable = 0
    for line in order.lines:
        line_taxable = gst.line_taxable_paise(line.qty, line.unit_price_paise)
        taxable += line_taxable
        lines.append(
            OrderLineOut(
                id=line.id,
                item_id=line.item_id,
                item_code=masters.get_item(db, line.item_id).code,
                qty=line.qty,
                uom=line.uom,
                unit_price_paise=line.unit_price_paise,
                gst_rate_bp=line.gst_rate_bp,
                taxable_paise=line_taxable,
            )
        )
    return OrderOut(
        id=order.id,
        client_uuid=order.client_uuid,
        customer_id=order.customer_id,
        customer_code=masters.get_customer(db, order.customer_id).code,
        salesman_id=order.salesman_id,
        order_date=order.order_date,
        status=order.status,
        taxable_paise=taxable,
        lines=lines,
    )


def _get(db: Session, order_id: int, *, lock: bool = False) -> SalesOrder:
    q = select(SalesOrder).where(SalesOrder.id == order_id)
    if lock:
        q = q.with_for_update()  # a concurrent approve/invoice/dispatch of this order waits here
    order = db.scalar(q)
    if order is None:
        raise not_found("order", order_id)
    return order


def _may_read(user: AppUser, order: SalesOrder) -> None:
    """A salesman sees only the orders they placed; other roles already passed require_roles."""
    if user.role == Role.SALESMAN and order.salesman_id != user.id:
        raise AppError(403, "FORBIDDEN", "this order belongs to another salesman")


def get_order(db: Session, order_id: int, user: AppUser) -> OrderOut:
    order = _get(db, order_id)
    _may_read(user, order)
    return _out(db, order)


def list_orders(db: Session, user: AppUser) -> list[OrderOut]:
    q = select(SalesOrder).order_by(SalesOrder.id)
    if user.role == Role.SALESMAN:
        q = q.where(SalesOrder.salesman_id == user.id)
    return [_out(db, order) for order in db.scalars(q)]


# ---- idempotency ---------------------------------------------------------------------


def _request_hash(data: OrderCreate) -> str:
    """A stable fingerprint of the request body. Two requests that parse to the same order
    (e.g. '2 cartons' and '40 pkt' both normalise the same) share a hash and so replay as one."""
    return hashlib.sha256(data.model_dump_json().encode()).hexdigest()


def _replay(existing: IdempotencyKey, request_hash: str) -> OrderOut:
    if existing.route != ORDER_ROUTE or existing.request_hash != request_hash:
        raise AppError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "this Idempotency-Key was already used for a different request",
        )
    return OrderOut.model_validate(existing.response_json)


# ---- writing -------------------------------------------------------------------------


def create_order(db: Session, key: str, data: OrderCreate, user: AppUser) -> OrderOut:
    """Place an order. The server prices every line from the price list, so the client's phone
    can't set its own price. A replayed Idempotency-Key returns the first result, not a copy."""
    request_hash = _request_hash(data)
    existing = db.get(IdempotencyKey, key)
    if existing is not None:
        return _replay(existing, request_hash)

    customer = masters.get_customer(db, data.customer_id)
    if user.role == Role.SALESMAN and customer.salesman_id != user.id:
        raise AppError(403, "FORBIDDEN", f"{customer.code} is not your customer")

    order = SalesOrder(
        client_uuid=key,
        customer_id=customer.id,
        salesman_id=user.id,
        order_date=data.order_date,
        status=OrderStatus.PENDING.value,
        created_by=user.id,
    )
    db.add(order)
    db.flush()
    seen: set[int] = set()
    for line_in in data.lines:
        item = masters.get_item(db, line_in.item_id)
        if item.kind != ItemKind.FG:
            raise AppError(422, "NOT_SELLABLE", f"{item.code} is not a finished good")
        if item.sale_price_paise is None:
            raise AppError(422, "NO_PRICE", f"{item.code} has no sale price")
        if item.id in seen:
            raise AppError(422, "DUPLICATE_LINE", f"{item.code} is listed twice")
        seen.add(item.id)
        db.add(
            OrderLine(
                order_id=order.id,
                item_id=item.id,
                qty=masters.base_qty(line_in.qty, line_in.uom, item),
                uom=item.base_uom,
                unit_price_paise=item.sale_price_paise,  # priced by the server, from the price list
                gst_rate_bp=item.gst_rate_bp,
            )
        )
    db.flush()
    db.refresh(order)  # load the lines just inserted
    out = _out(db, order)
    db.add(
        IdempotencyKey(
            key=key,
            user_id=user.id,
            route=ORDER_ROUTE,
            request_hash=request_hash,
            status_code=201,
            response_json=out.model_dump(mode="json"),
        )
    )
    audit.record(
        db,
        entity="sales_order",
        entity_id=order.id,
        action="CREATE",
        user_id=user.id,
        after=out.model_dump(mode="json"),
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request with the same key committed first (UNIQUE on the key / client_uuid).
        # Replay its stored result instead of failing the double-tap.
        db.rollback()
        winner = db.get(IdempotencyKey, key)
        if winner is None:
            raise
        return _replay(winner, request_hash)
    return out


def _available(db: Session, item_id: int) -> Decimal:
    """Finished goods a new order may take = on hand (SUM of the ledger) minus what approved-but-
    undispatched orders have already reserved. Dispatched orders are not subtracted: their stock
    has physically left the ledger already, so counting them too would double-count."""
    on_hand, _ = inventory.balance(db, item_id)
    reserved = db.scalar(
        select(func.coalesce(func.sum(OrderLine.qty), 0))
        .join(SalesOrder, SalesOrder.id == OrderLine.order_id)
        .where(OrderLine.item_id == item_id, SalesOrder.status.in_(RESERVED_STATUSES))
    )
    return on_hand - reserved


def approve_order(db: Session, order_id: int, user: AppUser) -> OrderOut:
    """Admin approval with a stock-cover check. Over-approval raises INSUFFICIENT_STOCK (409)
    with requested / available / shortage, so the admin can approve a partial qty or hold it."""
    order = _get(db, order_id, lock=True)
    if order.status != OrderStatus.PENDING.value:
        raise AppError(409, "ORDER_NOT_PENDING", f"order {order_id} is {order.status}, not PENDING")
    before = _out(db, order).model_dump(mode="json")
    # Lock the items so the check and the status change can't race a dispatch or another approval:
    # anything that changes these balances takes the same lock and waits (masters.lock_items).
    masters.lock_items(db, (line.item_id for line in order.lines))
    for line in order.lines:
        available = _available(db, line.item_id)
        if line.qty > available:
            item = masters.get_item(db, line.item_id)
            raise InsufficientStockError(line.qty, available, item=item.code)
    order.status = OrderStatus.APPROVED.value
    order.approved_by = user.id
    order.approved_at = now_ist()
    db.flush()
    out = _out(db, order)
    audit.record(
        db,
        entity="sales_order",
        entity_id=order.id,
        action="APPROVE",
        user_id=user.id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


def tax_preview(db: Session, order_id: int, user: AppUser) -> TaxPreview:
    """What the order would be taxed if invoiced now: CGST+SGST or IGST by place of supply,
    computed per line and summed. Creates nothing."""
    order = _get(db, order_id)
    _may_read(user, order)
    customer = masters.get_customer(db, order.customer_id)
    supply = gst.supply_type(masters.get_company(db).state_code, customer.state_code)
    taxes = [
        gst.line_tax(
            gst.line_taxable_paise(line.qty, line.unit_price_paise), line.gst_rate_bp, supply
        )
        for line in order.lines
    ]
    totals = gst.invoice_totals(taxes)
    return TaxPreview(
        supply_type=supply.value,
        taxable_paise=totals.taxable_paise,
        cgst_paise=totals.cgst_paise,
        sgst_paise=totals.sgst_paise,
        igst_paise=totals.igst_paise,
        total_paise=totals.total_paise,
    )


# ---- for the billing module ----------------------------------------------------------


def load_order(db: Session, order_id: int, *, lock: bool = False) -> SalesOrder:
    """The order model, for billing to invoice or dispatch. Billing reads it through this
    service; it never touches the sales tables itself."""
    return _get(db, order_id, lock=lock)


def set_status(db: Session, order: SalesOrder, to: OrderStatus, user: AppUser) -> None:
    """Record an order's state change (invariant 8). Flushes inside the caller's transaction;
    the caller commits the whole event (order, invoice/dispatch, movements, audit) together."""
    before = order.status
    order.status = to.value
    db.flush()
    audit.record(
        db,
        entity="sales_order",
        entity_id=order.id,
        action=f"STATUS_{to.value}",
        user_id=user.id,
        before={"status": before},
        after={"status": to.value},
    )
