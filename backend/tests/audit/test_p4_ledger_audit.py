"""Hostile audit after P4 (ledger-auditor). Tests marked `# guard` pass and prove a control holds.
Every other test is a FINDING: it fails until the code is fixed. Severity is in each docstring.

Attacks follow .claude/agents/ledger-auditor.md. Out of scope at P4 (not built): order idempotency,
reversals/credit notes (8), invoice numbering (9).
"""

import itertools
import re
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

import app.inventory.service as inv_mod
from app.auth.models import AppUser
from app.core.db import SessionLocal, engine
from app.core.errors import AppError
from app.inventory import service as stock
from app.inventory.models import MovementType, SourceType
from app.inventory.service import MovementLine
from app.masters.models import Item
from app.production import service as production
from app.production.schemas import RunComplete, RunCreate
from tests.invariants import ledger_problems

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"
D = Decimal
APP_DIR = Path(__file__).resolve().parents[2] / "app"
_seq = itertools.count(1)
WRITER = r"(?<!class )StockMovement\(|insert\s+into\s+stock_movement"


# ---- helpers (all through the real API) --------------------------------------------------


def sandbox(client, as_user, raws=(("g", "1", "kg"),), output="10"):
    """Fresh raw items + FG + BOM, so each attack starts from known zero stock."""
    admin, n = as_user("admin"), next(_seq)
    raw_ids = []
    for i, (base, _, _) in enumerate(raws):
        body = {"code": f"AUD-R{n}-{i}", "name": "audit raw", "kind": "RAW", "base_uom": base}
        r = client.post(f"{API}/items", json=body, headers=admin)
        assert r.status_code == 201, r.text
        raw_ids.append(r.json()["id"])
    fg = {
        "code": f"AUD-FG{n}",
        "name": "audit FG",
        "kind": "FG",
        "base_uom": "pkt",
        "sale_price_paise": 5000,
        "gst_rate_bp": 500,
        "shelf_life_days": 90,
    }
    r = client.post(f"{API}/items", json=fg, headers=admin)
    assert r.status_code == 201, r.text
    fg_id = r.json()["id"]
    bom = {
        "code": f"AUD-BOM{n}",
        "item_id": fg_id,
        "output_qty": output,
        "lines": [
            {"item_id": rid, "qty": qty, "uom": uom}
            for rid, (_, qty, uom) in zip(raw_ids, raws, strict=True)
        ],
    }
    r = client.post(f"{API}/boms", json=bom, headers=admin)
    assert r.status_code == 201, r.text
    return SimpleNamespace(raws=raw_ids, fg=fg_id, bom=r.json()["id"])


def buy(client, as_user, lines, on="2026-11-02"):
    prod = as_user("production")
    supplier = client.get(f"{API}/suppliers", params={"code": "FLOUR-SUPPLIER"}, headers=prod)
    body = {
        "supplier_id": supplier.json()[0]["id"],
        "purchase_date": on,
        "lines": [
            {"item_id": i, "qty": q, "uom": u, "rate_paise": rate} for i, q, u, rate in lines
        ],
    }
    r = client.post(f"{API}/purchases", json=body, headers=prod)
    assert r.status_code == 201, r.text
    return r.json()


def start(client, as_user, bom, issues, on="2026-11-02"):
    body = {
        "bom_id": bom,
        "batches": "1",
        "run_date": on,
        "issues": [{"item_id": i, "qty": q, "uom": u} for i, q, u in issues],
    }
    return client.post(f"{API}/production-runs", json=body, headers=as_user("production"))


def balance(client, as_user, item_id, as_of=None):
    params = {"as_of": as_of} if as_of else {}
    r = client.get(f"{API}/stock/balance/{item_id}", params=params, headers=as_user("accountant"))
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["qty"], str)  # quantities are decimal strings on the wire
    return D(r.json()["qty"]), r.json()["value_paise"]


