"""Master data: the seeded benchmark masters, creation rules and wire formats."""

import pytest
from sqlalchemy import text

from app.core.db import engine

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"


def _one(client, headers, resource: str, code: str) -> dict:
    rows = client.get(f"{API}/{resource}", params={"code": code}, headers=headers).json()
    assert len(rows) == 1, rows
    return rows[0]


def test_seeded_items_use_base_units(client, as_user) -> None:
    admin = as_user("admin")
    flour = _one(client, admin, "items", "FLOUR")
    assert (flour["kind"], flour["base_uom"]) == ("RAW", "g")
    murukku = _one(client, admin, "items", "MURUKKU-200G")
    assert murukku["units"] == [{"uom": "carton", "factor": "20.000"}]
    assert (murukku["sale_price_paise"], murukku["gst_rate_bp"], murukku["hsn"]) == (
        5000,
        500,
        "2106",
    )


def test_bom_is_stored_per_batch_in_base_units(client, as_user) -> None:
    admin = as_user("admin")
    murukku = _one(client, admin, "items", "MURUKKU-200G")
    [bom] = client.get(f"{API}/boms", params={"item_id": murukku["id"]}, headers=admin).json()
    assert (bom["output_qty"], bom["output_uom"]) == ("200.000", "pkt")
    lines = {line["item_code"]: (line["qty"], line["uom"]) for line in bom["lines"]}
    assert lines == {
        "FLOUR": ("40000.000", "g"),
        "OIL": ("10000.000", "ml"),
        "SPICE-MIX": ("1200.000", "g"),
        "POUCH-200G": ("200.000", "pcs"),
        "CARTON": ("10.000", "pcs"),
    }


def test_salesman_sees_prices_from_the_price_list(client, as_user) -> None:
    rows = {
        r["code"]: r for r in client.get(f"{API}/price-list", headers=as_user("salesman_a")).json()
    }
    murukku = rows["MURUKKU-200G"]
    assert (murukku["sale_price_paise"], murukku["gst_rate_bp"], murukku["uom"]) == (
        5000,
        500,
        "pkt",
    )


def test_customers_carry_their_place_of_supply(client, as_user) -> None:
    headers = as_user("salesman_b")
    assert _one(client, headers, "customers", "RETAILER-A")["state_code"] == "33"
    assert _one(client, headers, "customers", "DISTRIBUTOR-B")["state_code"] == "29"


def test_new_customer_gets_a_gstin_warning_and_an_audit_row(client, as_user) -> None:
    body = {"code": "SHOP-C", "name": "Shop C", "gstin": "29ABCDE1234F1Z5", "state_code": "33"}
    r = client.post(f"{API}/customers", json=body, headers=as_user("admin"))
    assert r.status_code == 201, r.text
    assert len(r.json()["warnings"]) == 1  # saved anyway: GSTIN checks warn, they don't block
    with engine.connect() as conn:
        actions = conn.execute(
            text("SELECT action FROM audit_log WHERE entity = 'customer' AND entity_id = :id"),
            {"id": r.json()["id"]},
        ).scalars()
        assert list(actions) == ["CREATE"]


def test_duplicate_code_is_409(client, as_user) -> None:
    body = {"code": "RETAILER-A", "name": "Again", "state_code": "33"}
    r = client.post(f"{API}/customers", json=body, headers=as_user("admin"))
    assert (r.status_code, r.json()["error"]["code"]) == (409, "DUPLICATE_CODE")


@pytest.mark.parametrize(
    "change",
    [
        {"base_uom": "kg"},  # stock is never kept in kg
        {"sale_price_paise": None},  # a finished good needs a price
        {"sale_price_paise": 49.5},  # money is whole paise, not a float
    ],
)
def test_invalid_items_are_refused(client, as_user, change) -> None:
    item = {
        "code": "BAD-ITEM",
        "name": "Bad",
        "kind": "FG",
        "base_uom": "pkt",
        "sale_price_paise": 5000,
    }
    r = client.post(f"{API}/items", json={**item, **change}, headers=as_user("admin"))
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")


def test_new_product_and_bom_in_kitchen_units(client, as_user) -> None:
    admin = as_user("admin")  # BOMs are masters: admin only (spec section 2)
    item = {
        "code": "PAKODA-200G",
        "name": "Ribbon pakoda 200 g",
        "kind": "FG",
        "base_uom": "pkt",
        "hsn": "2106",
        "gst_rate_bp": 500,
        "sale_price_paise": 4500,
    }
    product = client.post(f"{API}/items", json=item, headers=admin)
    assert product.status_code == 201, product.text
    flour = _one(client, admin, "items", "FLOUR")
    bom = {
        "code": "PAKODA-200G-STD",
        "item_id": product.json()["id"],
        "output_qty": "150",
        "lines": [{"item_id": flour["id"], "qty": "30", "uom": "kg"}],
    }

    wrong_unit = {**bom, "lines": [{"item_id": flour["id"], "qty": "30", "uom": "l"}]}
    r = client.post(f"{API}/boms", json=wrong_unit, headers=admin)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "UNIT_ERROR")  # flour isn't liquid

    float_qty = {**bom, "lines": [{"item_id": flour["id"], "qty": 30.5, "uom": "kg"}]}
    r = client.post(f"{API}/boms", json=float_qty, headers=admin)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "VALIDATION_ERROR")

    created = client.post(f"{API}/boms", json=bom, headers=admin)
    assert created.status_code == 201, created.text
    assert created.json()["lines"][0]["qty"] == "30000.000"  # 30 kg stored as grams

    again = client.post(f"{API}/boms", json={**bom, "code": "PAKODA-200G-V2"}, headers=admin)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "BOM_EXISTS")


