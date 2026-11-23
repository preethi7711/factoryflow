"""Sales orders through the API: server-side pricing, the Idempotency-Key guard, per-salesman
access, the approval stock-cover check and the GST tax preview (PROBLEM.md section 5 steps 4, 6).

Each test reseeds, because approving an order reserves finished goods and would otherwise change
what a later test sees on hand.
"""

import uuid
from decimal import Decimal

import pytest

from app import seed
from app.core.config import get_settings
from tests.conftest import reset_database

API = "/api/v1"
D = Decimal
ORDER_DATE = "2026-11-03"


@pytest.fixture
def fresh(client):
    """A freshly seeded database per test (opening finished goods = 50 packets)."""
    reset_database()
    seed.run()
    return client


def _headers(client, username: str) -> dict[str, str]:
    password = get_settings().seed_demo_password
    r = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _customer_id(client, code: str, headers: dict) -> int:
    return client.get(f"{API}/customers", params={"code": code}, headers=headers).json()[0]["id"]


def _murukku_id(client, headers: dict) -> int:
    # Salesmen can't read /items (costs), but they can read the price list.
    rows = client.get(f"{API}/price-list", headers=headers).json()
    return next(r["item_id"] for r in rows if r["code"] == "MURUKKU-200G")


def _order_body(client, customer_code: str, qty: str, headers: dict) -> dict:
    return {
        "customer_id": _customer_id(client, customer_code, headers),
        "order_date": ORDER_DATE,
        "lines": [{"item_id": _murukku_id(client, headers), "qty": qty, "uom": "pkt"}],
    }


def _key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


def test_order_is_priced_by_the_server(fresh) -> None:
    sales = _headers(fresh, "salesman_a")
    body = _order_body(fresh, "RETAILER-A", "40", sales)
    r = fresh.post(f"{API}/orders", json=body, headers={**sales, **_key()})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "PENDING"
    line = out["lines"][0]
    assert line["unit_price_paise"] == 5000  # from the price list, not the request
    assert line["taxable_paise"] == 200000
    assert out["taxable_paise"] == 200000


def test_missing_idempotency_key_is_rejected(fresh) -> None:
    sales = _headers(fresh, "salesman_a")
    body = _order_body(fresh, "RETAILER-A", "10", sales)
    r = fresh.post(f"{API}/orders", json=body, headers=sales)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_key_same_body_replays_the_first_order(fresh) -> None:
    sales = _headers(fresh, "salesman_a")
    body = _order_body(fresh, "RETAILER-A", "10", sales)
    key = _key()
    first = fresh.post(f"{API}/orders", json=body, headers={**sales, **key})
    second = fresh.post(f"{API}/orders", json=body, headers={**sales, **key})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]  # replayed, not a second order
    assert len(fresh.get(f"{API}/orders", headers=sales).json()) == 1


def test_same_key_different_body_is_a_conflict(fresh) -> None:
    sales = _headers(fresh, "salesman_a")
    key = _key()
    fresh.post(
        f"{API}/orders",
        json=_order_body(fresh, "RETAILER-A", "10", sales),
        headers={**sales, **key},
    )
    clash = fresh.post(
        f"{API}/orders",
        json=_order_body(fresh, "RETAILER-A", "11", sales),
        headers={**sales, **key},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_salesman_cannot_order_for_another_salesmans_customer(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    body = _order_body(fresh, "DISTRIBUTOR-B", "10", sales_a)  # B belongs to salesman_b
    r = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_salesman_cannot_read_another_salesmans_order(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    sales_b = _headers(fresh, "salesman_b")
    body = _order_body(fresh, "RETAILER-A", "10", sales_a)
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()}).json()["id"]
    assert fresh.get(f"{API}/orders/{order_id}", headers=sales_b).status_code == 403
    assert fresh.get(f"{API}/orders", headers=sales_b).json() == []  # list is scoped per salesman


def test_salesman_cannot_approve_even_their_own_order(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    body = _order_body(fresh, "RETAILER-A", "10", sales_a)
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()}).json()["id"]
    assert fresh.post(f"{API}/orders/{order_id}/approve", headers=sales_a).status_code == 403


def test_approve_within_cover_succeeds(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    admin = _headers(fresh, "admin")
    body = _order_body(fresh, "RETAILER-A", "40", sales_a)  # 40 <= 50 on hand
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()}).json()["id"]
    r = fresh.post(f"{API}/orders/{order_id}/approve", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"


def test_over_approval_reports_the_shortage(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    admin = _headers(fresh, "admin")
    body = _order_body(fresh, "RETAILER-A", "60", sales_a)  # 60 > 50 on hand
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()}).json()["id"]
    r = fresh.post(f"{API}/orders/{order_id}/approve", headers=admin)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "INSUFFICIENT_STOCK"
    assert D(err["details"]["requested"]) == 60
    assert D(err["details"]["available"]) == 50
    assert D(err["details"]["shortage"]) == 10


def test_tax_preview_is_intra_state_for_a_tamil_nadu_customer(fresh) -> None:
    sales_a = _headers(fresh, "salesman_a")
    admin = _headers(fresh, "admin")
    body = _order_body(fresh, "RETAILER-A", "40", sales_a)
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_a, **_key()}).json()["id"]
    p = fresh.get(f"{API}/orders/{order_id}/tax-preview", headers=admin).json()
    assert p["supply_type"] == "INTRA"
    assert (p["cgst_paise"], p["sgst_paise"], p["igst_paise"]) == (5000, 5000, 0)
    assert p["total_paise"] == 210000


def test_tax_preview_is_inter_state_for_a_karnataka_customer(fresh) -> None:
    sales_b = _headers(fresh, "salesman_b")
    admin = _headers(fresh, "admin")
    body = _order_body(fresh, "DISTRIBUTOR-B", "40", sales_b)
    order_id = fresh.post(f"{API}/orders", json=body, headers={**sales_b, **_key()}).json()["id"]
    p = fresh.get(f"{API}/orders/{order_id}/tax-preview", headers=admin).json()
    assert p["supply_type"] == "INTER"
    assert (p["cgst_paise"], p["sgst_paise"], p["igst_paise"]) == (0, 0, 10000)
    assert p["total_paise"] == 210000
