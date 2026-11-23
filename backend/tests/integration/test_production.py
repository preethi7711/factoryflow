"""Production runs, end to end through the API: the benchmark's purchase -> run -> output ->
overheads flow (PROBLEM.md section 5 steps 1-3 and 8), plus the rules around it.

B13 is proven here: the benchmark's own B13 check needs scenario step 8, which comes after
orders and payments, so it only turns green in P6 (docs/project_status.md, Open issues).
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.main import app

API = "/api/v1"
D = Decimal
RUN_DATE = "2026-11-02"
CODES = ("FLOUR", "OIL", "SPICE-MIX", "POUCH-200G", "CARTON", "MURUKKU-200G")


def _headers(client: TestClient, username: str) -> dict[str, str]:
    password = get_settings().seed_demo_password
    r = client.post(f"{API}/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _balance(client: TestClient, headers: dict, item_id: int) -> tuple[Decimal, int]:
    body = client.get(f"{API}/stock/balance/{item_id}", headers=headers).json()
    return D(body["qty"]), body["value_paise"]


@pytest.fixture(scope="module")
def flow(seeded_db):
    """Steps 1-3 and 8 of the benchmark, once per module; tests read what each call returned."""
    with TestClient(app) as client:
        prod = _headers(client, "production")
        ids = {
            code: client.get(f"{API}/items", params={"code": code}, headers=prod).json()[0]["id"]
            for code in CODES
        }
        supplier = client.get(f"{API}/suppliers", params={"code": "FLOUR-SUPPLIER"}, headers=prod)
        bom = client.get(f"{API}/boms", params={"item_id": ids["MURUKKU-200G"]}, headers=prod)
        purchase = {
            "supplier_id": supplier.json()[0]["id"],
            "purchase_date": RUN_DATE,
            "lines": [{"item_id": ids["FLOUR"], "qty": "60", "uom": "kg", "rate_paise": 4500}],
        }
        assert client.post(f"{API}/purchases", json=purchase, headers=prod).status_code == 201

        start = {
            "bom_id": bom.json()[0]["id"],
            "batches": "1",
            "run_date": RUN_DATE,
            "issues": [
                {"item_id": ids["FLOUR"], "qty": "40", "uom": "kg"},
                {"item_id": ids["OIL"], "qty": "10.5", "uom": "l"},
                {"item_id": ids["SPICE-MIX"], "qty": "1.2", "uom": "kg"},
            ],
        }
        started = client.post(f"{API}/production-runs", json=start, headers=prod)
        assert started.status_code == 201, started.text
        run = f"{API}/production-runs/{started.json()['id']}"
        finish = {
            "output_qty": "188",
            "issues": [
                {"item_id": ids["POUCH-200G"], "qty": "194", "uom": "pcs"},
                {"item_id": ids["CARTON"], "qty": "9", "uom": "pcs"},
            ],
            "damaged": [{"item_id": ids["POUCH-200G"], "qty": "6", "uom": "pcs"}],
        }
        completed = client.post(f"{run}/complete", json=finish, headers=prod)
        assert completed.status_code == 200, completed.text
        variance = client.get(f"{run}/variance", headers=prod).json()
        cost_before = client.get(f"{run}/cost", headers=prod).json()
        lines = [
            {"kind": "LABOUR", "amount_paise": 120000},
            {"kind": "GAS_POWER", "amount_paise": 60000},
        ]
        overheads = client.post(f"{run}/overheads", json={"lines": lines}, headers=prod)
        assert overheads.status_code == 201, overheads.text
        yield SimpleNamespace(
            ids=ids,
            bom_id=start["bom_id"],
            run_id=started.json()["id"],
            run_url=run,
            started=started.json(),
            completed=completed.json(),
            variance=variance,
            cost_before=cost_before,
            overheads=overheads.json(),
            cost=client.get(f"{run}/cost", headers=prod).json(),
            balances={code: _balance(client, prod, ids[code]) for code in CODES},
        )


def _lines(run: dict) -> dict[str, tuple]:
    return {
        line["item_code"]: (D(line["planned_qty"]), D(line["actual_qty"]), D(line["damaged_qty"]))
        for line in run["lines"]
    }


def test_start_plans_every_bom_line_and_issues_the_raw_materials(flow) -> None:
    assert flow.started["status"] == "DRAFT"
    assert _lines(flow.started) == {
        "FLOUR": (D(40000), D(40000), D(0)),
        "OIL": (D(10000), D(10500), D(0)),  # 0.5 L over standard
        "SPICE-MIX": (D(1200), D(1200), D(0)),
        "POUCH-200G": (D(200), D(0), D(0)),  # packaging comes at the end
        "CARTON": (D(10), D(0), D(0)),
    }


def test_completion_posts_output_at_material_cost(flow) -> None:
    done = flow.completed
    assert (done["status"], D(done["good_qty"]), D(done["planned_qty"])) == ("COMPLETED", 188, 200)
    assert done["output_lot_no"] == f"RUN-{flow.run_id:04d}"
    assert _lines(done)["POUCH-200G"] == (D(200), D(194), D(6))  # 6 damaged are part of the 194
    # B1-B6 with values: WAC issues, and FG = opening Rs 992.50 + materials + overheads.
    assert flow.balances == {
        "FLOUR": (D(120000), 517500),
        "OIL": (D(19500), 273000),
        "SPICE-MIX": (D(3800), 76000),
        "POUCH-200G": (D(306), 76500),
        "CARTON": (D(21), 31500),
        "MURUKKU-200G": (D(238), 99250 + 405500 + 180000),
    }


def test_output_lot_expires_after_the_shelf_life(flow) -> None:
    with engine.connect() as conn:
        mfg, expiry = conn.execute(
            text("SELECT mfg_date, expiry_date FROM stock_lot WHERE lot_no = :lot"),
            {"lot": flow.completed["output_lot_no"]},
        ).one()
    assert (mfg, expiry) == (date(2026, 11, 2), date(2027, 1, 31))  # A16: 90 days


def test_variance_matches_the_benchmark(flow) -> None:
    v = flow.variance
    assert (v["yield"]["variance_bp"], v["yield"]["flagged"]) == (-600, True)  # B8
    rows = {line["item_code"]: (line["variance_bp"], line["flagged"]) for line in v["lines"]}
    assert rows == {
        "FLOUR": (0, False),
        "OIL": (500, True),  # B9
        "SPICE-MIX": (0, False),
        "POUCH-200G": (-300, False),  # B9b: exactly -3.00% is not "beyond 3%" (A2)
        "CARTON": (-1000, True),  # A4: under-use, shown for information
    }


def test_b13_cost_per_packet_with_overheads(flow) -> None:
    before, after = flow.cost_before, flow.cost
    assert (before["material_paise"], before["overhead_paise"]) == (405500, 0)
    assert before["cost_per_unit_paise"] == 2157  # materials only: 405500 / 188
    assert (after["material_paise"], after["overhead_paise"], after["total_paise"]) == (
        405500,
        180000,
        585500,
    )
    assert (D(after["good_qty"]), after["cost_per_unit_paise"]) == (D(188), 3114)  # Rs 31.14


def test_overheads_post_value_only_movements_on_the_run_lot(flow) -> None:
    assert flow.overheads["overhead_paise"] == 180000
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT m.qty, m.value_paise FROM stock_movement m"
                " JOIN stock_lot l ON l.id = m.lot_id"
                " WHERE m.movement_type = 'COST_ADJUST' AND l.lot_no = :lot ORDER BY m.id"
            ),
            {"lot": flow.completed["output_lot_no"]},
        ).all()
    assert [(D(q), v) for q, v in rows] == [(D(0), 120000), (D(0), 60000)]


def test_a_run_cannot_be_completed_twice(client, as_user, flow) -> None:
    again = {"output_qty": "188"}
    r = client.post(f"{flow.run_url}/complete", json=again, headers=as_user("production"))
    assert (r.status_code, r.json()["error"]["code"]) == (409, "RUN_ALREADY_COMPLETED")
    murukku = flow.ids["MURUKKU-200G"]
    assert _balance(client, as_user("production"), murukku) == flow.balances["MURUKKU-200G"]


def test_a_failed_start_leaves_no_trace(client, as_user, flow) -> None:
    count = "SELECT (SELECT COUNT(*) FROM production_run), (SELECT COUNT(*) FROM stock_movement)"
    with engine.connect() as conn:
        before = conn.execute(text(count)).one()
    start = {
        "bom_id": flow.bom_id,
        "batches": "1",
        "run_date": RUN_DATE,
        "issues": [
            {"item_id": flow.ids["OIL"], "qty": "1", "uom": "l"},  # fine on its own...
            {"item_id": flow.ids["FLOUR"], "qty": "500", "uom": "kg"},  # ...but only 120 kg left
        ],
    }
    r = client.post(f"{API}/production-runs", json=start, headers=as_user("production"))
    assert (r.status_code, r.json()["error"]["code"]) == (409, "INSUFFICIENT_STOCK")
    details = r.json()["error"]["details"]
    assert details["item"] == "FLOUR"
    assert (D(details["available"]), D(details["shortage"])) == (D(120000), D(380000))
    with engine.connect() as conn:
        assert conn.execute(text(count)).one() == before  # no run, no oil issue: all or nothing


def test_rules_for_an_unfinished_run(client, as_user, flow) -> None:
    prod = as_user("production")
    draft = {"bom_id": flow.bom_id, "batches": "1", "run_date": RUN_DATE}
    created = client.post(f"{API}/production-runs", json=draft, headers=prod)
    run = f"{API}/production-runs/{created.json()['id']}"

    for method, path in (("GET", "/variance"), ("GET", "/cost")):
        r = client.request(method, f"{run}{path}", headers=prod)
        assert (r.status_code, r.json()["error"]["code"]) == (409, "RUN_NOT_COMPLETED")
    labour = {"lines": [{"kind": "LABOUR", "amount_paise": 100}]}
    r = client.post(f"{run}/overheads", json=labour, headers=prod)
    assert (r.status_code, r.json()["error"]["code"]) == (409, "RUN_NOT_COMPLETED")

    nothing_issued = {"output_qty": "10"}
    r = client.post(f"{run}/complete", json=nothing_issued, headers=prod)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "NOTHING_ISSUED")

    murukku = {"item_id": flow.ids["MURUKKU-200G"], "qty": "1", "uom": "pkt"}
    r = client.post(f"{run}/complete", json={"output_qty": "10", "issues": [murukku]}, headers=prod)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "NOT_IN_BOM")

    spice_before = _balance(client, prod, flow.ids["SPICE-MIX"])
    too_much_damage = {
        "output_qty": "10",
        "issues": [{"item_id": flow.ids["SPICE-MIX"], "qty": "0.1", "uom": "kg"}],
        "damaged": [{"item_id": flow.ids["SPICE-MIX"], "qty": "0.2", "uom": "kg"}],
    }
    r = client.post(f"{run}/complete", json=too_much_damage, headers=prod)
    assert (r.status_code, r.json()["error"]["code"]) == (422, "DAMAGED_EXCEEDS_ISSUED")
    assert _balance(client, prod, flow.ids["SPICE-MIX"]) == spice_before  # issue rolled back


@pytest.mark.parametrize(
    ("username", "method", "path", "status"),
    [
        ("salesman_a", "GET", "/variance", 403),  # costs and production aren't sales data
        ("admin", "POST", "/complete", 403),  # only the floor supervisor records production
        ("admin", "GET", "", 200),
        ("accountant", "GET", "/cost", 200),
        ("owner", "GET", "/variance", 200),
    ],
)
def test_run_roles(client, as_user, flow, username, method, path, status) -> None:
    r = client.request(method, f"{flow.run_url}{path}", headers=as_user(username), json={})
    assert r.status_code == status, r.text


def test_every_run_step_is_audited(flow) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, before ->> 'status', after ->> 'status' FROM audit_log"
                " WHERE entity = 'production_run' AND entity_id = :id ORDER BY id"
            ),
            {"id": flow.run_id},
        ).all()
    assert [tuple(r) for r in rows] == [
        ("START", None, "DRAFT"),
        ("COMPLETE", "DRAFT", "COMPLETED"),
        ("OVERHEAD", None, None),
    ]