def run_movement_value(run_id: int, movement_type: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT COALESCE(SUM(value_paise), 0) FROM stock_movement WHERE"
                " source_type = 'production_run' AND source_id = :id AND movement_type = :t"
            ),
            {"id": run_id, "t": movement_type},
        ).scalar_one()


def user_id(username: str) -> int:
    with SessionLocal() as s:
        return s.scalar(select(AppUser.id).where(AppUser.username == username))


# ---- 1. direct writes --------------------------------------------------------------------


def test_only_inventory_service_constructs_movements() -> None:  # guard
    writers = [
        str(p.relative_to(APP_DIR))
        for p in APP_DIR.rglob("*.py")
        if re.search(WRITER, p.read_text(), re.I)
    ]
    assert writers == ["inventory/service.py"]


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE stock_movement SET value_paise = 0 WHERE movement_type = 'OPENING'",
        "DELETE FROM stock_movement WHERE movement_type = 'OPENING'",
        "TRUNCATE stock_movement CASCADE",
    ],
)
def test_ledger_rows_cannot_be_changed_by_sql(sql: str) -> None:  # guard
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(sql))


# ---- 2. orphans ----------------------------------------------------------------------------


def test_post_movements_refuses_a_source_document_that_does_not_exist(db) -> None:
    """FINDING (major, invariant 6): post_movements() never checks that source_type/source_id
    names a real document, and tests/invariants.py ORPHANS only looks for NULLs in NOT NULL
    columns, so it can never fire. A caller bug posts untraceable stock and every check is green.
    """
    flour = db.scalar(select(Item).where(Item.code == "FLOUR"))
    lot = stock.create_lot(
        db,
        item_id=flour.id,
        lot_no="AUD-GHOST",
        received_at=datetime(2026, 11, 2, tzinfo=UTC),
        source_type=SourceType.PURCHASE,
        source_id=987654,  # no such purchase
    )
    ghost = MovementLine(
        flour.id, D(1000), MovementType.PURCHASE, 1, lot_id=lot.id, value_paise=4200
    )
    try:
        stock.post_movements(
            db,
            source_type=SourceType.PURCHASE,
            source_id=987654,
            movement_date=date(2026, 11, 2),
            user_id=user_id("admin"),
            lines=[ghost],
        )
    except (ValueError, AppError):
        return  # refused: the control exists
    assert ledger_problems(db) != [], "1 kg of flour from purchase #987654 (does not exist) passes"


def test_a_posted_purchase_cannot_be_deleted(client, as_user, db) -> None:
    """FINDING (major, invariant 7): purchase/purchase_line have no append-only guard. Deleting a
    posted purchase succeeds and leaves its PURCHASE movements pointing at nothing; reconcile()
    and the orphan check both stay []. (Rolled back by the db fixture.)"""
    s = sandbox(client, as_user)
    purchase = buy(client, as_user, [(s.raws[0], "5", "kg", 4000)])
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM purchase_line WHERE purchase_id = :p"), {"p": purchase["id"]})
        db.execute(text("DELETE FROM purchase WHERE id = :p"), {"p": purchase["id"]})


def test_run_cost_and_yield_cannot_diverge_from_the_ledger(client, as_user, db) -> None:
    """FINDING (major): production_run.good_qty and run_overhead are mutable second copies of the
    OUTPUT / COST_ADJUST movements. /cost and /variance read the copies; reconcile() never
    cross-checks them. Changing good_qty 10 -> 12 silently rewrites cost per packet and yield."""
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()
    done = client.post(
        f"{API}/production-runs/{run['id']}/complete",
        json={"output_qty": "10"},
        headers=as_user("production"),
    )
    assert done.status_code == 200, done.text
    honest = production.run_cost(db, run["id"]).cost_per_unit_paise  # 4000 / 10 = 400
    try:
        db.execute(text("UPDATE production_run SET good_qty = 12 WHERE id = :r"), {"r": run["id"]})
    except DBAPIError:
        return  # refused: the control exists
    db.expire_all()
    tampered = production.run_cost(db, run["id"]).cost_per_unit_paise
    assert (honest, tampered) == (400, 333)  # evidence: the report followed the edited copy
    assert stock.reconcile(db) != [], "good_qty 12 vs OUTPUT 10 in the ledger: reconcile is blind"


