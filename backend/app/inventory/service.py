"""The only code that writes stock_movement (stock-ledger skill, rule 1).

Other modules describe what moved (MovementLine) and call post_movements(); this module
locks, checks, allocates lots, values outflows at WAC and inserts. Nothing else inserts.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.money import round_half_up
from app.core.units import check_qty_scale
from app.core.wac import InsufficientStockError, issue_value
from app.inventory.models import (
    MovementType,
    SourceType,
    StockAdjustment,
    StockAdjustmentLine,
    StockLot,
    StockMovement,
)
from app.masters import service as masters

INFLOWS = frozenset({MovementType.OPENING, MovementType.PURCHASE, MovementType.OUTPUT})
OUTFLOWS = frozenset({MovementType.ISSUE, MovementType.SCRAP, MovementType.DISPATCH})
# Source documents whose table we can check for existence (invariant 6, every table added as built).
KNOWN_SOURCE_TABLES = frozenset(
    {
        SourceType.STOCK_ADJUSTMENT,
        SourceType.PURCHASE,
        SourceType.PRODUCTION_RUN,
        SourceType.DISPATCH,
        SourceType.CREDIT_NOTE,
    }
)


@dataclass(frozen=True)
class MovementLine:
    """One requested stock change, in the item's base unit.

    Inflows (qty > 0) and COST_ADJUST name their lot and value. Outflows (qty < 0) leave
    value_paise empty (valued at WAC here) and may leave lot_id empty (lots taken FIFO here).
    """

    item_id: int
    qty: Decimal
    movement_type: MovementType
    source_line_id: int
    lot_id: int | None = None
    value_paise: int | None = None


@dataclass(frozen=True)
class OpeningLine:
    item_id: int
    qty: Decimal  # base unit, > 0
    value_paise: int


@dataclass(frozen=True)
class ReversalLine:
    """One movement to undo. The reversal mirrors it exactly (same lot, opposite qty and value)."""

    original_id: int  # the stock_movement being reversed
    source_line_id: int  # a line of the reversing document (e.g. credit_note_line.id)


# ---- reading -------------------------------------------------------------------------


def balance(
    db: Session, item_id: int, *, lot_id: int | None = None, as_of: date | None = None
) -> tuple[Decimal, int]:
    """(qty, value_paise) = SUM of the ledger. The only definition of "stock" in the system."""
    q = select(
        func.coalesce(func.sum(StockMovement.qty), 0),
        func.coalesce(func.sum(StockMovement.value_paise), 0),
    ).where(StockMovement.item_id == item_id)
    if lot_id is not None:
        q = q.where(StockMovement.lot_id == lot_id)
    if as_of is not None:
        q = q.where(StockMovement.movement_date <= as_of)
    qty, value = db.execute(q).one()
    return Decimal(qty), int(value)


def source_value(
    db: Session,
    source_type: SourceType,
    source_id: int,
    movement_type: MovementType | None = None,
) -> int:
    """SUM(value_paise) of one document's movements, e.g. a run's ISSUEs (a negative number)."""
    q = select(func.coalesce(func.sum(StockMovement.value_paise), 0)).where(
        StockMovement.source_type == SourceType(source_type).value,
        StockMovement.source_id == source_id,
    )
    if movement_type is not None:
        q = q.where(StockMovement.movement_type == MovementType(movement_type).value)
    return int(db.scalar(q))


def source_qty_by_line(
    db: Session, source_type: SourceType, source_id: int, movement_type: MovementType
) -> dict[int, Decimal]:
    """SUM(qty) per source line of one document, e.g. how much each run line really issued.

    Documents read their actual quantities from here instead of storing a second copy.
    """
    q = (
        select(StockMovement.source_line_id, func.sum(StockMovement.qty))
        .where(
            StockMovement.source_type == SourceType(source_type).value,
            StockMovement.source_id == source_id,
            StockMovement.movement_type == MovementType(movement_type).value,
        )
        .group_by(StockMovement.source_line_id)
    )
    return {line_id: Decimal(qty) for line_id, qty in db.execute(q)}


def get_lot(db: Session, lot_id: int) -> StockLot:
    lot = db.get(StockLot, lot_id)
    if lot is None:
        raise ValueError(f"lot {lot_id} does not exist")
    return lot


def lot_balances(
    db: Session, item_id: int, *, as_of: date | None = None
) -> list[tuple[int, Decimal]]:
    """Lots of an item that still hold stock as of a date, oldest received first."""
    held = func.sum(StockMovement.qty)
    q = (
        select(StockLot.id, held)
        .join(StockMovement, StockMovement.lot_id == StockLot.id)
        .where(StockLot.item_id == item_id)
        .group_by(StockLot.id)
        .having(held > 0)
        .order_by(StockLot.received_at, StockLot.id)
    )
    if as_of is not None:
        q = q.where(StockMovement.movement_date <= as_of)
    return [(lot_id, Decimal(qty)) for lot_id, qty in db.execute(q)]


def allocate(
    db: Session, item_id: int, qty: Decimal, *, as_of: date | None = None
) -> list[tuple[int, Decimal]]:
    """Which lots an outflow of qty comes from: FIFO, oldest received first.

    `as_of` keeps a backdated issue from drawing a lot that had not arrived yet.
    FEFO (stretch goal) = order lot_balances by expiry_date instead; nothing else changes.
    """
    parts: list[tuple[int, Decimal]] = []
    remaining = qty
    for lot_id, held in lot_balances(db, item_id, as_of=as_of):
        take = min(held, remaining)
        parts.append((lot_id, take))
        remaining -= take
        if remaining == 0:
            return parts
    raise InsufficientStockError(qty, qty - remaining)


def reconcile(db: Session) -> list[str]:
    """Checks that must always hold. An empty list means the ledger is healthy.

    1. No item and no lot below zero.
    2. No value left on zero stock (what the anti-drift rule prevents).
    """
    problems: list[str] = []
    qty = func.sum(StockMovement.qty)
    value = func.sum(StockMovement.value_paise)
    per_item = select(StockMovement.item_id, qty, value).group_by(StockMovement.item_id)
    for item_id, q, v in db.execute(per_item.order_by(StockMovement.item_id)):
        code = masters.get_item(db, item_id).code
        if q < 0:
            problems.append(f"{code}: stock is negative ({q})")
        elif q == 0 and v != 0:
            problems.append(f"{code}: {v} paise of value left on zero stock")
        elif v < 0:
            problems.append(f"{code}: stock value is negative ({v} paise)")
    per_lot = (
        select(StockMovement.lot_id, StockMovement.item_id, qty)
        .group_by(StockMovement.lot_id, StockMovement.item_id)
        .having(qty < 0)
    )
    for lot_id, item_id, q in db.execute(per_lot):
        problems.append(f"lot {lot_id} of item {item_id}: stock is negative ({q})")
    return problems


# ---- writing -------------------------------------------------------------------------


def create_lot(
    db: Session,
    *,
    item_id: int,
    lot_no: str,
    received_at: datetime,
    source_type: SourceType,
    source_id: int,
    mfg_date: date | None = None,
    expiry_date: date | None = None,
) -> StockLot:
    lot = StockLot(
        item_id=item_id,
        lot_no=lot_no,
        received_at=received_at,
        source_type=SourceType(source_type).value,
        source_id=source_id,
        mfg_date=mfg_date,
        expiry_date=expiry_date,
    )
    db.add(lot)
    db.flush()
    return lot


def _check(line: MovementLine) -> None:
    t = MovementType(line.movement_type)
    check_qty_scale(line.qty)
    if t is MovementType.REVERSAL:
        raise ValueError("reversals mirror an existing movement; they come with credit notes (P5)")
    if (t in INFLOWS and line.qty <= 0) or (t in OUTFLOWS and line.qty >= 0):
        raise ValueError(f"{t} has the wrong sign: {line.qty}")
    if t is MovementType.COST_ADJUST and line.qty != 0:
        raise ValueError("COST_ADJUST moves value only (qty 0)")
    if t is MovementType.ADJUST and line.qty == 0:
        raise ValueError("ADJUST needs a non-zero quantity")
    if line.qty > 0 or t is MovementType.COST_ADJUST:
        if line.lot_id is None or line.value_paise is None:
            raise ValueError(f"{t} must name its lot and its value")
        if line.qty > 0 and line.value_paise < 0:
            raise ValueError("an inflow can't have a negative value")
        # COST_ADJUST only ever adds cost (overheads). A negative one could drive value below zero.
        if t is MovementType.COST_ADJUST and line.value_paise <= 0:
            raise ValueError("COST_ADJUST must add a positive value")
    elif line.value_paise is not None:
        raise ValueError("outflows are valued at weighted average cost; don't pass value_paise")


def _lot_of_item(db: Session, lot_id: int, item_id: int) -> None:
    lot = db.get(StockLot, lot_id)
    if lot is None or lot.item_id != item_id:
        raise ValueError(f"lot {lot_id} does not belong to item {item_id}")


def _require_source_exists(db: Session, source_type: SourceType, source_id: int) -> None:
    """Every movement must trace to a real document (invariant 6). Callers create and flush the
    document before posting, so this catches a programming error, never normal use."""
    st = SourceType(source_type)
    if st not in KNOWN_SOURCE_TABLES:
        return
    # st.value is an enum-controlled table name, so this interpolation is safe.
    exists = db.execute(text(f"SELECT 1 FROM {st.value} WHERE id = :id"), {"id": source_id}).first()
    if exists is None:
        raise ValueError(f"source document {st.value} #{source_id} does not exist")


def post_movements(
    db: Session,
    *,
    source_type: SourceType,
    source_id: int,
    movement_date: date,
    user_id: int,
    lines: Sequence[MovementLine],
) -> list[StockMovement]:
    """Post one business event's stock changes. The only writer of stock_movement.

    Runs inside the caller's transaction and never commits, so the document, its movements
    and its audit row commit together or not at all. Item rows are locked first, so no other
    transaction can change these balances between our check and our insert.
    """
    if not lines:
        raise ValueError("nothing to post")
    for line in lines:
        _check(line)
    _require_source_exists(db, source_type, source_id)
    items = masters.lock_items(db, (line.item_id for line in lines))

    posted: list[StockMovement] = []

    def insert(line: MovementLine, lot_id: int, qty: Decimal, value: int) -> None:
        movement = StockMovement(
            item_id=line.item_id,
            lot_id=lot_id,
            qty=qty,
            value_paise=value,
            movement_type=MovementType(line.movement_type).value,
            movement_date=movement_date,
            source_type=SourceType(source_type).value,
            source_id=source_id,
            source_line_id=line.source_line_id,
            posted_by=user_id,
        )
        db.add(movement)
        db.flush()  # later balance() calls in this transaction must see it
        posted.append(movement)

    for line in lines:
        if line.qty < 0:
            wanted = -line.qty
            try:
                # One rounding point per issue line (architecture section 5): value the whole
                # line once at the weighted-average cost as of the movement date, then split that
                # value across FIFO lots with the remainder on the last lot. Reading balances
                # as of the date stops a backdated issue from drawing stock that had not arrived.
                on_hand, on_hand_value = balance(db, line.item_id, as_of=movement_date)
                total_value = issue_value(wanted, on_hand, on_hand_value)
                if line.lot_id:
                    parts = [(line.lot_id, wanted)]
                else:
                    parts = allocate(db, line.item_id, wanted, as_of=movement_date)
                allocated = 0
                last = len(parts) - 1
                for i, (lot_id, part) in enumerate(parts):
                    _lot_of_item(db, lot_id, line.item_id)
                    # A lot has exactly one inflow (its creation); only outflows follow, so its
                    # balance never rises after that date and the current balance is its lowest
                    # point from the movement date on. Check the as-of-date balance AND the current
                    # one: the first stops drawing stock before it arrived, the second stops a
                    # backdated outflow from taking stock a later-dated outflow already took (which
                    # would leave the lot negative on that later date, so reconcile is never clean).
                    in_lot_asof, _ = balance(db, line.item_id, lot_id=lot_id, as_of=movement_date)
                    in_lot_now, _ = balance(db, line.item_id, lot_id=lot_id)
                    available = min(in_lot_asof, in_lot_now)
                    if part > available:
                        raise InsufficientStockError(part, available)
                    if i == last:
                        value = total_value - allocated  # remainder, so the parts sum exactly
                    else:
                        value = round_half_up(Decimal(total_value) * part / wanted)
                    allocated += value
                    insert(line, lot_id, -part, -value)
            except InsufficientStockError as exc:  # say which item is short
                code = items[line.item_id].code
                raise InsufficientStockError(exc.requested, exc.available, item=code) from None
        else:
            assert line.lot_id is not None and line.value_paise is not None  # checked in _check
            _lot_of_item(db, line.lot_id, line.item_id)
            is_cost_adjust = MovementType(line.movement_type) is MovementType.COST_ADJUST
            if is_cost_adjust and balance(db, line.item_id)[0] == 0:
                raise ValueError("no stock left to carry this cost; it would sit on zero quantity")
            insert(line, line.lot_id, line.qty, line.value_paise)
    return posted


def post_reversals(
    db: Session,
    *,
    source_type: SourceType,
    source_id: int,
    movement_date: date,
    user_id: int,
    lines: Sequence[ReversalLine],
) -> list[StockMovement]:
    """Undo named movements by mirroring each one: same lot, opposite qty and opposite value,
    linked to the original by reverses_id. Used by credit notes to cancel a dispatch.

    Mirroring (not recomputing) is what makes a cancellation exact: the stock and the value that
    left on dispatch come back unchanged, so balances and the item's weighted-average cost return
    to exactly where they were. reverses_id is UNIQUE, so a movement can be reversed at most once.
    """
    if not lines:
        raise ValueError("nothing to reverse")
    _require_source_exists(db, source_type, source_id)
    originals: dict[int, StockMovement] = {}
    for line in lines:
        original = db.get(StockMovement, line.original_id)
        if original is None:
            raise ValueError(f"movement {line.original_id} does not exist")
        if MovementType(original.movement_type) is MovementType.REVERSAL:
            raise ValueError("a reversal cannot itself be reversed")
        originals[line.original_id] = original
    # Lock the items first (as everywhere that posts), so a concurrent dispatch of the same item
    # can't interleave with this undo.
    masters.lock_items(db, (m.item_id for m in originals.values()))
    posted: list[StockMovement] = []
    for line in lines:
        original = originals[line.original_id]
        reversal = StockMovement(
            item_id=original.item_id,
            lot_id=original.lot_id,
            qty=-original.qty,
            value_paise=-original.value_paise,
            movement_type=MovementType.REVERSAL.value,
            movement_date=movement_date,
            source_type=SourceType(source_type).value,
            source_id=source_id,
            source_line_id=line.source_line_id,
            reverses_id=original.id,
            posted_by=user_id,
        )
        db.add(reversal)
        db.flush()  # the reverses_id UNIQUE index rejects a second reversal of the same movement
        posted.append(reversal)
    return posted


def post_opening_stock(
    db: Session,
    *,
    as_of: date,
    received_at: datetime,
    user_id: int,
    lines: Sequence[OpeningLine],
) -> StockAdjustment:
    """Opening balances as a real document (kind OPENING), so even day-one stock has a source."""
    doc = StockAdjustment(
        kind="OPENING", adj_date=as_of, reason="Opening stock", created_by=user_id
    )
    db.add(doc)
    db.flush()
    movements: list[MovementLine] = []
    for opening in lines:
        item = masters.get_item(db, opening.item_id)
        lot = create_lot(
            db,
            item_id=item.id,
            lot_no=f"OPEN-{item.code}",
            received_at=received_at,
            source_type=SourceType.STOCK_ADJUSTMENT,
            source_id=doc.id,
        )
        doc_line = StockAdjustmentLine(
            adjustment_id=doc.id,
            item_id=item.id,
            lot_id=lot.id,
            qty=opening.qty,
            value_paise=opening.value_paise,
        )
        db.add(doc_line)
        db.flush()
        movements.append(
            MovementLine(
                item_id=item.id,
                qty=opening.qty,
                movement_type=MovementType.OPENING,
                source_line_id=doc_line.id,
                lot_id=lot.id,
                value_paise=opening.value_paise,
            )
        )
    post_movements(
        db,
        source_type=SourceType.STOCK_ADJUSTMENT,
        source_id=doc.id,
        movement_date=as_of,
        user_id=user_id,
        lines=movements,
    )
    audit.record(
        db,
        entity="stock_adjustment",
        entity_id=doc.id,
        action="POST",
        user_id=user_id,
        after={"kind": "OPENING", "date": as_of.isoformat(), "lines": len(lines)},
    )
    return doc
