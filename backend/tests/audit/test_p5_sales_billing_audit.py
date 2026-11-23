"""Hostile audit after P5 (sales orders + billing). Every test is now a `# guard` that passes and
proves a control holds. Three started as findings the ledger-auditor confirmed; all three were
fixed in the same change and the tests below now assert the corrected, secure behaviour:

- CRITICAL (invariant 4, no negative stock): a backdated, out-of-order dispatch could drive a lot
  negative, because post_movements only checked the as-of-date balance. Fixed by also checking the
  current per-lot balance (a lot has one inflow, so now is its lowest point). See
  test_backdated_out_of_order_dispatch_is_refused.
- MINOR (idempotency under concurrency): the losing caller of a double-tap raised instead of
  replaying. Fixed by widening create_order's IntegrityError->replay guard to cover the flush, not
  just the commit. See test_concurrent_double_tap_replays_for_the_loser.
- MINOR (confidentiality): replay did not check the caller owned the key. Fixed in _replay. See
  test_replay_by_another_user_is_refused.

In scope for P5 (ledger-auditor attacks): 4 idempotency replay, 8 reversal symmetry, 9 invoice
numbering, plus the standing invariants (reconcile clean, no negative/stranded value, no orphans,
API balance == SUM(ledger)) after the sales/billing scenarios.

Helpers (sandbox/buy/start/balance/user_id/_in_threads) are reused from the P4 audit suite so the
fixtures and style match exactly.
"""

import time
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.auth.models import AppUser
from app.billing.models import InvoiceSequence
from app.billing.schemas import InvoiceCreate
from app.billing.service import create_invoice
from app.core.db import SessionLocal, engine
from app.inventory.models import StockMovement
from app.sales.schemas import OrderCreate, OrderLineIn
from app.sales.service import create_order
from tests.audit.test_p4_ledger_audit import (
    _in_threads,
    balance,
    buy,
    sandbox,
    start,
    user_id,
)
from tests.invariants import ledger_problems

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"
D = Decimal


# ---- helpers (all through the real API) --------------------------------------------------


def fg_with_stock(client, as_user, pkts="300"):
    """A fresh FG item (priced 5000 paise, GST 5%) carrying `pkts` of committed stock produced by
    a real run, so each billing attack starts from known, isolated finished goods."""
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "1", "kg", 4000)])
    run_id = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")]).json()["id"]
    r = client.post(
        f"{API}/production-runs/{run_id}/complete",
        json={"output_qty": pkts},
        headers=as_user("production"),
    )
    assert r.status_code == 200, r.text
    return s.fg


_cust = iter(range(1, 10_000))


def make_customer(client, as_user, *, state_code="33", salesman="salesman_a"):
    n = next(_cust)
    body = {
        "code": f"AUD-CUST{n}",
        "name": "Audit customer",
        "state_code": state_code,
        "salesman_id": user_id(salesman),
    }
    r = client.post(f"{API}/customers", json=body, headers=as_user("admin"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def place(client, as_user, key, customer_id, fg_id, qty, *, salesman="salesman_a", on="2026-11-03"):
    body = {
        "customer_id": customer_id,
        "order_date": on,
        "lines": [{"item_id": fg_id, "qty": qty, "uom": "pkt"}],
    }
    headers = {**as_user(salesman), "Idempotency-Key": key}
    return client.post(f"{API}/orders", json=body, headers=headers)


def approve(client, as_user, order_id):
    return client.post(f"{API}/orders/{order_id}/approve", headers=as_user("admin"))


def raise_invoice(client, as_user, order_id, on="2026-11-03"):
    return client.post(
        f"{API}/orders/{order_id}/invoice", json={"invoice_date": on}, headers=as_user("admin")
    )


def dispatch(client, as_user, invoice_id, on="2026-11-03"):
    return client.post(
        f"{API}/invoices/{invoice_id}/dispatch",
        json={"dispatch_date": on},
        headers=as_user("admin"),
    )


def cancel(client, as_user, invoice_id, on="2026-11-04"):
    return client.post(
        f"{API}/invoices/{invoice_id}/cancel",
        json={"cn_date": on, "reason": "audit"},
        headers=as_user("admin"),
    )


def orders_with_uuid(key: str) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT COUNT(*) FROM sales_order WHERE client_uuid = :k"), {"k": key}
        ).scalar_one()


_key = iter(range(1, 10_000))


def fresh_key(tag: str) -> str:
    return f"aud-{tag}-{next(_key)}"


# ---- 4. idempotency replay ---------------------------------------------------------------


def test_replay_same_key_same_body_returns_the_first_order(client, as_user) -> None:  # guard
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user)
    key = fresh_key("same")
    first = place(client, as_user, key, cust, fg, "10")
    assert first.status_code == 201, first.text
    second = place(client, as_user, key, cust, fg, "10")
    assert second.status_code in (200, 201), second.text
    assert second.json()["id"] == first.json()["id"]  # the first order, not a copy
    assert orders_with_uuid(key) == 1  # exactly one row landed