# ---- 3. negative stock ---------------------------------------------------------------------


def test_cannot_issue_more_than_on_hand_through_the_api(client, as_user) -> None:  # guard
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    r = start(client, as_user, s.bom, [(s.raws[0], "1.001", "kg")])
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INSUFFICIENT_STOCK")
    assert balance(client, as_user, s.raws[0]) == (D(1000), 4000)


def _slow(monkeypatch, name: str) -> None:
    """Widen the check-then-insert window inside the ledger so an unlocked race would show."""
    real = getattr(inv_mod, name)

    def slow(*args, **kwargs):
        time.sleep(0.4)
        return real(*args, **kwargs)

    monkeypatch.setattr(inv_mod, name, slow)


def _in_threads(*jobs):
    results: list = [None] * len(jobs)
    barrier = threading.Barrier(len(jobs))

    def runner(i, job):
        with SessionLocal() as s:
            barrier.wait()
            try:
                results[i] = job(s)
            except Exception as exc:  # noqa: BLE001 - we inspect it below
                s.rollback()
                results[i] = exc

    threads = [threading.Thread(target=runner, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return results


def _race_two_runs(client, as_user, monkeypatch):
    """Two start_run calls, separate sessions, each issuing 6 of 10 kg. lock_items is delayed so
    both transactions have inserted their run rows before either takes the item lock."""
    import app.masters.service as masters_mod

    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "10", "kg", 4000)])
    real_lock = masters_mod.lock_items

    def slow_lock(*args, **kwargs):
        time.sleep(0.4)
        return real_lock(*args, **kwargs)

    monkeypatch.setattr(masters_mod, "lock_items", slow_lock)
    _slow(monkeypatch, "issue_value")
    pid = user_id("production")

    def job(session):
        body = RunCreate(
            bom_id=s.bom,
            batches="1",
            run_date=date(2026, 11, 2),
            issues=[{"item_id": s.raws[0], "qty": "6", "uom": "kg"}],
        )
        return production.start_run(session, body, session.get(AppUser, pid))

    return s, _in_threads(job, job)


def test_two_concurrent_runs_cannot_overdraw_stock(client, as_user, monkeypatch) -> None:  # guard
    s, results = _race_two_runs(client, as_user, monkeypatch)
    assert sum(not isinstance(r, Exception) for r in results) == 1, results
    assert balance(client, as_user, s.raws[0]) == (D(4000), 16000)
    with SessionLocal() as session:
        assert ledger_problems(session) == []


def test_concurrent_runs_lose_with_insufficient_stock_not_a_deadlock(
    client, as_user, monkeypatch
) -> None:
    """FINDING (minor by the rubric, no wrong number; high priority): masters.lock_items()
    claims "the fixed order means they can't deadlock" (masters/service.py:77-82). But start_run
    inserts production_run/run_consumption first (and create_purchase inserts stock_lot/
    purchase_line), whose foreign keys take FOR KEY SHARE on the same item rows. Two such
    transactions each hold KEY SHARE and then wait for FOR UPDATE: Postgres kills one with
    DeadlockDetected, an unhandled 500 instead of 409 INSUFFICIENT_STOCK. A client that retries
    a 500 (the P8 offline queue) risks double posting once idempotency exists only per key."""
    _, results = _race_two_runs(client, as_user, monkeypatch)
    losers = [r for r in results if isinstance(r, Exception)]
    assert [type(e).__name__ for e in losers] == ["InsufficientStockError"], losers


