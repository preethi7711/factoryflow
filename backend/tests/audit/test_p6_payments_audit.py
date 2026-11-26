"""Hostile audit after P6 (payments + allocation + derived outstanding). Every test here is a
`# guard`: it passes and proves a money-integrity control holds. No finding was confirmed — P6
survived every attack below, so the committed sum of allocations for an invoice never exceeds its
total, outstanding always equals invoice.total - SUM(allocations) over non-cancelled invoices, and
payments touch no stock.

In scope for P6 (money integrity): over-allocation (one payment, across payments, concurrent
double-pay), allocation integrity (sum mismatch, non-positive, duplicate invoice, wrong customer,
unknown invoice), cancelled-invoice payment, cancel vs a prior payment, append-only payment rows,
and the standing invariant that the stock ledger is untouched by payments.

Helpers (_in_threads/user_id) come from the P4 suite; the billing helpers
(fg_with_stock/make_customer/place/approve/raise_invoice/cancel/fresh_key) from the P5 suite, so
the fixtures and style match exactly.
"""

import time
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.auth.models import AppUser
from app.core.db import SessionLocal, engine
from app.payments.schemas import PaymentAllocationIn, PaymentCreate
from app.payments.service import record_payment
from tests.audit.test_p4_ledger_audit import _in_threads, user_id
from tests.audit.test_p5_sales_billing_audit import (
    approve,
    cancel,
    fg_with_stock,
    fresh_key,
    make_customer,
    place,
    raise_invoice,
)
from tests.invariants import ledger_problems

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"
D = Decimal


# ---- helpers (all through the real API) --------------------------------------------------


def billed(client, as_user, qty="10", *, state="33", salesman="salesman_a"):
    """One priced, approved, raised invoice (not dispatched — payment only needs an invoice).
    FG is priced 5000 paise at GST 5%, so qty 10 intra-state -> taxable 50000 + 1250 + 1250 =
    52500 paise total."""
    fg = fg_with_stock(client, as_user)
    cust = make_customer(client, as_user, state_code=state, salesman=salesman)
    oid = place(client, as_user, fresh_key("pay"), cust, fg, qty, salesman=salesman).json()["id"]
    assert approve(client, as_user, oid).status_code == 200
    inv = raise_invoice(client, as_user, oid).json()
    return cust, inv


def pay(client, as_user, customer_id, amount, allocations, *, on="2026-11-05", who="admin"):
    body = {
        "customer_id": customer_id,
        "payment_date": on,
        "amount_paise": amount,
        "allocations": allocations,
    }
    headers = {**as_user(who), "Idempotency-Key": fresh_key("pay")}
    return client.post(f"{API}/payments", json=body, headers=headers)


def one_alloc(invoice_id, amount):
    return [{"invoice_id": invoice_id, "amount_paise": amount}]


def outstanding(client, as_user, customer_id, who="admin"):
    return client.get(f"{API}/customers/{customer_id}/outstanding", headers=as_user(who))


def allocated_in_db(invoice_id: int) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT COALESCE(SUM(amount_paise),0) FROM payment_allocation WHERE invoice_id=:i"
            ),
            {"i": invoice_id},
        ).scalar_one()


def movement_count() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM stock_movement")).scalar_one()


# ---- outstanding is derived and correct --------------------------------------------------


def test_part_payment_leaves_the_exact_remainder_outstanding(client, as_user) -> None:  # guard
    """B11-shaped: a part payment makes outstanding == invoice.total - paid, to the paisa, and the
    reported number matches the SUM of the payment_allocation rows that back it."""
    cust, inv = billed(client, as_user, "10")  # total 52500
    total = inv["total_paise"]
    r = pay(client, as_user, cust, 40000, one_alloc(inv["id"], 40000))
    assert r.status_code == 201, r.text
    out = outstanding(client, as_user, cust).json()
    assert out["outstanding_paise"] == total - 40000
    assert allocated_in_db(inv["id"]) == 40000  # reported number == the rows that back it
    row = next(i for i in out["invoices"] if i["invoice_id"] == inv["id"])
    assert (row["total_paise"], row["paid_paise"], row["outstanding_paise"]) == (
        total,
        40000,
        total - 40000,
    )


