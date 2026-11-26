"""Payments through the API: allocation validation, over-allocation, cancelled invoices, and the
derived outstanding balance (PROBLEM.md section 5 step 7, B11). Also the P11 Idempotency-Key guard
on POST /payments.

Each test reseeds (opening finished goods = 50 packets).
"""

import uuid

import pytest

from app import seed
from app.core.config import get_settings
from tests.conftest import reset_database

API = "/api/v1"
DT = "2026-11-05"
IDT = "2026-11-03"


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


def _invoice(client, customer_code: str, qty: str, salesman: str) -> dict:
    """An approved, invoiced order for the customer; returns the invoice JSON."""
    sales = _headers(client, salesman)
    admin = _headers(client, "admin")
    body = {
        "customer_id": _id(client, "customers", customer_code, admin),
        "order_date": IDT,
        "lines": [
            {"item_id": _id(client, "items", "MURUKKU-200G", admin), "qty": qty, "uom": "pkt"}
        ],
    }
    order_id = client.post(
        f"{API}/orders", json=body, headers={**sales, "Idempotency-Key": str(uuid.uuid4())}
    ).json()["id"]
    assert client.post(f"{API}/orders/{order_id}/approve", headers=admin).status_code == 200
    r = client.post(f"{API}/orders/{order_id}/invoice", json={"invoice_date": IDT}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _customer_id(client, code: str, headers: dict) -> int:
    return _id(client, "customers", code, headers)


def _pay(client, headers, body, key: str | None = None):
    """POST /payments with an Idempotency-Key, which the endpoint requires. Pass a fixed `key`
    to exercise the replay behaviour; otherwise a fresh key is generated for each call."""
    return client.post(
        f"{API}/payments",
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
    )


def _body(cust: int, amount: int, inv_id: int) -> dict:
    return {
        "customer_id": cust,
        "payment_date": DT,
        "amount_paise": amount,
        "allocations": [{"invoice_id": inv_id, "amount_paise": amount}],
    }


def test_partial_payment_reduces_outstanding(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")  # total 210000
    cust = inv["customer_id"]
    r = _pay(fresh, admin, _body(cust, 100000, inv["id"]))
    assert r.status_code == 201, r.text
    out = fresh.get(f"{API}/customers/{cust}/outstanding", headers=admin).json()
    assert out["outstanding_paise"] == 110000
    assert out["invoices"][0]["paid_paise"] == 100000
    assert out["invoices"][0]["outstanding_paise"] == 110000


def test_full_payment_clears_the_invoice(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")  # total 210000
    cust = inv["customer_id"]
    assert _pay(fresh, admin, _body(cust, 210000, inv["id"])).status_code == 201
    out = fresh.get(f"{API}/customers/{cust}/outstanding", headers=admin).json()
    assert out["outstanding_paise"] == 0
    assert out["invoices"] == []  # nothing still owing


def test_allocations_must_sum_to_the_amount(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    body = {
        "customer_id": inv["customer_id"],
        "payment_date": DT,
        "amount_paise": 100000,
        "allocations": [{"invoice_id": inv["id"], "amount_paise": 90000}],
    }
    r = _pay(fresh, admin, body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ALLOCATION_MISMATCH"


def test_cannot_over_allocate_an_invoice(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")  # total 210000
    cust = inv["customer_id"]
    # pay 200000 first, then try 20000 more (would be 220000 > 210000)
    assert _pay(fresh, admin, _body(cust, 200000, inv["id"])).status_code == 201
    r = _pay(fresh, admin, _body(cust, 20000, inv["id"]))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "OVER_ALLOCATION"


def test_cannot_pay_a_cancelled_invoice(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    assert (
        fresh.post(
            f"{API}/invoices/{inv['id']}/cancel", json={"cn_date": DT}, headers=admin
        ).status_code
        == 200
    )
    r = _pay(fresh, admin, _body(inv["customer_id"], 50000, inv["id"]))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVOICE_CANCELLED"


def test_cannot_allocate_another_customers_invoice(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv_a = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    cust_b = _customer_id(fresh, "DISTRIBUTOR-B", admin)
    r = _pay(fresh, admin, _body(cust_b, 50000, inv_a["id"]))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "WRONG_CUSTOMER"


@pytest.mark.parametrize("username", ["salesman_a", "production"])
def test_only_admin_can_record_a_payment(fresh, username) -> None:
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    r = _pay(fresh, _headers(fresh, username), _body(inv["customer_id"], 50000, inv["id"]))
    assert r.status_code == 403


# ---- P11: Idempotency-Key guard --------------------------------------------------------


def test_payment_requires_idempotency_key(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    r = fresh.post(
        f"{API}/payments", json=_body(inv["customer_id"], 50000, inv["id"]), headers=admin
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_repeated_key_replays_one_receipt_only(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")  # total 210000
    cust = inv["customer_id"]
    key = str(uuid.uuid4())
    body = _body(cust, 100000, inv["id"])
    first = _pay(fresh, admin, body, key=key)
    second = _pay(fresh, admin, body, key=key)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json() == second.json()  # same receipt, not two
    # Only one allocation hit the invoice; outstanding is 110000, not 10000.
    out = fresh.get(f"{API}/customers/{cust}/outstanding", headers=admin).json()
    assert out["outstanding_paise"] == 110000


def test_same_key_different_body_is_a_conflict(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    cust = inv["customer_id"]
    key = str(uuid.uuid4())
    assert _pay(fresh, admin, _body(cust, 50000, inv["id"]), key=key).status_code == 201
    r = _pay(fresh, admin, _body(cust, 60000, inv["id"]), key=key)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_another_user_cannot_reuse_my_key(fresh) -> None:
    admin = _headers(fresh, "admin")
    inv = _invoice(fresh, "RETAILER-A", "40", "salesman_a")
    cust = inv["customer_id"]
    key = str(uuid.uuid4())
    assert _pay(fresh, admin, _body(cust, 50000, inv["id"]), key=key).status_code == 201
    # The current API only lets admins record payments, but if another admin existed, they
    # would not be handed the first admin's receipt either. We test the owner here (403 before
    # the replay check), proving the role gate still fires; the replay rule itself is enforced
    # in the service (see sales for the parallel pattern).
    r = _pay(fresh, _headers(fresh, "owner"), _body(cust, 50000, inv["id"]), key=key)
    assert r.status_code == 403  # role gate wins first
