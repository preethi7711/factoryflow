"""The stock ledger: opening stock, append-only, traceability, FIFO lots, WAC values, reconcile.

Service-level tests use the rolled-back `db` fixture, so nothing they post survives the test.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.auth.models import AppUser
from app.core.db import engine
from app.core.wac import InsufficientStockError
from app.inventory import service as stock
from app.inventory.models import MovementType, SourceType, StockAdjustment
from app.inventory.service import MovementLine
from app.masters.models import Item

pytestmark = pytest.mark.usefixtures("seeded_db")
D = Decimal
ON = date(2026, 11, 2)

RAW_INSERT = text(
    "INSERT INTO stock_movement (item_id, lot_id, qty, value_paise, movement_type,"
    " movement_date, source_type, source_id, source_line_id, posted_by)"
    " VALUES (:item, :lot, :qty, :value, :type, '2026-11-02', 'stock_adjustment', 1, :line, :user)"
)


def _item(db, code: str) -> Item:
    return db.scalar(select(Item).where(Item.code == code))


def _admin_id(db) -> int:
    return db.scalar(select(AppUser.id).where(AppUser.username == "admin"))


def _first_lot(db, code: str) -> int:
    return stock.lot_balances(db, _item(db, code).id)[0][0]


def _post(db, *lines: MovementLine, source_type: SourceType = SourceType.STOCK_ADJUSTMENT):
    # Post against a real stock_adjustment document: post_movements now refuses an orphan source,
    # and that is correct. source_type is kept for call-site readability; the document is real.
    doc = StockAdjustment(
        kind="ADJUST", adj_date=ON, reason="ledger test", created_by=_admin_id(db)
    )
    db.add(doc)
    db.flush()
    return stock.post_movements(
        db,
        source_type=SourceType.STOCK_ADJUSTMENT,
        source_id=doc.id,
        movement_date=ON,
        user_id=_admin_id(db),
        lines=list(lines),
    )


def _issue(item: Item, qty: str) -> MovementLine:
    return MovementLine(item.id, -D(qty), MovementType.ISSUE, source_line_id=1)


# ---- through the API -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "qty", "uom", "value"),
    [
        ("FLOUR", "100000", "g", 420000),  # 100 kg at Rs 42
        ("OIL", "30000", "ml", 420000),  # 30 L at Rs 140
        ("SPICE-MIX", "5000", "g", 100000),
        ("POUCH-200G", "500", "pcs", 125000),
        ("CARTON", "30", "pcs", 45000),
        ("MURUKKU-200G", "50", "pkt", 99250),  # A5: 50 x Rs 19.85
    ],
)
def test_opening_stock_after_seed(client, as_user, db, code, qty, uom, value) -> None:
    item = _item(db, code)
    body = client.get(f"/api/v1/stock/balance/{item.id}", headers=as_user("production")).json()
    assert (D(body["qty"]), body["uom"], body["value_paise"]) == (D(qty), uom, value)


def test_balance_before_the_opening_date_is_zero(client, as_user, db) -> None:
    flour = _item(db, "FLOUR")
    r = client.get(
        f"/api/v1/stock/balance/{flour.id}",
        params={"as_of": "2026-10-30"},
        headers=as_user("admin"),
    )
    assert D(r.json()["qty"]) == 0


def test_reconcile_is_clean_after_seed(client, as_user) -> None:
    r = client.get("/api/v1/stock/reconcile", headers=as_user("accountant"))
    assert r.json() == {"ok": True, "problems": []}


# ---- what the database itself refuses ------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE stock_movement SET qty = qty + 1",
        "DELETE FROM stock_movement",
        "TRUNCATE stock_movement",
        "UPDATE audit_log SET action = 'EDITED'",
        "DELETE FROM audit_log",
    ],
)
def test_ledger_and_audit_log_are_append_only(sql: str) -> None:
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(sql))


@pytest.mark.parametrize(
    "change",
    [
        {"line": None},  # no source line: an orphan
        {"lot": "OIL"},  # flour movement pointing at an oil lot
        {"type": "ISSUE", "qty": 5},  # an issue must reduce stock
        {"type": "GIFT"},  # not a movement type
    ],
)
def test_database_rejects_bad_movements(db, change: dict) -> None:
    params = {
        "item": _item(db, "FLOUR").id,
        "lot": _first_lot(db, "FLOUR"),
        "qty": 1,
        "value": 0,
        "type": "ADJUST",
        "line": 1,
        "user": _admin_id(db),
    }
    if change.get("lot") == "OIL":
        change = {"lot": _first_lot(db, "OIL")}
    with pytest.raises(IntegrityError):
        db.execute(RAW_INSERT, {**params, **change})


# ---- post_movements ------------------------------------------------------------------


def test_issue_takes_oldest_lot_first_valued_at_weighted_average(db) -> None:
    flour = _item(db, "FLOUR")
    opening_lot = _first_lot(db, "FLOUR")
    new_lot = stock.create_lot(
        db,
        item_id=flour.id,
        lot_no="TEST-PURCHASE",
        received_at=datetime(2026, 11, 2, tzinfo=UTC),
        source_type=SourceType.PURCHASE,
        source_id=999,
    )
    purchase = MovementLine(
        flour.id, D(60000), MovementType.PURCHASE, 1, lot_id=new_lot.id, value_paise=270000
    )
    _post(db, purchase, source_type=SourceType.PURCHASE)  # 160 kg for Rs 6,900 = Rs 43.125/kg

    issued = _post(db, _issue(flour, "120000"), source_type=SourceType.PRODUCTION_RUN)

    assert [(m.lot_id, m.qty, m.value_paise) for m in issued] == [
        (opening_lot, D(-100000), -431250),  # the whole opening lot first (FIFO)
        (new_lot.id, D(-20000), -86250),  # then the rest from the new lot, same average
    ]
    assert stock.balance(db, flour.id) == (D(40000), 172500)  # 40 kg left at Rs 43.125/kg


def test_cannot_issue_more_than_on_hand(db) -> None:
    with pytest.raises(InsufficientStockError) as exc:
        _post(db, _issue(_item(db, "FLOUR"), "200000"))
    assert (exc.value.requested, exc.value.available) == (D(200000), D(100000))


def test_last_issue_takes_the_rounding_remainder(db) -> None:
    oil = _item(db, "OIL")
    lot = stock.create_lot(
        db,
        item_id=oil.id,
        lot_no="TEST-ODD",
        received_at=datetime(2026, 11, 2, tzinfo=UTC),
        source_type=SourceType.PURCHASE,
        source_id=999,
    )
    odd = MovementLine(oil.id, D(1000), MovementType.PURCHASE, 1, lot_id=lot.id, value_paise=14001)
    _post(db, odd, source_type=SourceType.PURCHASE)  # 31000 ml worth 434001 paise
    first = _post(db, _issue(oil, "10000"))
    assert first[0].value_paise == -140000  # 140000.32 rounded half-up
    _post(db, _issue(oil, "21000"))  # empties the oil: takes all 294001 left
    assert stock.balance(db, oil.id) == (D(0), 0)
    assert stock.reconcile(db) == []


def test_cost_adjust_adds_value_without_quantity(db) -> None:
    murukku = _item(db, "MURUKKU-200G")
    adjust = MovementLine(
        murukku.id,
        D(0),
        MovementType.COST_ADJUST,
        1,
        lot_id=_first_lot(db, "MURUKKU-200G"),
        value_paise=18000,
    )
    _post(db, adjust, source_type=SourceType.PRODUCTION_RUN)
    assert stock.balance(db, murukku.id) == (D(50), 117250)


def test_cost_adjust_on_zero_stock_is_refused(db) -> None:
    cartons = _item(db, "CARTON")
    lot = _first_lot(db, "CARTON")
    _post(db, _issue(cartons, "30"))
    adjust = MovementLine(cartons.id, D(0), MovementType.COST_ADJUST, 1, lot_id=lot, value_paise=1)
    with pytest.raises(ValueError, match="zero quantity"):
        _post(db, adjust)


def test_malformed_lines_are_refused_before_anything_is_written(db) -> None:
    flour = _item(db, "FLOUR")
    oil_lot = _first_lot(db, "OIL")
    bad_lines = [
        MovementLine(flour.id, D("-1.2345"), MovementType.ISSUE, 1),  # 4 decimals of a gram
        MovementLine(flour.id, D(5), MovementType.ISSUE, 1),  # an issue must be negative
        MovementLine(flour.id, D(5), MovementType.PURCHASE, 1),  # inflow without lot and value
        MovementLine(flour.id, D(-5), MovementType.ISSUE, 1, value_paise=10),  # WAC sets value
        MovementLine(flour.id, D(5), MovementType.PURCHASE, 1, lot_id=oil_lot, value_paise=1),
        MovementLine(flour.id, D(-5), MovementType.REVERSAL, 1),  # arrives with credit notes
    ]
    for line in bad_lines:
        with pytest.raises(ValueError):
            _post(db, line)
    assert stock.balance(db, flour.id) == (D(100000), 420000)  # untouched


def test_reconcile_reports_value_left_on_zero_stock(db) -> None:
    cartons = _item(db, "CARTON")
    lot = _first_lot(db, "CARTON")
    _post(db, _issue(cartons, "30"))
    # Only raw SQL can bypass post_movements; reconcile must still catch the damage.
    db.execute(
        RAW_INSERT,
        {
            "item": cartons.id,
            "lot": lot,
            "qty": 0,
            "value": 100,
            "type": "COST_ADJUST",
            "line": 1,
            "user": _admin_id(db),
        },
    )
    assert stock.reconcile(db) == ["CARTON: 100 paise of value left on zero stock"]
