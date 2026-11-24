"""Hostile audit after P7 (reports + invoice PDF). P7 is read-only: the reports, exports and PDF
write nothing to the ledger, so the only way to break the books here is a report, export or PDF
that DISAGREES with the ledger / invoices it claims to summarise, or that drops, duplicates or
mis-buckets rows.

Every test below is a `# guard`: it passes and proves a control holds. No finding was confirmed --
P7 survived every attack:

- The stock-summary identity opening + receipts - issues +/- adjustments == closing holds for
  EVERY item after a purchase / run / dispatch / credit-note(REVERSAL) scenario, and the reported
  closing qty AND value equal SUM(stock_movement) as of `to` and the /stock/balance endpoint.
- Period bucketing is inclusive on both `from` and `to` with no off-by-one: a movement dated on
  `from` is in the period (not in opening), one dated on `to` is in the period and in closing. A
  REVERSAL lands in adjustments and a COST_ADJUST (qty 0) moves no qty column.
- The sales register shows every invoice in the period exactly once (a cancelled one still shown
  with status CANCELLED), and its column totals equal the SUM of the row values.
- CSV and XLSX carry the same headers, rows (same order, none dropped/duplicated) and the same
  numbers as the JSON envelope, cell by cell, including the totals row; money is not reformatted.
- The invoice PDF renders (%PDF) and the invoice it is built from has its per-line CGST+SGST+IGST
  summing to the line tax and the line totals summing to invoice.total_paise; a cancelled invoice
  still renders.
- sales/production get 403 on every report and on the PDF; an unknown report name is 404.

Helpers (sandbox/buy/start/balance/user_id) come from the P4 suite and the sales/billing helpers
(fg_with_stock/make_customer/place/approve/raise_invoice/dispatch/cancel/fresh_key) from the P5
suite, so the fixtures and style match exactly.
"""

import csv
import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.core.db import engine
from tests.audit.test_p4_ledger_audit import balance
from tests.audit.test_p5_sales_billing_audit import (
    approve,
    cancel,
    dispatch,
    fg_with_stock,
    fresh_key,
    make_customer,
    place,
    raise_invoice,
)

pytestmark = pytest.mark.usefixtures("seeded_db")
API = "/api/v1"
D = Decimal

PERIOD = {"from": "2026-11-01", "to": "2026-11-30"}


# ---- helpers -----------------------------------------------------------------------------


def report(client, as_user, name, params, *, fmt="json", who="accountant"):
    q = {**params, "format": fmt}
    return client.get(f"{API}/reports/{name}", params=q, headers=as_user(who))


def item_code(item_id: int) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT code FROM item WHERE id = :i"), {"i": item_id}
        ).scalar_one()


