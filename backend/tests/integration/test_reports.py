"""Reports and the invoice PDF through the API (M6–M8). A module-scoped fixture runs the benchmark
flow once (purchase → run → order → invoice → dispatch → payment → overheads); the tests read it.

The stock summary must reconcile: per item, opening + receipts − issues ± adjustments == closing,
and closing == the balance endpoint (== SUM of the ledger).
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

API = "/api/v1"
D = Decimal
PDATE = "2026-11-02"
ODATE = "2026-11-03"
PAYDATE = "2026-11-05"
FROM, TO = "2026-11-01", "2026-11-30"
CODES = ("FLOUR", "OIL", "SPICE-MIX", "POUCH-200G", "CARTON", "MURUKKU-200G")


def _h(client, username):
    pw = get_settings().seed_demo_password
    r = client.post(f"{API}/auth/login", json={"username": username, "password": pw})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _key():
    import uuid

    return {"Idempotency-Key": str(uuid.uuid4())}


@pytest.fixture(scope="module")
def flow(seeded_db):
    with TestClient(app) as client:
        admin, prod, sa = _h(client, "admin"), _h(client, "production"), _h(client, "salesman_a")
        ids = {
            c: client.get(f"{API}/items", params={"code": c}, headers=admin).json()[0]["id"]
            for c in CODES
        }
        supplier = client.get(
            f"{API}/suppliers", params={"code": "FLOUR-SUPPLIER"}, headers=prod
        ).json()[0]["id"]
        bom = client.get(
            f"{API}/boms", params={"item_id": ids["MURUKKU-200G"]}, headers=prod
        ).json()[0]["id"]
        retailer = client.get(
            f"{API}/customers", params={"code": "RETAILER-A"}, headers=admin
        ).json()[0]["id"]

        client.post(
            f"{API}/purchases",
            json={
                "supplier_id": supplier,
                "purchase_date": PDATE,
                "lines": [{"item_id": ids["FLOUR"], "qty": "60", "uom": "kg", "rate_paise": 4500}],
            },
            headers=prod,
        )
        run = client.post(
            f"{API}/production-runs",
            json={
                "bom_id": bom,
                "batches": "1",
                "run_date": PDATE,
                "issues": [
                    {"item_id": ids["FLOUR"], "qty": "40", "uom": "kg"},
                    {"item_id": ids["OIL"], "qty": "10.5", "uom": "l"},
                    {"item_id": ids["SPICE-MIX"], "qty": "1.2", "uom": "kg"},
                ],
            },
            headers=prod,
        ).json()
        client.post(
            f"{API}/production-runs/{run['id']}/complete",
            json={
                "output_qty": "188",
                "issues": [
                    {"item_id": ids["POUCH-200G"], "qty": "194", "uom": "pcs"},
                    {"item_id": ids["CARTON"], "qty": "9", "uom": "pcs"},
                ],
                "damaged": [{"item_id": ids["POUCH-200G"], "qty": "6", "uom": "pcs"}],
            },
            headers=prod,
        )
        order = client.post(
            f"{API}/orders",
            json={
                "customer_id": retailer,
                "order_date": ODATE,
                "lines": [{"item_id": ids["MURUKKU-200G"], "qty": "150", "uom": "pkt"}],
            },
            headers={**sa, **_key()},
        ).json()
        client.post(f"{API}/orders/{order['id']}/approve", headers=admin)
        inv = client.post(
            f"{API}/orders/{order['id']}/invoice", json={"invoice_date": ODATE}, headers=admin
        ).json()
        client.post(
            f"{API}/invoices/{inv['id']}/dispatch", json={"dispatch_date": ODATE}, headers=admin
        )
        client.post(
            f"{API}/payments",
            json={
                "customer_id": retailer,
                "payment_date": PAYDATE,
                "amount_paise": 400000,
                "allocations": [{"invoice_id": inv["id"], "amount_paise": 400000}],
            },
            headers=admin,
        )
        client.post(
            f"{API}/production-runs/{run['id']}/overheads",
            json={
                "lines": [
                    {"kind": "LABOUR", "amount_paise": 120000},
                    {"kind": "GAS_POWER", "amount_paise": 60000},
                ]
            },
            headers=prod,
        )
        yield {
            "client": client,
            "admin": admin,
            "ids": ids,
            "invoice_id": inv["id"],
            "run_no": run["run_no"],
        }


def _report(flow, name, headers=None, **params):
    headers = headers or flow["admin"]
    return flow["client"].get(
        f"{API}/reports/{name}", params={"from": FROM, "to": TO, **params}, headers=headers
    )


def test_sales_register_lists_the_invoice(flow):
    body = _report(flow, "sales-register").json()
    assert body["name"] == "sales-register" and body["from"] == FROM
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["invoice_no"] == "FF/2026-27/0001"
    assert row["total_paise"] == 787500
    assert body["totals"]["taxable_paise"] == 750000
    assert body["totals"]["total_paise"] == 787500


def test_stock_summary_reconciles_with_the_ledger(flow):
    body = _report(flow, "stock-summary").json()
    for row in body["rows"]:
        opening, receipts = D(row["opening_qty"]), D(row["receipts_qty"])
        issues, adj, closing = (
            D(row["issues_qty"]),
            D(row["adjustments_qty"]),
            D(row["closing_qty"]),
        )
        assert opening + receipts - issues + adj == closing, row
        # closing must equal the live balance endpoint (= SUM of the ledger)
        item_id = flow["ids"][row["item_code"]]
        bal = flow["client"].get(f"{API}/stock/balance/{item_id}", headers=flow["admin"]).json()
        assert D(bal["qty"]) == closing, row
    flour = next(r for r in body["rows"] if r["item_code"] == "FLOUR")
    assert D(flour["closing_qty"]) == D("120000")  # 100 + 60 − 40 kg, in grams (B1)


def test_stock_ledger_rows_carry_their_source(flow):
    body = _report(flow, "stock-ledger").json()
    assert body["rows"], "no ledger rows in the period"
    assert all(r["source_type"] and r["source_id"] for r in body["rows"])
    # OPENING is dated 31 Oct (before the window), so the Nov ledger shows the month's own moves.
    assert {"PURCHASE", "OUTPUT", "ISSUE", "DISPATCH"} <= {r["movement_type"] for r in body["rows"]}


def test_production_report_shows_cost_and_variance(flow):
    body = _report(flow, "production").json()
    row = next(r for r in body["rows"] if r["run_no"] == flow["run_no"])
    assert row["cost_per_unit_paise"] == 3114  # B13
    assert row["yield_variance_bp"] == -600  # B8
    assert D(row["good_qty"]) == 188


def test_csv_and_xlsx_exports(flow):
    csv = _report(flow, "sales-register", format="csv")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Invoice no." in csv.text.splitlines()[0]
    xlsx = _report(flow, "stock-summary", format="xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["content-type"]
    assert xlsx.content[:2] == b"PK"  # a zip/xlsx magic


def test_invoice_pdf_is_a_pdf(flow):
    r = flow["client"].get(f"{API}/invoices/{flow['invoice_id']}/pdf", headers=flow["admin"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_reports_are_not_for_sales_or_production(flow):
    assert (
        _report(flow, "sales-register", headers=_h(flow["client"], "salesman_a")).status_code == 403
    )
    assert (
        _report(flow, "stock-summary", headers=_h(flow["client"], "production")).status_code == 403
    )


def test_unknown_report_is_404(flow):
    assert _report(flow, "nonsense").status_code == 404