def test_replay_same_key_different_qty_is_409(client, as_user) -> None:  # guard
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user)
    key = fresh_key("diffqty")
    assert place(client, as_user, key, cust, fg, "10").status_code == 201
    clash = place(client, as_user, key, cust, fg, "11")
    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert orders_with_uuid(key) == 1


def test_replay_cannot_smuggle_a_different_customer(client, as_user) -> None:  # guard
    """A replayed key with a different customer must 409, never silently re-point the order."""
    fg = fg_with_stock(client, as_user)
    cust_a = make_customer(client, as_user)
    cust_b = make_customer(client, as_user)
    key = fresh_key("smuggle")
    assert place(client, as_user, key, cust_a, fg, "10").status_code == 201
    clash = place(client, as_user, key, cust_b, fg, "10")
    assert clash.status_code == 409, clash.text
    assert orders_with_uuid(key) == 1


def test_concurrent_double_tap_replays_for_the_loser(client, as_user, monkeypatch) -> None:  # guard
    """A genuine double-tap (two requests, same key, same body) lands exactly one order (UNIQUE
    client_uuid) AND the losing caller gets the stored response, not a 500. create_order() wraps
    the whole create — flush included, not only the commit — in the IntegrityError->replay guard,
    so the UNIQUE violation (which fires at the flush right after db.add(order)) is caught and the
    loser replays, as docs/architecture.md section 5 promises.
    """
    import app.masters.service as masters_mod

    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user)
    sid = user_id("salesman_a")
    key = fresh_key("race")
    data = OrderCreate(
        customer_id=cust,
        order_date=date(2026, 11, 3),
        lines=[OrderLineIn(item_id=fg, qty=D("5"), uom="pkt")],
    )
    # Widen the window between the "does this key exist?" read and the commit, so both requests
    # pass the existence check before either commits and the UNIQUE race is really exercised.
    real_get_customer = masters_mod.get_customer

    def slow_get_customer(*args, **kwargs):
        time.sleep(0.4)
        return real_get_customer(*args, **kwargs)

    monkeypatch.setattr(masters_mod, "get_customer", slow_get_customer)

    def job(session):
        return create_order(session, key, data, session.get(AppUser, sid))

    results = _in_threads(job, job)
    assert orders_with_uuid(key) == 1  # the reassuring half: no double order, no double stock
    errors = [r for r in results if isinstance(r, Exception)]
    assert errors == [], f"a concurrent double-tap raised instead of replaying: {errors}"


def test_replay_by_another_user_is_refused(client, as_user) -> None:  # guard
    """Replay is scoped to the user who first used the key: a second salesman presenting
    salesman_a's Idempotency-Key and exact body is refused (403), not handed salesman_a's order.
    _replay() checks existing.user_id == the caller before returning the stored response.
    """
    fg = fg_with_stock(client, as_user)
    cust_a = make_customer(client, as_user, salesman="salesman_a")  # owned by salesman_a
    key = fresh_key("cross")
    mine = place(client, as_user, key, cust_a, fg, "10", salesman="salesman_a")
    assert mine.status_code == 201, mine.text
    # salesman_b replays A's key with A's exact body.
    body = {
        "customer_id": cust_a,
        "order_date": "2026-11-03",
        "lines": [{"item_id": fg, "qty": "10", "uom": "pkt"}],
    }
    headers = {**as_user("salesman_b"), "Idempotency-Key": key}
    stolen = client.post(f"{API}/orders", json=body, headers=headers)
    # Secure behaviour: salesman_b must not receive another salesman's order.
    assert stolen.status_code == 403, (
        f"salesman_b received order {stolen.json().get('id')} for customer "
        f"{stolen.json().get('customer_code')} via replay of salesman_a's key"
    )


# ---- 8. reversal symmetry ----------------------------------------------------------------


