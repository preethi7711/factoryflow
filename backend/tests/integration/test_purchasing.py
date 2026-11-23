"""Purchases: one lot per line, stocked in base units at the quoted rate, input GST not costed."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.db import engine

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"
D = Decimal


def _id(client, headers, resource: str, code: str) -> int:
    return client.get(f"{API}/{resource}", params={"code": code}, headers=headers).json()[0]["id"]


def _balance(client, headers, item_id: int) -> tuple[Decimal, int]:
    body = client.get(f"{API}/stock/balance/{item_id}", headers=headers).json()
    return D(body["qty"]), body["value_paise"]


def _purchase(client, headers, **line) -> dict:
    flour = _id(client, headers, "items", "FLOUR")
    supplier = _id(client, headers, "suppliers", "FLOUR-SUPPLIER")
    body = {
        "supplier_id": line.pop("supplier_id", supplier),
        "purchase_date": "2026-11-02",
        "lines": [{"item_id": flour, "qty": "60", "uom": "kg", "rate_paise": 4500, **line}],
    }
    return body


def test_purchase_in_kg_is_stocked_in_grams_at_the_quoted_rate(client, as_user) -> None:
    production = as_user("production")
    flour = _id(client, production, "items", "FLOUR")
    body = {**_purchase(client, production), "bill_no": "SUP-778"}
    r = client.post(f"{API}/purchases", json=body, headers=production)
    assert r.status_code == 201, r.text
    purchase = r.json()
    [line] = purchase["lines"]
    assert (line["qty"], line["uom"]) == ("60000.000", "g")
    assert (line["entered_qty"], line["entered_uom"], line["rate_paise"]) == ("60.000", "kg", 4500)
    assert (line["value_paise"], purchase["total_paise"]) == (270000, 270000)  # 60 x Rs 45
    assert line["lot_no"] == f"PUR-{purchase['id']:04d}-1"
    assert _balance(client, production, flour) == (D(160000), 690000)  # Rs 43.125/kg on average

    again = client.get(f"{API}/purchases/{purchase['id']}", headers=as_user("accountant"))
    assert again.json() == purchase
    with engine.connect() as conn:
        audit = conn.execute(
            text("SELECT action FROM audit_log WHERE entity = 'purchase' AND entity_id = :id"),
            {"id": purchase["id"]},
        ).scalar_one()
    assert audit == "POST"


def test_input_gst_is_recorded_but_not_added_to_stock_value(client, as_user) -> None:
    production = as_user("production")
    pouch = _id(client, production, "items", "POUCH-200G")
    qty_before, value_before = _balance(client, production, pouch)
    body = _purchase(client, production)
    body["lines"] = [
        {"item_id": pouch, "qty": "100", "uom": "pcs", "rate_paise": 250, "gst_rate_bp": 1800}
    ]
    purchase = client.post(f"{API}/purchases", json=body, headers=production).json()
    taxes = (purchase["supply_type"], purchase["cgst_paise"], purchase["sgst_paise"])
    assert taxes == ("INTRA", 2250, 2250)  # Tamil Nadu supplier: 9% + 9% of Rs 250
    assert (purchase["taxable_paise"], purchase["total_paise"]) == (25000, 29500)
    # A15: the stock is valued at the taxable value only.
    assert _balance(client, production, pouch) == (qty_before + 100, value_before + 25000)


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"uom": "l"}, 422, "UNIT_ERROR"),  # flour isn't a liquid
        ({"rate_paise": 45.5}, 422, "VALIDATION_ERROR"),  # money is whole paise
        ({"qty": 60.5}, 422, "VALIDATION_ERROR"),  # quantities are decimal strings
        ({"qty": "1.2345"}, 422, "INVALID_QUANTITY"),  # more decimals than we store
        ({"supplier_id": 999999}, 404, "NOT_FOUND"),
    ],
)
def test_bad_purchases_are_refused(client, as_user, change, status, code) -> None:
    production = as_user("production")
    r = client.post(
        f"{API}/purchases", json=_purchase(client, production, **change), headers=production
    )
    assert (r.status_code, r.json()["error"]["code"]) == (status, code)


def test_finished_goods_are_not_purchased(client, as_user) -> None:
    production = as_user("production")
    body = _purchase(client, production)
    body["lines"][0]["item_id"] = _id(client, production, "items", "MURUKKU-200G")
    body["lines"][0]["uom"] = "pkt"
    r = client.post(f"{API}/purchases", json=body, headers=production)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "NOT_PURCHASABLE")


def test_only_production_records_purchases(client, as_user) -> None:
    admin = as_user("admin")
    r = client.post(f"{API}/purchases", json=_purchase(client, admin), headers=admin)
    assert r.status_code == 403