def test_two_concurrent_completes_post_output_once(client, as_user, monkeypatch) -> None:  # guard
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run_id = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()["id"]
    _slow(monkeypatch, "post_movements")
    pid = user_id("production")

    def job(session):
        body = RunComplete(output_qty="10")
        return production.complete_run(session, run_id, body, session.get(AppUser, pid))

    results = _in_threads(job, job)
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1 and getattr(errors[0], "code", None) == "RUN_ALREADY_COMPLETED"
    assert balance(client, as_user, s.fg) == (D(10), 4000)
    assert run_movement_value(run_id, "OUTPUT") == 4000


def test_backdated_run_cannot_consume_stock_that_had_not_arrived(client, as_user) -> None:
    """FINDING (critical): post_movements checks only today's total balance, never the balance on
    the movement's date. A run dated 2 Nov consumes flour received on 20 Nov, so the ledger shows
    -4 kg (and negative value) on 2 Nov via /stock/balance?as_of=, and FIFO takes a lot before
    it was received. reconcile() says healthy. Period stock reports (M7) will print it."""
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "10", "kg", 4000)], on="2026-11-20")
    r = start(client, as_user, s.bom, [(s.raws[0], "4", "kg")], on="2026-11-02")
    if r.status_code != 201:
        return  # refused: the control exists
    assert balance(client, as_user, s.raws[0], as_of="2026-11-02") >= (
        D(0),
        0,
    ), "stock on 2 Nov is negative"


# ---- 4. double posting ---------------------------------------------------------------------


def test_completing_a_run_twice_is_refused(client, as_user) -> None:  # guard
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run_id = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()["id"]
    url = f"{API}/production-runs/{run_id}/complete"
    first = client.post(url, json={"output_qty": "10"}, headers=as_user("production"))
    again = client.post(url, json={"output_qty": "10"}, headers=as_user("production"))
    assert (first.status_code, again.status_code) == (200, 409)
    assert balance(client, as_user, s.fg) == (D(10), 4000)


# ---- 5. float leaks ------------------------------------------------------------------------


def test_no_float_or_round_in_app_code() -> None:  # guard
    hits = [
        f"{p.relative_to(APP_DIR)}:{n}"
        for p in APP_DIR.rglob("*.py")
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if re.search(r"\bfloat\(|(?<![_\w])round\((?!\))|Decimal\(\d+\.\d", line.split("#")[0])
    ]
    assert hits == []


def test_json_floats_are_refused_for_qty_and_money(client, as_user) -> None:  # guard
    s = sandbox(client, as_user)
    prod = as_user("production")
    bad_run = {"bom_id": s.bom, "batches": 1.5, "run_date": "2026-11-02"}
    assert client.post(f"{API}/production-runs", json=bad_run, headers=prod).status_code == 422
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run_id = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()["id"]
    url = f"{API}/production-runs/{run_id}"
    assert (
        client.post(f"{url}/complete", json={"output_qty": 10.0}, headers=prod).status_code == 422
    )
    client.post(f"{url}/complete", json={"output_qty": "10"}, headers=prod)
    money = {"lines": [{"kind": "LABOUR", "amount_paise": 100.0}]}
    assert client.post(f"{url}/overheads", json=money, headers=prod).status_code == 422


# ---- 6. rounding residue -------------------------------------------------------------------


def test_issuing_to_zero_in_odd_steps_leaves_zero_paise(client, as_user) -> None:  # guard
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 1001)])  # 1000 g for 1001 paise
    for qty in ("333", "333", "334"):
        assert start(client, as_user, s.bom, [(s.raws[0], qty, "g")]).status_code == 201
    assert balance(client, as_user, s.raws[0]) == (D(0), 0)


def test_issue_value_does_not_depend_on_how_many_lots_it_spans(client, as_user) -> None:
    """FINDING (minor, money off by 1 paisa per lot boundary): architecture section 5 defines ONE
    rounding point, issue value = half_up(qty x value / qty_on_hand). post_movements rounds each
    FIFO lot part separately. Stock 3 g worth 5 paise in two lots; issuing 2 g should cost
    half_up(2 x 5 / 3) = 3 paise; the ledger books 4 (2 + 2) and the run's material cost with it."""
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "g", 1), (s.raws[0], "2", "g", 2)])  # two lots
    r = start(client, as_user, s.bom, [(s.raws[0], "2", "g")])
    assert r.status_code == 201, r.text
    assert run_movement_value(r.json()["id"], "ISSUE") == -3