def _round_trip(client, as_user, qty, *, state="33", salesman="salesman_a"):
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user, state_code=state, salesman=salesman)
    before = balance(client, as_user, fg)
    order = place(client, as_user, fresh_key("rt"), cust, fg, qty, salesman=salesman).json()
    assert approve(client, as_user, order["id"]).status_code == 200
    inv = raise_invoice(client, as_user, order["id"]).json()
    assert dispatch(client, as_user, inv["id"]).status_code == 200
    after_dispatch = balance(client, as_user, fg)
    return fg, inv, before, after_dispatch


def test_cancel_restores_fg_qty_and_value_exactly(client, as_user) -> None:  # guard
    fg, inv, before, after_dispatch = _round_trip(client, as_user, "150")
    assert after_dispatch[0] == before[0] - D(150)  # stock really left on dispatch
    assert after_dispatch[1] < before[1]
    assert cancel(client, as_user, inv["id"]).status_code == 200
    restored = balance(client, as_user, fg)
    assert restored == before, f"cancel did not restore exactly: {restored} vs {before}"


def test_cancel_after_emptying_stock_restores_without_drift(client, as_user) -> None:  # guard
    """Dispatch every packet (WAC's emptying issue takes all remaining value), then cancel: the
    mirror must bring qty AND value back to exactly where they were (no WAC drift, no stranding)."""
    fg = fg_with_stock(client, as_user, pkts="300")
    cust = make_customer(client, as_user)
    before = balance(client, as_user, fg)
    order = place(client, as_user, fresh_key("empty"), cust, fg, "300").json()
    assert approve(client, as_user, order["id"]).status_code == 200
    inv = raise_invoice(client, as_user, order["id"]).json()
    assert dispatch(client, as_user, inv["id"]).status_code == 200
    assert balance(client, as_user, fg) == (D(0), 0)  # emptied, no value stranded
    assert cancel(client, as_user, inv["id"]).status_code == 200
    assert balance(client, as_user, fg) == before


def test_cancel_twice_is_refused(client, as_user) -> None:  # guard
    _fg, inv, _before, _after = _round_trip(client, as_user, "20")
    assert cancel(client, as_user, inv["id"]).status_code == 200
    again = cancel(client, as_user, inv["id"])
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "ALREADY_CANCELLED"


def test_cannot_redispatch_a_cancelled_invoice(client, as_user) -> None:  # guard
    _fg, inv, _before, _after = _round_trip(client, as_user, "20")
    assert cancel(client, as_user, inv["id"]).status_code == 200
    redispatch = dispatch(client, as_user, inv["id"])
    assert redispatch.status_code == 409, redispatch.text
    assert redispatch.json()["error"]["code"] == "INVOICE_CANCELLED"


def test_a_dispatch_movement_can_be_reversed_at_most_once(client, as_user, db) -> None:  # guard
    """reverses_id is UNIQUE: a second REVERSAL of the same dispatch movement must be rejected by
    the database. We ask inventory.post_reversals to mirror one dispatch movement twice in a single
    transaction (rolled back by the db fixture) and expect the UNIQUE index to raise."""
    from sqlalchemy.exc import IntegrityError

    from app.billing.models import CreditNote
    from app.inventory.models import MovementType, SourceType
    from app.inventory.service import ReversalLine, post_reversals

    _fg, inv, _before, _after = _round_trip(client, as_user, "20")
    dispatch_mv = db.scalar(
        select(StockMovement)
        .where(StockMovement.movement_type == MovementType.DISPATCH.value)
        .order_by(StockMovement.id.desc())
    )
    assert dispatch_mv is not None
    # A real credit_note source document, so the invariant-6 existence check passes.
    cn = CreditNote(
        invoice_id=inv["id"],
        cn_date=date(2026, 11, 5),
        taxable_paise=0,
        created_by=user_id("admin"),
    )
    db.add(cn)
    db.flush()
    with pytest.raises(IntegrityError):
        post_reversals(
            db,
            source_type=SourceType.CREDIT_NOTE,
            source_id=cn.id,
            movement_date=date(2026, 11, 5),
            user_id=user_id("admin"),
            lines=[
                ReversalLine(original_id=dispatch_mv.id, source_line_id=1),
                ReversalLine(original_id=dispatch_mv.id, source_line_id=1),
            ],
        )


# ---- 9. invoice numbering ----------------------------------------------------------------


