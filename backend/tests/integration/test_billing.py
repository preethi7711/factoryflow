"""Billing through the API: invoice from an approved order, gapless FY numbering, dispatch that
moves stock, and cancellation via a credit note whose reversals restore stock and value exactly
(PROBLEM.md section 5 step 5, plus the cancellation path invariant 7 requires).

Each test reseeds (opening finished goods = 50 packets).
"""

import uuid
from decimal import Decimal

import pytest

from app import seed
from app.core.config import get_settings
from tests.conftest import reset_database

API = "/api/v1"
D = Decimal
DT = "2026-11-03"


@pytest.fixture
def fresh(client):
    reset_database()
    seed.run()
    return client


def _headers(client, username: str) -> dict[str, str]:
    password = get_settings().seed_demo_password
    r = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _id(client, resource: str, code: str, headers: dict) -> int:
    return client.get(f"{API}/{resource}", params={"code": code}, headers=headers).json()[0]["id"]


def _balance(client, item_id: int, headers: dict) -> tuple[Decimal, int]:
    body = client.get(f"{API}/stock/balance/{item_id}", headers=headers).json()
    return D(body["qty"]), body["value_paise"]


def _approved_order(client, customer_code: str, qty: str, salesman: str) -> int:
    sales = _headers(client, salesman)
    admin = _headers(client, "admin")
    item_id = _id(client, "items", "MURUKKU-200G", admin)
    body = {
        "customer_id": _id(client, "customers", customer_code, admin),
        "order_date": DT,
        "lines": [{"item_id": item_id, "qty": qty, "uom": "pkt"}],
    }
    order_id = client.post(
        f"{API}/orders", json=body, headers={**sales, "Idempotency-Key": str(uuid.uuid4())}
    ).json()["id"]
    assert client.post(f"{API}/orders/{order_id}/approve", headers=admin).status_code == 200
    return order_id


def test_invoice_from_approved_order_numbers_and_taxes(fresh) -> None:
    admin = _headers(fresh, "admin")
    order_id = _approved_order(fresh, "RETAILER-A", "40", "salesman_a")
    r = fresh.post(f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin)
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["invoice_no"] == "FF/2026-27/0001"
    assert inv["supply_type"] == "INTRA"
    assert inv["taxable_paise"] == 200000
    assert (inv["cgst_paise"], inv["sgst_paise"], inv["igst_paise"]) == (5000, 5000, 0)
    assert inv["total_paise"] == 210000
    assert inv["status"] == "ISSUED"


def test_fy_numbering_is_gapless(fresh) -> None:
    admin = _headers(fresh, "admin")
    first = _approved_order(fresh, "RETAILER-A", "10", "salesman_a")
    second = _approved_order(fresh, "RETAILER-A", "10", "salesman_a")
    no1 = fresh.post(
        f"{API}/orders/{first}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()
    no2 = fresh.post(
        f"{API}/orders/{second}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()
    assert no1["invoice_no"] == "FF/2026-27/0001"
    assert no2["invoice_no"] == "FF/2026-27/0002"


def test_cannot_invoice_an_unapproved_order(fresh) -> None:
    sales = _headers(fresh, "salesman_a")
    admin = _headers(fresh, "admin")
    item_id = _id(fresh, "items", "MURUKKU-200G", admin)
    body = {
        "customer_id": _id(fresh, "customers", "RETAILER-A", admin),
        "order_date": DT,
        "lines": [{"item_id": item_id, "qty": "10", "uom": "pkt"}],
    }
    order_id = fresh.post(
        f"{API}/orders", json=body, headers={**sales, "Idempotency-Key": str(uuid.uuid4())}
    ).json()["id"]
    r = fresh.post(f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ORDER_NOT_APPROVED"


def test_inter_state_invoice_charges_igst(fresh) -> None:
    admin = _headers(fresh, "admin")
    order_id = _approved_order(fresh, "DISTRIBUTOR-B", "20", "salesman_b")
    inv = fresh.post(
        f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()
    assert inv["supply_type"] == "INTER"
    assert inv["taxable_paise"] == 100000
    assert (inv["cgst_paise"], inv["sgst_paise"], inv["igst_paise"]) == (0, 0, 5000)


def test_dispatch_moves_stock_and_cannot_repeat(fresh) -> None:
    admin = _headers(fresh, "admin")
    item_id = _id(fresh, "items", "MURUKKU-200G", admin)
    order_id = _approved_order(fresh, "RETAILER-A", "20", "salesman_a")
    invoice_id = fresh.post(
        f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()["id"]
    before, _ = _balance(fresh, item_id, admin)
    r = fresh.post(
        f"{API}/invoices/{invoice_id}/dispatch", json={"dispatch_date": DT}, headers=admin
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "DISPATCHED"
    after, _ = _balance(fresh, item_id, admin)
    assert after == before - 20
    # a second dispatch is refused
    again = fresh.post(
        f"{API}/invoices/{invoice_id}/dispatch", json={"dispatch_date": DT}, headers=admin
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_DISPATCHED"


def test_cancel_reverses_a_dispatch_exactly(fresh) -> None:
    admin = _headers(fresh, "admin")
    acct = _headers(fresh, "accountant")
    item_id = _id(fresh, "items", "MURUKKU-200G", admin)
    order_id = _approved_order(fresh, "RETAILER-A", "20", "salesman_a")
    invoice_id = fresh.post(
        f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()["id"]
    before_qty, before_value = _balance(fresh, item_id, admin)  # on hand before dispatch
    fresh.post(f"{API}/invoices/{invoice_id}/dispatch", json={"dispatch_date": DT}, headers=admin)

    r = fresh.post(
        f"{API}/invoices/{invoice_id}/cancel",
        json={"cn_date": DT, "reason": "customer returned the goods"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["invoice"]["status"] == "CANCELLED"
    assert body["credit_note"]["cn_no"] == "CN/2026-27/0001"
    assert body["credit_note"]["total_paise"] == 105000  # 20 x 50 = 1000 + 5% = 1050

    after_qty, after_value = _balance(fresh, item_id, admin)
    assert (after_qty, after_value) == (before_qty, before_value)  # restored exactly (WAC symmetry)
    assert fresh.get(f"{API}/stock/reconcile", headers=acct).json()["problems"] == []
    # a second cancel is refused
    again = fresh.post(f"{API}/invoices/{invoice_id}/cancel", json={"cn_date": DT}, headers=admin)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_CANCELLED"


def test_cancel_an_issued_invoice_before_dispatch(fresh) -> None:
    admin = _headers(fresh, "admin")
    order_id = _approved_order(fresh, "RETAILER-A", "20", "salesman_a")
    invoice_id = fresh.post(
        f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=admin
    ).json()["id"]
    r = fresh.post(f"{API}/invoices/{invoice_id}/cancel", json={"cn_date": DT}, headers=admin)
    assert r.status_code == 200, r.text  # nothing to reverse, just cancelled
    assert r.json()["invoice"]["status"] == "CANCELLED"


@pytest.mark.parametrize("username", ["salesman_a", "accountant", "production"])
def test_only_admin_can_invoice(fresh, username) -> None:
    other = _headers(fresh, username)
    order_id = _approved_order(fresh, "RETAILER-A", "10", "salesman_a")
    r = fresh.post(f"{API}/orders/{order_id}/invoice", json={"invoice_date": DT}, headers=other)
    assert r.status_code == 403