def test_count_units_are_whole_numbers(client, as_user) -> None:
    """FINDING (minor, missing guard): 187.5 packets of FG (or 0.5 pouch) are accepted. Packets
    are the invoice unit, and core.gst assumes whole packets; a fractional FG balance can't be
    invoiced cleanly later (P5) and is physically meaningless."""
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run_id = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()["id"]
    r = client.post(
        f"{API}/production-runs/{run_id}/complete",
        json={"output_qty": "187.5"},
        headers=as_user("production"),
    )
    assert r.status_code == 422, f"accepted {balance(client, as_user, s.fg)[0]} pkt"


def test_cost_adjust_cannot_drive_value_negative(db) -> None:
    """FINDING (minor, service-level guard missing): post_movements() accepts a COST_ADJUST with a
    negative value larger than the stock's value. reconcile() catches it afterwards, but the
    single writer of the ledger should refuse it (the API only sends positive overheads today)."""
    murukku = db.scalar(select(Item).where(Item.code == "MURUKKU-200G"))
    lot = stock.lot_balances(db, murukku.id)[0][0]
    wipe = MovementLine(
        murukku.id, D(0), MovementType.COST_ADJUST, 1, lot_id=lot, value_paise=-(10**9)
    )
    with pytest.raises(ValueError):
        stock.post_movements(
            db,
            source_type=SourceType.STOCK_ADJUSTMENT,
            source_id=1,
            movement_date=date(2026, 11, 2),
            user_id=user_id("admin"),
            lines=[wipe],
        )


# ---- 7. unit confusion ---------------------------------------------------------------------


def test_buy_in_kg_issue_in_g_and_kg_agree(client, as_user) -> None:  # guard
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "2.5", "kg", 4300)])  # 2500 g, 10750 paise
    assert start(client, as_user, s.bom, [(s.raws[0], "1.234567", "kg")]).status_code == 201
    assert start(client, as_user, s.bom, [(s.raws[0], "1265.433", "g")]).status_code == 201
    assert balance(client, as_user, s.raws[0]) == (D(0), 0)
    wrong = start(client, as_user, s.bom, [(s.raws[0], "1", "l")])
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "UNIT_ERROR")
    run_id = start(client, as_user, s.bom, []).json()["id"]
    kg_out = client.post(
        f"{API}/production-runs/{run_id}/complete",
        json={"output_qty": "1", "output_uom": "kg"},
        headers=as_user("production"),
    )
    assert kg_out.status_code == 422


# ---- 10. RBAC -------------------------------------------------------------------------------

WRITES = [
    "/items",
    "/customers",
    "/suppliers",
    "/boms",
    "/purchases",
    "/production-runs",
    "/production-runs/1/complete",
    "/production-runs/1/overheads",
]


@pytest.mark.parametrize("username", ["accountant", "owner", "salesman_a"])
@pytest.mark.parametrize("path", WRITES)
def test_read_only_roles_cannot_write(client, as_user, username, path) -> None:  # guard
    r = client.post(f"{API}{path}", json={}, headers=as_user(username))
    assert r.status_code == 403, r.text


@pytest.mark.parametrize("path", WRITES[4:])
def test_admin_cannot_post_stock(client, as_user, path) -> None:  # guard
    assert client.post(f"{API}{path}", json={}, headers=as_user("admin")).status_code == 403


@pytest.mark.parametrize(
    ("username", "path"),
    [
        ("salesman_a", "/stock/balance/1"),
        ("salesman_a", "/production-runs/1/cost"),
        ("salesman_a", "/purchases/1"),
        ("salesman_a", "/suppliers"),
        ("production", "/customers"),
        ("production", "/stock/reconcile"),
    ],
)
def test_roles_cannot_read_outside_their_area(client, as_user, username, path) -> None:  # guard
    assert client.get(f"{API}{path}", headers=as_user(username)).status_code == 403