def _approved_order(client, as_user, fg, cust, qty, on="2026-11-03"):
    order = place(client, as_user, fresh_key("num"), cust, fg, qty, on=on).json()
    assert approve(client, as_user, order["id"]).status_code == 200
    return order["id"]


def test_consecutive_invoices_in_one_fy_have_no_gap(client, as_user) -> None:  # guard
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user)
    seqs = []
    nos = []
    for _ in range(3):
        oid = _approved_order(client, as_user, fg, cust, "5")
        inv = raise_invoice(client, as_user, oid, on="2026-11-03").json()
        assert inv["fy"] == "2026-27"
        seqs.append(inv["seq"])
        nos.append(inv["invoice_no"])
    assert seqs == [seqs[0], seqs[0] + 1, seqs[0] + 2], seqs  # gapless, consecutive
    assert len(set(nos)) == 3  # unique
    assert nos == [f"FF/2026-27/{s:04d}" for s in seqs]


def test_invoice_date_decides_the_fy_at_the_april_boundary(client, as_user) -> None:  # guard
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user)
    march = raise_invoice(
        client, as_user, _approved_order(client, as_user, fg, cust, "5"), on="2027-03-31"
    ).json()
    april = raise_invoice(
        client, as_user, _approved_order(client, as_user, fg, cust, "5"), on="2027-04-01"
    ).json()
    assert march["fy"] == "2026-27", march["invoice_no"]
    assert april["fy"] == "2027-28", april["invoice_no"]
    assert march["invoice_no"].startswith("FF/2026-27/")
    assert april["invoice_no"].startswith("FF/2027-28/")


def test_a_rolled_back_invoice_does_not_consume_a_number(db) -> None:  # guard
    """A failed invoice must not leave a gap: the sequence bump lives in the invoice's transaction,
    so a rollback un-bumps it. We bump a brand-new FY's sequence, roll back, and confirm a fresh
    session sees no advance."""
    from app.billing.service import _next_seq

    fy = "2041-42"  # a year no other test touches
    assert _next_seq(db, fy) == 1
    db.rollback()
    with SessionLocal() as s:
        assert s.scalar(select(InvoiceSequence).where(InvoiceSequence.fy == fy)) is None


def test_concurrent_invoices_get_distinct_consecutive_numbers(
    client, as_user, monkeypatch
) -> None:  # guard
    """Two invoices raced for the same FY must serialise on the FOR UPDATE sequence row and come
    out with distinct, consecutive numbers (no duplicate, no gap)."""
    import app.billing.service as billing_mod

    fg = fg_with_stock(client, as_user, pkts="300")
    cust = make_customer(client, as_user)
    o1 = _approved_order(client, as_user, fg, cust, "5")
    o2 = _approved_order(client, as_user, fg, cust, "5")
    fy = "2026-27"
    with SessionLocal() as s:
        base = s.scalar(select(InvoiceSequence.last_seq).where(InvoiceSequence.fy == fy)) or 0
    real_invoice_no = billing_mod.gst.invoice_no

    def slow_invoice_no(*args, **kwargs):  # hold the seq lock a beat so the race is real
        time.sleep(0.4)
        return real_invoice_no(*args, **kwargs)

    monkeypatch.setattr(billing_mod.gst, "invoice_no", slow_invoice_no)
    admin_id = user_id("admin")

    def job(order_id):
        def run(session):
            return create_invoice(
                session,
                order_id,
                InvoiceCreate(invoice_date=date(2026, 11, 3)),
                session.get(AppUser, admin_id),
            )

        return run

    results = _in_threads(job(o1), job(o2))
    for r in results:
        assert not isinstance(r, Exception), r
    seqs = sorted(r.seq for r in results)
    assert seqs == [base + 1, base + 2], seqs  # distinct and consecutive
    assert len({r.invoice_no for r in results}) == 2  # no duplicate number


# ---- backdated dispatch ------------------------------------------------------------------


def test_dispatch_before_the_goods_existed_is_refused(client, as_user) -> None:  # guard
    """A dispatch dated before the finished goods were ever in stock must fail the ledger's
    as-of-date balance check (the P4 backdating guard, now via the billing path)."""
    fg = fg_with_stock(client, as_user)  # produced on 2026-11-02 (sandbox default)
    cust = make_customer(client, as_user)
    oid = _approved_order(client, as_user, fg, cust, "10")
    inv = raise_invoice(client, as_user, oid, on="2026-11-03").json()
    early = dispatch(client, as_user, inv["id"], on="2026-11-01")  # before any stock existed
    assert early.status_code == 409, early.text
    assert early.json()["error"]["code"] == "INSUFFICIENT_STOCK"


