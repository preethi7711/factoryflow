"""PROBLEM.md section 5 benchmark, end to end through the HTTP API.

Expected numbers come from docs/project_spec.md section 4 (single source of truth).
Never change an expected number to make a test pass.

How it works:
- One module-scoped fixture (`sc`) wipes the test DB, seeds it, then runs steps 1-9 in order,
  logged in as the role that does each step in real life.
- If a step fails, the scenario stops there and records why. Each check calls
  `sc.require(step)` for the last step it depends on, so a phase can turn its own checks
  green while later steps are still unbuilt.
- Every check starts as `@NOT_BUILT` (xfail, strict). Strict means an unexpected pass
  fails the run, so the phase that makes a check pass must remove its marker in the same commit.

The request shapes below are the P1 contract. A later phase may adjust a path or payload
when it builds the endpoint; it must never adjust an expected number.

Quantities are compared in each item's base unit (A11): flour g, oil ml, spice g,
pouches and cartons pcs, finished goods pkt. Money is integer paise.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.db import engine
from app.main import app
from tests.conftest import reset_database
from tests.invariants import LEDGER_SUM, MOVEMENTS, ORPHANS

pytestmark = pytest.mark.benchmark
NOT_BUILT = pytest.mark.xfail(strict=True, reason="not built yet")

# Fixed dates inside FY 2026-27, so FY numbering and month reports never depend on today's date.
PURCHASE_DATE = "2026-11-02"
RUN_DATE = "2026-11-02"
ORDER_DATE = "2026-11-03"
PAYMENT_DATE = "2026-11-05"
MONTH_FROM, MONTH_TO = "2026-11-01", "2026-11-30"

# Item codes created by the seed script (P3).
FLOUR, OIL, SPICE, POUCH, CARTON, MURUKKU = (
    "FLOUR",
    "OIL",
    "SPICE-MIX",
    "POUCH-200G",
    "CARTON",
    "MURUKKU-200G",
)
ALL_ITEMS = (FLOUR, OIL, SPICE, POUCH, CARTON, MURUKKU)


class StepFailed(Exception):
    """An API call in the scenario returned an unexpected status."""


@dataclass(frozen=True)
class InvariantCheck:
    """Ledger health recorded right after one completed step."""

    step: int
    problems: list[str]  # from GET /stock/reconcile
    mismatches: list[str]  # items whose API balance differs from SUM(ledger)
    orphans: int
    movements: int


@dataclass
class Scenario:
    client: TestClient
    tokens: dict[str, str] = field(default_factory=dict)
    ids: dict[str, int] = field(default_factory=dict)
    snap: dict[str, Any] = field(default_factory=dict)  # values captured at a point in time
    invariants: list[InvariantCheck] = field(default_factory=list)  # one per completed step
    reached: int = -1  # last step that completed
    error: str | None = None

    def require(self, step: int) -> None:
        if self.reached < step:
            pytest.fail(f"scenario stopped before step {step} finished: {self.error}")

    def raw(self, method: str, path: str, user: str, **kwargs: Any):
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.tokens.get(user, '')}"
        return self.client.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    def call(self, method: str, path: str, user: str, expect: int = 200, **kwargs: Any) -> Any:
        r = self.raw(method, path, user, **kwargs)
        if r.status_code != expect:
            raise StepFailed(
                f"{method} {path} as {user}: expected {expect}, got {r.status_code}: {r.text[:300]}"
            )
        return r.json() if r.content else None

    def lookup(self, resource: str, code: str) -> int:
        rows = self.call("GET", f"/{resource}", "admin", params={"code": code})
        if len(rows) != 1:
            raise StepFailed(f"expected exactly one {resource} with code {code}, got {len(rows)}")
        return rows[0]["id"]

    def stock(self, code: str) -> tuple[Decimal, str]:
        body = self.call("GET", f"/stock/balance/{self.ids[code]}", "admin")
        return Decimal(body["qty"]), body["uom"]

    def check_invariants(self, step: int) -> None:
        """Invariants 4 and 6 after every completed step, so a step that breaks the ledger is
        caught even if a later step happens to hide the damage."""
        reconcile = self.call("GET", "/stock/reconcile", "accountant")
        with engine.connect() as conn:
            mismatches = [
                code
                for code in ALL_ITEMS
                if self.stock(code)[0]
                != conn.execute(LEDGER_SUM, {"item_id": self.ids[code]}).scalar_one()
            ]
            self.invariants.append(
                InvariantCheck(
                    step=step,
                    problems=reconcile["problems"],
                    mismatches=mismatches,
                    orphans=conn.execute(ORPHANS).scalar_one(),
                    movements=conn.execute(MOVEMENTS).scalar_one(),
                )
            )


# --- Scenario steps (PROBLEM.md section 5, "Steps to demonstrate") --------------------


def step0_seed_and_login(sc: Scenario) -> None:
    reset_database()
    from app import seed  # built in P3

    seed.run()
    password = get_settings().seed_demo_password
    for user in ("salesman_a", "salesman_b", "admin", "production", "accountant", "owner"):
        body = sc.call("POST", "/auth/login", user, json={"username": user, "password": password})
        sc.tokens[user] = body["access_token"]
    for code in ALL_ITEMS:
        sc.ids[code] = sc.lookup("items", code)
    sc.ids["RETAILER-A"] = sc.lookup("customers", "RETAILER-A")
    sc.ids["DISTRIBUTOR-B"] = sc.lookup("customers", "DISTRIBUTOR-B")
    sc.ids["SUPPLIER"] = sc.lookup("suppliers", "FLOUR-SUPPLIER")
    sc.ids["BOM"] = sc.call("GET", "/boms", "admin", params={"item_id": sc.ids[MURUKKU]})[0]["id"]


def step1_purchase_flour(sc: Scenario) -> None:
    # 60 kg flour at Rs 45/kg. rate_paise is per the line's uom (kg here).
    sc.call(
        "POST",
        "/purchases",
        "production",
        expect=201,
        json={
            "supplier_id": sc.ids["SUPPLIER"],
            "purchase_date": PURCHASE_DATE,
            "lines": [{"item_id": sc.ids[FLOUR], "qty": "60", "uom": "kg", "rate_paise": 4500}],
        },
    )


def step2_start_run(sc: Scenario) -> None:
    body = sc.call(
        "POST",
        "/production-runs",
        "production",
        expect=201,
        json={
            "bom_id": sc.ids["BOM"],
            "batches": "1",
            "run_date": RUN_DATE,
            "issues": [
                {"item_id": sc.ids[FLOUR], "qty": "40", "uom": "kg"},
                {"item_id": sc.ids[OIL], "qty": "10.5", "uom": "l"},
                {"item_id": sc.ids[SPICE], "qty": "1.2", "uom": "kg"},
            ],
        },
    )
    sc.ids["RUN"] = body["id"]


def step3_record_output(sc: Scenario) -> None:
    # 188 good packets. Pouches issued 194 = 188 used + 6 damaged. 9 cartons used.
    sc.call(
        "POST",
        f"/production-runs/{sc.ids['RUN']}/complete",
        "production",
        json={
            "output_qty": "188",
            "issues": [
                {"item_id": sc.ids[POUCH], "qty": "194", "uom": "pcs"},
                {"item_id": sc.ids[CARTON], "qty": "9", "uom": "pcs"},
            ],
            "damaged": [{"item_id": sc.ids[POUCH], "qty": "6", "uom": "pcs"}],
        },
    )
    # Raw materials don't move after this step (overheads are value only), so closing = now.
    sc.snap["after_run"] = {code: sc.stock(code) for code in ALL_ITEMS}
    sc.snap["variance"] = sc.call("GET", f"/production-runs/{sc.ids['RUN']}/variance", "production")


def step4_salesman_a_order(sc: Scenario) -> None:
    body = sc.call(
        "POST",
        "/orders",
        "salesman_a",
        expect=201,
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_id": sc.ids["RETAILER-A"],
            "order_date": ORDER_DATE,
            "lines": [{"item_id": sc.ids[MURUKKU], "qty": "150", "uom": "pkt"}],
        },
    )
    sc.ids["ORDER_A"] = body["id"]
    # RBAC probe: a salesman may not approve, not even their own order. Recorded, asserted later.
    r = sc.raw("POST", f"/orders/{sc.ids['ORDER_A']}/approve", "salesman_a")
    sc.snap["salesman_approve_status"] = r.status_code


def step5_approve_invoice_dispatch(sc: Scenario) -> None:
    sc.call("POST", f"/orders/{sc.ids['ORDER_A']}/approve", "admin")
    inv = sc.call(
        "POST",
        f"/orders/{sc.ids['ORDER_A']}/invoice",
        "admin",
        expect=201,
        json={"invoice_date": ORDER_DATE},
    )
    sc.ids["INVOICE_A"] = inv["id"]
    sc.snap["invoice_a"] = inv
    sc.call("POST", f"/invoices/{inv['id']}/dispatch", "admin", json={"dispatch_date": ORDER_DATE})
    sc.snap["fg_after_dispatch"] = sc.stock(MURUKKU)


def step6_distributor_b_shortage(sc: Scenario) -> None:
    body = sc.call(
        "POST",
        "/orders",
        "salesman_b",
        expect=201,
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_id": sc.ids["DISTRIBUTOR-B"],
            "order_date": ORDER_DATE,
            "lines": [{"item_id": sc.ids[MURUKKU], "qty": "120", "uom": "pkt"}],
        },
    )
    sc.ids["ORDER_B"] = body["id"]
    sc.snap["approve_b"] = sc.call(
        "POST", f"/orders/{sc.ids['ORDER_B']}/approve", "admin", expect=409
    )
    sc.snap["preview_b"] = sc.call("GET", f"/orders/{sc.ids['ORDER_B']}/tax-preview", "admin")


def step7_payment(sc: Scenario) -> None:
    sc.call(
        "POST",
        "/payments",
        "admin",
        expect=201,
        json={
            "customer_id": sc.ids["RETAILER-A"],
            "payment_date": PAYMENT_DATE,
            "amount_paise": 400000,
            "allocations": [{"invoice_id": sc.ids["INVOICE_A"], "amount_paise": 400000}],
        },
    )
    sc.snap["outstanding_a"] = sc.call(
        "GET", f"/customers/{sc.ids['RETAILER-A']}/outstanding", "admin"
    )


def step8_overheads_and_cost(sc: Scenario) -> None:
    sc.call(
        "POST",
        f"/production-runs/{sc.ids['RUN']}/overheads",
        "production",
        expect=201,
        json={
            "lines": [
                {"kind": "LABOUR", "amount_paise": 120000},
                {"kind": "GAS_POWER", "amount_paise": 60000},
            ]
        },
    )
    sc.snap["cost"] = sc.call("GET", f"/production-runs/{sc.ids['RUN']}/cost", "production")


def step9_month_reports(sc: Scenario) -> None:
    params = {"from": MONTH_FROM, "to": MONTH_TO}
    for report in ("sales-register", "stock-summary", "stock-ledger", "production"):
        sc.call("GET", f"/reports/{report}", "accountant", params=params)


STEPS = [
    step0_seed_and_login,
    step1_purchase_flour,
    step2_start_run,
    step3_record_output,
    step4_salesman_a_order,
    step5_approve_invoice_dispatch,
    step6_distributor_b_shortage,
    step7_payment,
    step8_overheads_and_cost,
    step9_month_reports,
]


@pytest.fixture(scope="module")
def sc():
    with TestClient(app) as client:
        scenario = Scenario(client)
        try:
            for n, step in enumerate(STEPS):
                step(scenario)
                scenario.reached = n
                scenario.check_invariants(n)
        except Exception as exc:  # record and stop; each check reports what it was missing
            scenario.error = f"step {scenario.reached + 1}: {type(exc).__name__}: {exc}"
        yield scenario


def _line(variance: dict, code: str) -> dict:
    return next(line for line in variance["lines"] if line["item_code"] == code)


# --- Checks (docs/project_spec.md section 4) ------------------------------------------


def test_b1_flour_closing_120_kg(sc):
    sc.require(3)
    assert sc.snap["after_run"][FLOUR] == (Decimal("120000"), "g")


def test_b2_oil_closing_19_5_l(sc):
    sc.require(3)
    assert sc.snap["after_run"][OIL] == (Decimal("19500"), "ml")


def test_b3_spice_closing_3_8_kg(sc):
    sc.require(3)
    assert sc.snap["after_run"][SPICE] == (Decimal("3800"), "g")


def test_b4_pouches_closing_306(sc):
    sc.require(3)
    assert sc.snap["after_run"][POUCH] == (Decimal("306"), "pcs")


def test_b5_cartons_closing_21(sc):
    sc.require(3)
    assert sc.snap["after_run"][CARTON] == (Decimal("21"), "pcs")


def test_b6_fg_after_run_238(sc):
    sc.require(3)
    assert sc.snap["after_run"][MURUKKU] == (Decimal("238"), "pkt")


def test_b7_fg_after_retailer_a_dispatch_88(sc):
    sc.require(5)
    assert sc.snap["fg_after_dispatch"] == (Decimal("88"), "pkt")


def test_b8_yield_variance_minus_6_pct_flagged(sc):
    sc.require(3)
    y = sc.snap["variance"]["yield"]
    assert Decimal(y["planned_qty"]) == 200
    assert Decimal(y["actual_qty"]) == 188
    assert y["variance_bp"] == -600
    assert y["flagged"] is True


def test_b9_oil_variance_plus_5_pct_flagged(sc):
    sc.require(3)
    oil = _line(sc.snap["variance"], OIL)
    assert oil["variance_bp"] == 500
    assert oil["flagged"] is True


def test_b9b_pouch_variance_minus_3_pct_not_flagged(sc):
    # A2: flag only when |variance| > 3.00% strictly. 194 vs 200 = exactly -3.00%.
    sc.require(3)
    pouch = _line(sc.snap["variance"], POUCH)
    assert pouch["variance_bp"] == -300
    assert pouch["flagged"] is False


def test_b10_retailer_a_invoice_cgst_sgst(sc):
    sc.require(5)
    inv = sc.snap["invoice_a"]
    assert inv["supply_type"] == "INTRA"
    assert inv["taxable_paise"] == 750000
    assert inv["cgst_paise"] == 18750
    assert inv["sgst_paise"] == 18750
    assert inv["igst_paise"] == 0
    assert inv["total_paise"] == 787500


def test_b10b_invoice_number_ff_2026_27_0001(sc):
    sc.require(5)
    assert sc.snap["invoice_a"]["invoice_no"] == "FF/2026-27/0001"


def test_b11_retailer_a_outstanding_3875(sc):
    sc.require(7)
    assert sc.snap["outstanding_a"]["outstanding_paise"] == 387500


def test_b12_distributor_b_shortage_32_flagged(sc):
    sc.require(6)
    err = sc.snap["approve_b"]["error"]
    assert err["code"] == "INSUFFICIENT_STOCK"
    assert Decimal(err["details"]["requested"]) == 120
    assert Decimal(err["details"]["available"]) == 88
    assert Decimal(err["details"]["shortage"]) == 32


def test_b12b_distributor_b_tax_preview_igst(sc):
    sc.require(6)
    p = sc.snap["preview_b"]
    assert p["supply_type"] == "INTER"
    assert p["taxable_paise"] == 600000
    assert p["igst_paise"] == 30000
    assert p["cgst_paise"] == 0
    assert p["sgst_paise"] == 0
    assert p["total_paise"] == 630000


def test_b13_cost_per_packet_31_14(sc):
    # WAC materials 4,055.00 + overheads 1,800.00 = 5,855.00 / 188 good = 31.1436 -> 31.14
    sc.require(8)
    c = sc.snap["cost"]
    assert c["material_paise"] == 405500
    assert c["overhead_paise"] == 180000
    assert c["total_paise"] == 585500
    assert Decimal(c["good_qty"]) == 188
    assert c["cost_per_unit_paise"] == 3114


def test_ledger_reconciles_after_every_step(sc):
    # Invariant 4: after every completed step, reconcile is clean and each balance the API
    # reports is exactly SUM(qty) of the ledger. Needs only step 0 (the seed's opening stock)
    # and gets stronger as each phase lets the scenario run further.
    sc.require(0)
    assert any(c.movements for c in sc.invariants), "no step posted any stock"
    assert [c for c in sc.invariants if c.problems or c.mismatches] == []


def test_no_orphan_movements_after_any_step(sc):
    # Invariant 6: every movement links to a source document, after every completed step.
    sc.require(0)
    assert any(c.movements for c in sc.invariants), "no step posted any stock"
    assert [c for c in sc.invariants if c.orphans] == []


def test_salesman_cannot_approve_order(sc):
    sc.require(4)
    assert sc.snap["salesman_approve_status"] == 403