def ledger_sums(as_of: str) -> dict[str, tuple[Decimal, int]]:
    """SUM(qty), SUM(value_paise) per item code from the raw ledger as of a date -- the ground
    truth the stock summary must reproduce."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT i.code, COALESCE(SUM(m.qty), 0) AS q,"
                "       COALESCE(SUM(m.value_paise), 0) AS v "
                "FROM item i LEFT JOIN stock_movement m"
                "  ON m.item_id = i.id AND m.movement_date <= :to "
                "GROUP BY i.code"
            ),
            {"to": as_of},
        ).all()
    return {code: (D(q), int(v)) for code, q, v in rows}


def build_dispatch_then_cancel(client, as_user, pkts="300", ship="150"):
    """A full stock scenario: a run outputs `pkts` FG (OUTPUT, 2026-11-02), an invoice dispatches
    `ship` of them (DISPATCH, 2026-11-03), then the invoice is cancelled (REVERSAL, 2026-11-04).
    Returns the FG item id and the invoice."""
    fg = fg_with_stock(client, as_user, pkts)
    cust = make_customer(client, as_user)
    oid = place(client, as_user, fresh_key("p7"), cust, fg, ship).json()["id"]
    assert approve(client, as_user, oid).status_code == 200
    inv = raise_invoice(client, as_user, oid).json()
    assert dispatch(client, as_user, inv["id"]).status_code == 200
    assert cancel(client, as_user, inv["id"]).status_code == 200
    return fg, inv


def _norm(v: object) -> str:
    return "" if v is None else str(v)


# ---- stock summary vs the ledger ---------------------------------------------------------


def test_stock_summary_reconciles_with_the_ledger_for_every_item(client, as_user) -> None:  # guard
    """opening + receipts - issues +/- adjustments == closing for EVERY item, and the reported
    closing qty AND value equal SUM(stock_movement) as of `to`. Built on a scenario that exercises
    OUTPUT, DISPATCH and a REVERSAL (so adjustments is non-zero), plus whatever the seed created."""
    fg, _inv = build_dispatch_then_cancel(client, as_user)
    rows = report(client, as_user, "stock-summary", PERIOD).json()["rows"]
    truth = ledger_sums(PERIOD["to"])
    assert rows, "the summary listed no items"
    for row in rows:
        opening = D(row["opening_qty"])
        receipts = D(row["receipts_qty"])
        issues = D(row["issues_qty"])
        adjustments = D(row["adjustments_qty"])
        closing = D(row["closing_qty"])
        # the report's own identity
        assert opening + receipts - issues + adjustments == closing, row
        # the closing it printed equals the raw ledger SUM (qty AND value)
        q, v = truth[row["item_code"]]
        assert closing == q, f"{row['item_code']}: summary closing {closing} vs ledger {q}"
        assert (
            row["closing_value_paise"] == v
        ), f"{row['item_code']}: summary value {row['closing_value_paise']} vs ledger {v}"
    # and the printed closing equals the /stock/balance endpoint for the FG we built
    fg_row = next(r for r in rows if r["item_code"] == item_code(fg))
    assert D(fg_row["closing_qty"]) == balance(client, as_user, fg, as_of=PERIOD["to"])[0] == D(300)


def test_stock_summary_buckets_output_dispatch_and_reversal_correctly(
    client, as_user
) -> None:  # guard
    """A REVERSAL (credit note) must land in adjustments, a DISPATCH in issues, an OUTPUT in
    receipts, and `from`/`to` are inclusive with no off-by-one: a day-window on each movement's
    date shows it, and opening (as of the day before) excludes it."""
    fg, _inv = build_dispatch_then_cancel(client, as_user)
    code = item_code(fg)

    def fg_row(day):
        rows = report(client, as_user, "stock-summary", {"from": day, "to": day}).json()["rows"]
        return next(r for r in rows if r["item_code"] == code)

    # OUTPUT +300 on 2026-11-02: in receipts, opening still 0 (`from` not double-counted as opening)
    out = fg_row("2026-11-02")
    assert (D(out["opening_qty"]), D(out["receipts_qty"]), D(out["closing_qty"])) == (0, 300, 300)
    # DISPATCH -150 on 2026-11-03: in issues (positive), opening is the 300 from the day before
    disp = fg_row("2026-11-03")
    assert (D(disp["opening_qty"]), D(disp["issues_qty"]), D(disp["closing_qty"])) == (
        300,
        150,
        150,
    )
    assert D(disp["adjustments_qty"]) == 0
    # REVERSAL +150 on 2026-11-04: in adjustments, not issues; stock returns to 300
    rev = fg_row("2026-11-04")
    assert (D(rev["opening_qty"]), D(rev["adjustments_qty"]), D(rev["closing_qty"])) == (
        150,
        150,
        300,
    )
    assert D(rev["issues_qty"]) == 0


def test_cost_adjust_does_not_move_a_quantity_column(client, as_user) -> None:  # guard
    """Overheads post a COST_ADJUST (qty 0, value only) on the FG lot. It must change the closing
    VALUE but no quantity column, and the qty identity must still hold."""
    fg = fg_with_stock(client, as_user, "100")
    # find the run and add an overhead (value-only COST_ADJUST on the FG lot)
    with engine.connect() as conn:
        run_id = conn.execute(
            text(
                "SELECT source_id FROM stock_movement WHERE item_id = :i AND movement_type='OUTPUT'"
            ),
            {"i": fg},
        ).scalar_one()
    r = client.post(
        f"{API}/production-runs/{run_id}/overheads",
        json={"lines": [{"kind": "LABOUR", "amount_paise": 5000}]},
        headers=as_user("production"),
    )
    assert r.status_code in (200, 201), r.text
    rows = report(client, as_user, "stock-summary", PERIOD).json()["rows"]
    code = item_code(fg)
    row = next(r for r in rows if r["item_code"] == code)
    # qty identity holds, receipts == the 100 output only (COST_ADJUST added no qty)
    assert D(row["opening_qty"]) + D(row["receipts_qty"]) - D(row["issues_qty"]) + D(
        row["adjustments_qty"]
    ) == D(row["closing_qty"])
    assert D(row["receipts_qty"]) == 100
    assert D(row["adjustments_qty"]) == 0 and D(row["issues_qty"]) == 0
    # the value carries the overhead, and equals the raw ledger value
    _q, v = ledger_sums(PERIOD["to"])[code]
    assert row["closing_value_paise"] == v


# ---- sales register ----------------------------------------------------------------------


def test_sales_register_totals_equal_the_sum_of_the_rows(client, as_user) -> None:  # guard
    build_dispatch_then_cancel(client, as_user)  # at least one (cancelled) invoice in the period
    rep = report(client, as_user, "sales-register", PERIOD).json()
    assert rep["rows"], "no invoices in the register"
    for key in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise"):
        assert rep["totals"][key] == sum(row[key] for row in rep["rows"]), key


def test_sales_register_shows_each_invoice_once_including_cancelled(client, as_user) -> None:
    # guard
    _fg, inv = build_dispatch_then_cancel(client, as_user)
    rep = report(client, as_user, "sales-register", PERIOD).json()
    matching = [r for r in rep["rows"] if r["invoice_no"] == inv["invoice_no"]]
    assert len(matching) == 1, "the invoice is missing or duplicated in the register"
    assert matching[0]["status"] == "CANCELLED"  # a cancelled invoice is still shown, with status


# ---- exports: CSV and XLSX carry exactly the JSON numbers --------------------------------


@pytest.mark.parametrize("name", ["sales-register", "stock-summary"])
def test_csv_matches_the_json_cell_for_cell(client, as_user, name) -> None:  # guard
    build_dispatch_then_cancel(client, as_user)
    rep = report(client, as_user, name, PERIOD).json()
    body = report(client, as_user, name, PERIOD, fmt="csv").content
    assert body[:3] == b"\xef\xbb\xbf"  # utf-8-sig BOM so Excel reads the rupee sign
    reader = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    labels = [c["label"] for c in rep["columns"]]
    keys = [c["key"] for c in rep["columns"]]
    assert reader[0] == labels
    data = reader[1:]
    if rep.get("totals"):
        data, totals_row = data[:-1], data[-1]
        expected_totals = ["TOTAL"] + [_norm(rep["totals"].get(k, "")) for k in keys[1:]]
        assert totals_row == expected_totals
    assert len(data) == len(rep["rows"]), "CSV dropped or duplicated a row"
    for csv_row, json_row in zip(data, rep["rows"], strict=True):
        assert csv_row == [_norm(json_row.get(k)) for k in keys]


@pytest.mark.parametrize("name", ["sales-register", "stock-summary"])
def test_xlsx_matches_the_json_cell_for_cell(client, as_user, name) -> None:  # guard
    build_dispatch_then_cancel(client, as_user)
    rep = report(client, as_user, name, PERIOD).json()
    body = report(client, as_user, name, PERIOD, fmt="xlsx").content
    sheet = load_workbook(io.BytesIO(body)).active
    grid = [[_norm(v) for v in row] for row in sheet.iter_rows(values_only=True)]
    labels = [c["label"] for c in rep["columns"]]
    keys = [c["key"] for c in rep["columns"]]
    assert grid[0] == labels
    data = grid[1:]
    if rep.get("totals"):
        data, totals_row = data[:-1], data[-1]
        assert totals_row == ["TOTAL"] + [_norm(rep["totals"].get(k, "")) for k in keys[1:]]
    assert len(data) == len(rep["rows"]), "XLSX dropped or duplicated a row"
    for xlsx_row, json_row in zip(data, rep["rows"], strict=True):
        assert xlsx_row == [_norm(json_row.get(k)) for k in keys]


# ---- invoice PDF -------------------------------------------------------------------------


def _invoice(client, as_user, state="33"):
    fg = fg_with_stock(client, as_user, "50")
    cust = make_customer(client, as_user, state_code=state)
    oid = place(client, as_user, fresh_key("pdf"), cust, fg, "10").json()["id"]
    assert approve(client, as_user, oid).status_code == 200
    return raise_invoice(client, as_user, oid).json()


@pytest.mark.parametrize("state", ["33", "29"])  # INTRA (CGST+SGST) and INTER (IGST)
def test_invoice_lines_sum_to_the_total_the_pdf_prints(client, as_user, state) -> None:  # guard
    """The PDF prints numbers straight off the invoice row. Prove the source is internally exact:
    each line's CGST+SGST+IGST and taxable sum to the invoice header, and the line totals
    (taxable + tax) sum to total_paise -- so the PDF cannot print a total its lines don't make."""
    inv = _invoice(client, as_user, state=state)
    lines = inv["lines"]
    assert sum(line["taxable_paise"] for line in lines) == inv["taxable_paise"]
    assert sum(line["cgst_paise"] for line in lines) == inv["cgst_paise"]
    assert sum(line["sgst_paise"] for line in lines) == inv["sgst_paise"]
    assert sum(line["igst_paise"] for line in lines) == inv["igst_paise"]
    line_total = sum(
        line["taxable_paise"] + line["cgst_paise"] + line["sgst_paise"] + line["igst_paise"]
        for line in lines
    )
    assert line_total == inv["total_paise"]
    assert (
        inv["taxable_paise"] + inv["cgst_paise"] + inv["sgst_paise"] + inv["igst_paise"]
        == (inv["total_paise"])
    )