def test_full_payment_clears_outstanding_to_zero(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    assert pay(client, as_user, cust, total, one_alloc(inv["id"], total)).status_code == 201
    out = outstanding(client, as_user, cust).json()
    assert out["outstanding_paise"] == 0
    assert out["invoices"] == []  # a fully-paid invoice drops out of the owing list
    assert allocated_in_db(inv["id"]) == total


# ---- over-allocation ---------------------------------------------------------------------


def test_single_payment_beyond_the_total_is_refused(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    r = pay(client, as_user, cust, total + 1, one_alloc(inv["id"], total + 1))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "OVER_ALLOCATION"
    assert allocated_in_db(inv["id"]) == 0  # nothing committed


def test_second_payment_cannot_push_past_the_total(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    first = pay(client, as_user, cust, total - 100, one_alloc(inv["id"], total - 100))
    assert first.status_code == 201, first.text
    # a second payment of 200 would push the invoice 100 paise past its total
    r = pay(client, as_user, cust, 200, one_alloc(inv["id"], 200))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "OVER_ALLOCATION"
    assert allocated_in_db(inv["id"]) == total - 100
    assert outstanding(client, as_user, cust).json()["outstanding_paise"] == 100


def test_concurrent_double_pay_cannot_over_allocate(client, as_user, monkeypatch) -> None:  # guard
    """Two payments racing to allocate the FULL total to the same invoice: the FOR UPDATE row lock
    must serialise them, so exactly one commits and the other sees the committed allocation and is
    refused with OVER_ALLOCATION. The committed sum never exceeds the invoice total."""
    import app.masters.service as masters_mod

    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    # Widen the window before the lock so both callers are inside record_payment at once, then race
    # for the invoice's FOR UPDATE row.
    real_get_customer = masters_mod.get_customer

    def slow_get_customer(*args, **kwargs):
        time.sleep(0.4)
        return real_get_customer(*args, **kwargs)

    monkeypatch.setattr(masters_mod, "get_customer", slow_get_customer)
    admin_id = user_id("admin")
    data = PaymentCreate(
        customer_id=cust,
        payment_date=date(2026, 11, 5),
        amount_paise=total,
        allocations=[PaymentAllocationIn(invoice_id=inv["id"], amount_paise=total)],
    )

    def job(session):
        # Each thread uses its own idempotency key so the test exercises over-allocation (not the
        # replay guard, which is covered by the API-level tests).
        return record_payment(session, fresh_key("pay"), data, session.get(AppUser, admin_id))

    results = _in_threads(job, job)
    ok = [r for r in results if not isinstance(r, Exception)]
    errs = [r for r in results if isinstance(r, Exception)]
    assert len(ok) == 1, f"expected exactly one payment to win: {results}"
    assert len(errs) == 1 and getattr(errs[0], "code", None) == "OVER_ALLOCATION", errs
    assert allocated_in_db(inv["id"]) == total  # not 2 x total


# ---- allocation integrity ----------------------------------------------------------------


def test_allocations_must_sum_to_the_amount(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    r = pay(client, as_user, cust, 50000, one_alloc(inv["id"], 40000))  # 40000 != 50000
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "ALLOCATION_MISMATCH"
    assert allocated_in_db(inv["id"]) == 0


@pytest.mark.parametrize("amount", [0, -5000])
def test_non_positive_amount_is_refused(client, as_user, amount) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    r = pay(client, as_user, cust, amount, one_alloc(inv["id"], amount))
    assert r.status_code == 422, r.text  # schema Field(gt=0) + DB CHECK amount_positive
    assert allocated_in_db(inv["id"]) == 0


def test_same_invoice_twice_in_one_payment_is_refused(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    allocs = [
        {"invoice_id": inv["id"], "amount_paise": 10000},
        {"invoice_id": inv["id"], "amount_paise": 10000},
    ]
    r = pay(client, as_user, cust, 20000, allocs)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "DUPLICATE_ALLOCATION"
    assert allocated_in_db(inv["id"]) == 0


def test_cannot_allocate_another_customers_invoice(client, as_user) -> None:  # guard
    _cust_a, inv_a = billed(client, as_user, "10", salesman="salesman_a")
    cust_b = make_customer(client, as_user, state_code="33", salesman="salesman_b")
    r = pay(client, as_user, cust_b, 10000, one_alloc(inv_a["id"], 10000))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "WRONG_CUSTOMER"
    assert allocated_in_db(inv_a["id"]) == 0


def test_cannot_allocate_a_nonexistent_invoice(client, as_user) -> None:  # guard
    cust, _inv = billed(client, as_user, "10")
    r = pay(client, as_user, cust, 10000, one_alloc(2_000_000_000, 10000))
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "NOT_FOUND"


# ---- cancelled invoices ------------------------------------------------------------------


def test_paying_a_cancelled_invoice_is_refused(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    assert cancel(client, as_user, inv["id"]).status_code == 200
    r = pay(client, as_user, cust, 10000, one_alloc(inv["id"], 10000))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INVOICE_CANCELLED"
    assert allocated_in_db(inv["id"]) == 0


def test_cancelling_after_a_payment_drops_it_from_outstanding(client, as_user) -> None:  # guard
    """A part payment lands, then the invoice is cancelled: outstanding must exclude the cancelled
    invoice entirely (not a negative, not a stale balance), because outstanding sums only
    non-cancelled invoices."""
    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    assert pay(client, as_user, cust, 40000, one_alloc(inv["id"], 40000)).status_code == 201
    assert outstanding(client, as_user, cust).json()["outstanding_paise"] == total - 40000
    assert cancel(client, as_user, inv["id"]).status_code == 200
    out = outstanding(client, as_user, cust).json()
    assert out["outstanding_paise"] == 0
    assert all(i["invoice_id"] != inv["id"] for i in out["invoices"])


# ---- append-only payment rows ------------------------------------------------------------


def test_payment_rows_cannot_be_changed_by_sql(client, as_user) -> None:  # guard
    """payment and payment_allocation carry the same append-only triggers as the ledger: no UPDATE,
    DELETE or TRUNCATE. An attacker who edited an allocation amount could otherwise fabricate or
    erase outstanding; the DB refuses it."""
    cust, inv = billed(client, as_user, "10")
    r = pay(client, as_user, cust, 40000, one_alloc(inv["id"], 40000))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    statements = [
        f"UPDATE payment SET amount_paise = 1 WHERE id = {pid}",
        f"DELETE FROM payment WHERE id = {pid}",
        "TRUNCATE payment CASCADE",
        f"UPDATE payment_allocation SET amount_paise = 1 WHERE payment_id = {pid}",
        f"DELETE FROM payment_allocation WHERE payment_id = {pid}",
        "TRUNCATE payment_allocation CASCADE",
    ]
    for sql in statements:
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
            conn.execute(text(sql))
    assert allocated_in_db(inv["id"]) == 40000  # untouched after every attempt


# ---- RBAC --------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["salesman_a", "production", "accountant", "owner"])
def test_only_admin_records_payments(client, as_user, who) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    r = pay(client, as_user, cust, 10000, one_alloc(inv["id"], 10000), who=who)
    assert r.status_code == 403, r.text
    assert allocated_in_db(inv["id"]) == 0


@pytest.mark.parametrize("who", ["salesman_a", "production"])
def test_sales_and_production_cannot_read_outstanding(client, as_user, who) -> None:  # guard
    cust, _inv = billed(client, as_user, "10")
    assert outstanding(client, as_user, cust, who=who).status_code == 403


# ---- standing invariant: payments touch no stock -----------------------------------------


def test_recording_a_payment_posts_nothing_to_the_ledger(client, as_user) -> None:  # guard
    cust, inv = billed(client, as_user, "10")
    total = inv["total_paise"]
    before = movement_count()
    assert pay(client, as_user, cust, total, one_alloc(inv["id"], total)).status_code == 201
    assert movement_count() == before  # not one new movement
    with SessionLocal() as s:
        assert ledger_problems(s) == []  # reconcile clean + no orphan movements