# ---- P11: edit and deactivate masters ---------------------------------------------------


def test_edit_an_items_price_and_tolerance(client, as_user) -> None:
    admin = as_user("admin")
    murukku = _one(client, admin, "items", "MURUKKU-200G")
    r = client.patch(
        f"{API}/items/{murukku['id']}",
        json={"sale_price_paise": 5500, "variance_tol_bp": 500},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["sale_price_paise"], r.json()["variance_tol_bp"]) == (5500, 500)
    # The price list the salesman sees reflects the new price.
    prices = {p["code"]: p for p in client.get(f"{API}/price-list", headers=admin).json()}
    assert prices["MURUKKU-200G"]["sale_price_paise"] == 5500
    # And the edit is audit-logged with before/after.
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, before, after FROM audit_log "
                "WHERE entity = 'item' AND entity_id = :id ORDER BY id"
            ),
            {"id": murukku["id"]},
        ).all()
        assert [a for a, *_ in rows][-1] == "UPDATE"
        _, before, after = rows[-1]
        assert before["sale_price_paise"] == 5000 and after["sale_price_paise"] == 5500


def test_deactivated_item_drops_out_of_lists_and_price_list(client, as_user) -> None:
    admin = as_user("admin")
    murukku = _one(client, admin, "items", "MURUKKU-200G")
    assert (
        client.patch(
            f"{API}/items/{murukku['id']}", json={"is_active": False}, headers=admin
        ).status_code
        == 200
    )
    # Not in the default list.
    codes = [r["code"] for r in client.get(f"{API}/items", headers=admin).json()]
    assert "MURUKKU-200G" not in codes
    # Gone from the price list the salesman sees (what you can sell today).
    assert all(
        r["code"] != "MURUKKU-200G"
        for r in client.get(f"{API}/price-list", headers=as_user("salesman_a")).json()
    )
    # Visible again with include_inactive=true (the admin can reactivate).
    all_rows = client.get(f"{API}/items", params={"include_inactive": "true"}, headers=admin).json()
    assert any(r["code"] == "MURUKKU-200G" and r["is_active"] is False for r in all_rows)
    # Reactivate.
    assert (
        client.patch(
            f"{API}/items/{murukku['id']}", json={"is_active": True}, headers=admin
        ).status_code
        == 200
    )
    codes_again = [r["code"] for r in client.get(f"{API}/items", headers=admin).json()]
    assert "MURUKKU-200G" in codes_again


def test_edit_a_customer_and_reassign_the_salesman(client, as_user) -> None:
    admin = as_user("admin")
    retailer = _one(client, admin, "customers", "RETAILER-A")
    salesman_b = client.get(
        f"{API}/customers", params={"code": "DISTRIBUTOR-B"}, headers=admin
    ).json()[0]["salesman_id"]
    r = client.patch(
        f"{API}/customers/{retailer['id']}",
        json={"address": "New shop road", "salesman_id": salesman_b},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["address"], r.json()["salesman_id"]) == ("New shop road", salesman_b)


def test_cannot_assign_a_non_salesman_to_a_customer(client, as_user) -> None:
    admin = as_user("admin")
    retailer = _one(client, admin, "customers", "RETAILER-A")
    admin_id = client.get(f"{API}/auth/me", headers=admin).json()["id"]
    r = client.patch(
        f"{API}/customers/{retailer['id']}", json={"salesman_id": admin_id}, headers=admin
    )
    assert (r.status_code, r.json()["error"]["code"]) == (422, "INVALID_SALESMAN")


def test_deactivated_supplier_drops_out_of_default_list(client, as_user) -> None:
    admin = as_user("admin")
    supplier = _one(client, admin, "suppliers", "FLOUR-SUPPLIER")
    assert (
        client.patch(
            f"{API}/suppliers/{supplier['id']}", json={"is_active": False}, headers=admin
        ).status_code
        == 200
    )
    codes = [s["code"] for s in client.get(f"{API}/suppliers", headers=admin).json()]
    assert "FLOUR-SUPPLIER" not in codes
    # But a purchase register over the past still shows historical purchases from them — the ledger
    # and the stored purchase.supplier_id don't look at is_active.


@pytest.mark.parametrize("role", ["salesman_a", "production", "accountant", "owner"])
def test_only_admin_can_patch_a_master(client, as_user, role) -> None:
    admin = as_user("admin")
    retailer = _one(client, admin, "customers", "RETAILER-A")
    r = client.patch(
        f"{API}/customers/{retailer['id']}", json={"name": "Nope"}, headers=as_user(role)
    )
    assert r.status_code == 403


def test_patch_unknown_master_is_404(client, as_user) -> None:
    admin = as_user("admin")
    assert client.patch(f"{API}/items/999999", json={"name": "X"}, headers=admin).status_code == 404
    assert (
        client.patch(f"{API}/customers/999999", json={"name": "X"}, headers=admin).status_code
        == 404
    )
    assert (
        client.patch(f"{API}/suppliers/999999", json={"name": "X"}, headers=admin).status_code
        == 404
    )