# ---- 11. standing invariants (runs before the destructive backdating finding) ------------


def test_zz_ledger_reconciles_after_sales_and_billing(client, as_user) -> None:  # guard
    from app.masters.models import Item

    with SessionLocal() as s:
        assert ledger_problems(s) == []  # reconcile clean + no orphan movements
        for item_id in s.scalars(select(Item.id)).all():
            q, v = s.execute(
                text(
                    "SELECT COALESCE(SUM(qty),0), COALESCE(SUM(value_paise),0)"
                    " FROM stock_movement WHERE item_id = :i"
                ),
                {"i": item_id},
            ).one()
            assert balance(client, as_user, item_id) == (D(q), int(v))
        # Every dispatch line nets to exactly its DISPATCH movement quantity.
        bad = s.execute(
            text(
                """
            SELECT 'dispatch_line ' || dl.id FROM dispatch_line dl
              LEFT JOIN stock_movement m ON m.source_type = 'dispatch'
               AND m.source_id = dl.dispatch_id AND m.item_id = dl.item_id
               AND m.movement_type = 'DISPATCH'
             GROUP BY dl.id, dl.qty
            HAVING SUM(-m.qty) <> dl.qty
            """
            )
        ).all()
        assert bad == []
        # reverses_id is unique where present (a movement reversed at most once).
        dupes = s.scalar(
            select(func.count()).select_from(
                select(StockMovement.reverses_id)
                .where(StockMovement.reverses_id.is_not(None))
                .group_by(StockMovement.reverses_id)
                .having(func.count() > 1)
                .subquery()
            )
        )
        assert dupes == 0


def test_backdated_out_of_order_dispatch_is_refused(client, as_user) -> None:  # guard
    """A dispatch backdated before an already-posted later dispatch must be refused, not committed.
    dispatch_date is admin-supplied, and post_movements now checks the CURRENT per-lot balance as
    well as the as-of-date one. Here the first batch's lot has only 100 pkt left now (300 made,
    200 already dispatched on 11-10); a second 200-pkt dispatch backdated to 11-05 would make that
    lot -100 on 11-10. It is rejected with INSUFFICIENT_STOCK, so the committed ledger stays
    non-negative and reconcile stays clean (the earlier 'drives stock negative' finding, fixed).
    """
    s = sandbox(client, as_user)
    buy(client, as_user, [(s.raws[0], "2", "kg", 4000)], on="2026-11-01")
    r1 = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")], on="2026-11-02").json()
    assert (
        client.post(
            f"{API}/production-runs/{r1['id']}/complete",
            json={"output_qty": "300"},
            headers=as_user("production"),
        ).status_code
        == 200
    )
    fg = s.fg
    cust = make_customer(client, as_user)

    # Order 1: 200 pkt from the first batch, dispatched LATE (11-10). The lot now holds 100.
    o1 = _approved_order(client, as_user, fg, cust, "200", on="2026-11-02")
    inv1 = raise_invoice(client, as_user, o1, on="2026-11-03").json()
    assert dispatch(client, as_user, inv1["id"], on="2026-11-10").status_code == 200

    # A second batch on 11-20, so the whole-item total is comfortably positive.
    r2 = start(client, as_user, s.bom, [(s.raws[0], "1", "kg")], on="2026-11-20").json()
    assert (
        client.post(
            f"{API}/production-runs/{r2['id']}/complete",
            json={"output_qty": "300"},
            headers=as_user("production"),
        ).status_code
        == 200
    )

    # Order 2: 200 pkt dispatched EARLY (11-05) out of order. As of 11-05 the first batch shows 300,
    # but it currently has only 100 left, so the dispatch is refused instead of going negative.
    o2 = _approved_order(client, as_user, fg, cust, "200", on="2026-11-02")
    inv2 = raise_invoice(client, as_user, o2, on="2026-11-03").json()
    early = dispatch(client, as_user, inv2["id"], on="2026-11-05")
    assert early.status_code == 409, early.text
    assert early.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    # The committed ledger is non-negative on every date and reconcile is clean.
    assert balance(client, as_user, fg, as_of="2026-11-10")[0] == D(100)
    with SessionLocal() as session:
        assert ledger_problems(session) == []