def test_production_cannot_write_the_standard_it_is_measured_against(client, as_user) -> None:
    """FINDING (minor, RBAC vs spec section 2): masters (M2 includes BOM) are admin's. The
    production role can POST /boms, i.e. set the standard its own variance (B8/B9, S5 alerts) is
    measured against: no segregation of duties. masters/router.py BomEditor."""
    admin = as_user("admin")
    fg = {
        "code": "AUD-FG-RBAC",
        "name": "x",
        "kind": "FG",
        "base_uom": "pkt",
        "sale_price_paise": 1,
    }
    fg_id = client.post(f"{API}/items", json=fg, headers=admin).json()["id"]
    flour = client.get(f"{API}/items", params={"code": "FLOUR"}, headers=admin).json()[0]["id"]
    bom = {
        "code": "AUD-BOM-RBAC",
        "item_id": fg_id,
        "output_qty": "200",
        "lines": [{"item_id": flour, "qty": "999", "uom": "kg"}],  # generous standard
    }
    r = client.post(f"{API}/boms", json=bom, headers=as_user("production"))
    assert r.status_code == 403, r.status_code


# ---- 11. reconciliation (runs last: checks everything the attacks above committed) ---------


def test_zz_ledger_and_documents_reconcile_after_all_attacks(client, as_user) -> None:  # guard
    with SessionLocal() as s:
        assert ledger_problems(s) == []
        items = s.scalars(select(Item.id)).all()
        for item_id in items:
            q, v = s.execute(
                text(
                    "SELECT COALESCE(SUM(qty),0), COALESCE(SUM(value_paise),0)"
                    " FROM stock_movement WHERE item_id = :i"
                ),
                {"i": item_id},
            ).one()
            assert balance(client, as_user, item_id) == (D(q), int(v))
        mismatches = s.execute(
            text(
                """
            SELECT 'purchase_line ' || pl.id FROM purchase_line pl
              LEFT JOIN stock_movement m ON m.source_type = 'purchase'
               AND m.source_id = pl.purchase_id AND m.source_line_id = pl.id
             GROUP BY pl.id, pl.qty, pl.value_paise
            HAVING COUNT(m.id) <> 1 OR SUM(m.qty) <> pl.qty OR SUM(m.value_paise) <> pl.value_paise
            UNION ALL
            SELECT 'run ' || r.id FROM production_run r
              LEFT JOIN stock_movement m ON m.source_type = 'production_run'
               AND m.source_id = r.id AND m.movement_type = 'OUTPUT'
             WHERE r.status = 'COMPLETED'
             GROUP BY r.id, r.good_qty
            HAVING COUNT(m.id) <> 1 OR SUM(m.qty) <> r.good_qty
            UNION ALL
            SELECT 'overhead ' || o.id FROM run_overhead o
              LEFT JOIN stock_movement m ON m.source_type = 'production_run'
               AND m.source_id = o.run_id AND m.movement_type = 'COST_ADJUST'
               AND m.source_line_id = o.id
             GROUP BY o.id, o.amount_paise
            HAVING COUNT(m.id) <> 1 OR SUM(m.value_paise) <> o.amount_paise
            UNION ALL
            SELECT 'movement ' || m.id || ' has no document' FROM stock_movement m
             WHERE NOT EXISTS (SELECT 1 FROM purchase p WHERE m.source_type = 'purchase'
                                AND p.id = m.source_id)
               AND NOT EXISTS (SELECT 1 FROM production_run r
                                WHERE m.source_type = 'production_run' AND r.id = m.source_id)
               AND NOT EXISTS (SELECT 1 FROM stock_adjustment a
                                WHERE m.source_type = 'stock_adjustment' AND a.id = m.source_id)
            """
            )
        ).all()
        assert mismatches == []