def test_invoice_pdf_renders(client, as_user) -> None:  # guard
    inv = _invoice(client, as_user)
    r = client.get(f"{API}/invoices/{inv['id']}/pdf", headers=as_user("accountant"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_cancelled_invoice_pdf_still_renders(client, as_user) -> None:  # guard
    inv = _invoice(client, as_user)
    assert cancel(client, as_user, inv["id"]).status_code == 200
    r = client.get(f"{API}/invoices/{inv['id']}/pdf", headers=as_user("accountant"))
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"


# ---- RBAC --------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["salesman_a", "production"])
@pytest.mark.parametrize("name", ["sales-register", "stock-summary", "stock-ledger", "production"])
def test_sales_and_production_cannot_read_reports(client, as_user, who, name) -> None:  # guard
    assert report(client, as_user, name, PERIOD, who=who).status_code == 403


@pytest.mark.parametrize("who", ["salesman_a", "production"])
def test_sales_and_production_cannot_read_the_pdf(client, as_user, who) -> None:  # guard
    inv = _invoice(client, as_user)
    r = client.get(f"{API}/invoices/{inv['id']}/pdf", headers=as_user(who))
    assert r.status_code == 403, r.text


def test_unknown_report_name_is_404(client, as_user) -> None:  # guard
    assert report(client, as_user, "cost-sheet", PERIOD).status_code == 404
