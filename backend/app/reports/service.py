"""Read-only reports over the ledger and the documents. Nothing here writes.

The stock summary is computed from the same ledger the balances come from, so
opening + receipts - issues +/- adjustments == closing, and closing == SUM(ledger as of `to`);
a test asserts both (docs/project_status.md, M7).
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.billing.models import Invoice, InvoiceLine, InvoiceStatus
from app.inventory import service as inventory
from app.inventory.models import MovementType, StockLot, StockMovement
from app.masters import service as masters
from app.masters.models import Customer, Item, ItemKind
from app.payments.models import Payment, PaymentAllocation
from app.production import service as production
from app.production.models import ProductionRun, RunStatus
from app.purchasing.models import Purchase, PurchaseLine
from app.reports.schemas import Column, Report
from app.sales.models import OrderStatus, SalesOrder

INFLOWS = (MovementType.OPENING.value, MovementType.PURCHASE.value, MovementType.OUTPUT.value)
OUTFLOWS = (MovementType.ISSUE.value, MovementType.SCRAP.value, MovementType.DISPATCH.value)
ADJUSTS = (MovementType.ADJUST.value, MovementType.REVERSAL.value)


def _cols(*pairs: tuple[str, str]) -> list[Column]:
    return [Column(key=k, label=label) for k, label in pairs]


def _qty(value: Decimal) -> str:
    return str(Decimal(value))


# ---- sales register (M8) -------------------------------------------------------------


def sales_register(db: Session, start: date, end: date) -> Report:
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.invoice_date >= start, Invoice.invoice_date <= end)
        .order_by(Invoice.fy, Invoice.seq)
    ).all()
    rows = []
    totals = {
        k: 0 for k in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise")
    }
    for inv in invoices:
        customer = masters.get_customer(db, inv.customer_id)
        rows.append(
            {
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat(),
                "customer_code": customer.code,
                "gstin": customer.gstin,
                "place_of_supply": inv.place_of_supply_state,
                "supply_type": inv.supply_type,
                "taxable_paise": inv.taxable_paise,
                "cgst_paise": inv.cgst_paise,
                "sgst_paise": inv.sgst_paise,
                "igst_paise": inv.igst_paise,
                "total_paise": inv.total_paise,
                "status": inv.status,
            }
        )
        for k in totals:
            totals[k] += getattr(inv, k)
    return Report(
        name="sales-register",
        from_=start,
        to=end,
        columns=_cols(
            ("invoice_no", "Invoice no."),
            ("invoice_date", "Date"),
            ("customer_code", "Customer"),
            ("gstin", "GSTIN"),
            ("place_of_supply", "Place of supply"),
            ("supply_type", "Supply"),
            ("taxable_paise", "Taxable (paise)"),
            ("cgst_paise", "CGST"),
            ("sgst_paise", "SGST"),
            ("igst_paise", "IGST"),
            ("total_paise", "Total"),
            ("status", "Status"),
        ),
        rows=rows,
        totals=totals,
    )


# ---- stock summary (M7) --------------------------------------------------------------


def stock_summary(db: Session, start: date, end: date) -> Report:
    period = db.execute(
        select(
            StockMovement.item_id,
            func.coalesce(
                func.sum(
                    case((StockMovement.movement_type.in_(INFLOWS), StockMovement.qty), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((StockMovement.movement_type.in_(OUTFLOWS), -StockMovement.qty), else_=0)
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case((StockMovement.movement_type.in_(ADJUSTS), StockMovement.qty), else_=0)
                ),
                0,
            ),
        )
        .where(StockMovement.movement_date >= start, StockMovement.movement_date <= end)
        .group_by(StockMovement.item_id)
    ).all()
    moves = {item_id: (Decimal(r), Decimal(i), Decimal(a)) for item_id, r, i, a in period}

    rows = []
    for item in db.scalars(select(Item).order_by(Item.code)):
        opening, _ = inventory.balance(db, item.id, as_of=start - timedelta(days=1))
        closing, closing_value = inventory.balance(db, item.id, as_of=end)
        receipts, issues, adjustments = moves.get(item.id, (Decimal(0), Decimal(0), Decimal(0)))
        rows.append(
            {
                "item_code": item.code,
                "uom": item.base_uom,
                "opening_qty": _qty(opening),
                "receipts_qty": _qty(receipts),
                "issues_qty": _qty(issues),
                "adjustments_qty": _qty(adjustments),
                "closing_qty": _qty(closing),
                "closing_value_paise": closing_value,
            }
        )
    return Report(
        name="stock-summary",
        from_=start,
        to=end,
        columns=_cols(
            ("item_code", "Item"),
            ("uom", "Unit"),
            ("opening_qty", "Opening"),
            ("receipts_qty", "Receipts"),
            ("issues_qty", "Issues"),
            ("adjustments_qty", "Adjustments"),
            ("closing_qty", "Closing"),
            ("closing_value_paise", "Closing value (paise)"),
        ),
        rows=rows,
    )


# ---- stock ledger (M7) ---------------------------------------------------------------


def stock_ledger(db: Session, start: date, end: date) -> Report:
    q = (
        select(StockMovement, Item.code, StockLot.lot_no)
        .join(Item, Item.id == StockMovement.item_id)
        .join(StockLot, StockLot.id == StockMovement.lot_id)
        .where(StockMovement.movement_date >= start, StockMovement.movement_date <= end)
        .order_by(StockMovement.id)
    )
    rows = []
    for mv, code, lot_no in db.execute(q):
        rows.append(
            {
                "movement_date": mv.movement_date.isoformat(),
                "item_code": code,
                "lot_no": lot_no,
                "movement_type": mv.movement_type,
                "qty": _qty(mv.qty),
                "value_paise": mv.value_paise,
                "source_type": mv.source_type,
                "source_id": mv.source_id,
                "source_line_id": mv.source_line_id,
            }
        )
    return Report(
        name="stock-ledger",
        from_=start,
        to=end,
        columns=_cols(
            ("movement_date", "Date"),
            ("item_code", "Item"),
            ("lot_no", "Lot"),
            ("movement_type", "Type"),
            ("qty", "Qty"),
            ("value_paise", "Value (paise)"),
            ("source_type", "Source"),
            ("source_id", "Doc id"),
            ("source_line_id", "Line id"),
        ),
        rows=rows,
    )


# ---- production (M6) -----------------------------------------------------------------


def production_report(db: Session, start: date, end: date) -> Report:
    runs = db.scalars(
        select(ProductionRun)
        .where(ProductionRun.run_date >= start, ProductionRun.run_date <= end)
        .order_by(ProductionRun.id)
    ).all()
    rows = []
    for run in runs:
        completed = run.status == RunStatus.COMPLETED.value
        cost = production.run_cost(db, run.id) if completed else None
        var = production.run_variance(db, run.id) if completed else None
        rows.append(
            {
                "run_no": run.run_no,
                "run_date": run.run_date.isoformat(),
                "item_code": masters.get_item(db, run.item_id).code,
                "status": run.status,
                "planned_qty": _qty(run.planned_qty),
                "good_qty": _qty(run.good_qty) if run.good_qty is not None else None,
                "yield_variance_bp": var.yield_.variance_bp if var else None,
                "material_paise": cost.material_paise if cost else None,
                "overhead_paise": cost.overhead_paise if cost else None,
                "cost_per_unit_paise": cost.cost_per_unit_paise if cost else None,
            }
        )
    return Report(
        name="production",
        from_=start,
        to=end,
        columns=_cols(
            ("run_no", "Run"),
            ("run_date", "Date"),
            ("item_code", "Product"),
            ("status", "Status"),
            ("planned_qty", "Planned"),
            ("good_qty", "Good output"),
            ("yield_variance_bp", "Yield var (bp)"),
            ("material_paise", "Material (paise)"),
            ("overhead_paise", "Overhead (paise)"),
            ("cost_per_unit_paise", "Cost/unit (paise)"),
        ),
        rows=rows,
    )


# ---- GST summary (S4: GSTR-1 B2B + 3B 3.1(a) outward supply totals) ------------------
#
# Lists every non-cancelled invoice of the period with its tax split, and tots them up as the
# totals row. Those totals ARE the numbers that populate table 3.1(a) of GSTR-3B for the month
# (taxable, CGST, SGST, IGST, total). A cancelled invoice drops out because its credit note has
# zeroed the supply; this matches how the ledger already handles a cancellation (gross dispatch +
# reversal adjustment).


def gst_summary(db: Session, start: date, end: date) -> Report:
    invoices = db.scalars(
        select(Invoice)
        .where(
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
            Invoice.status != InvoiceStatus.CANCELLED.value,
        )
        .order_by(Invoice.fy, Invoice.seq)
    ).all()
    rows = []
    totals = {
        k: 0 for k in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise")
    }
    for inv in invoices:
        customer = masters.get_customer(db, inv.customer_id)
        rows.append(
            {
                "invoice_no": inv.invoice_no,
                "invoice_date": inv.invoice_date.isoformat(),
                "customer_code": customer.code,
                "gstin": customer.gstin or "",
                "place_of_supply": inv.place_of_supply_state,
                "supply_type": inv.supply_type,
                "taxable_paise": inv.taxable_paise,
                "cgst_paise": inv.cgst_paise,
                "sgst_paise": inv.sgst_paise,
                "igst_paise": inv.igst_paise,
                "total_paise": inv.total_paise,
            }
        )
        for k in totals:
            totals[k] += getattr(inv, k)
    return Report(
        name="gst-summary",
        from_=start,
        to=end,
        columns=_cols(
            ("invoice_no", "Invoice no."),
            ("invoice_date", "Date"),
            ("customer_code", "Customer"),
            ("gstin", "GSTIN"),
            ("place_of_supply", "Place of supply"),
            ("supply_type", "Supply"),
            ("taxable_paise", "Taxable (paise)"),
            ("cgst_paise", "CGST"),
            ("sgst_paise", "SGST"),
            ("igst_paise", "IGST"),
            ("total_paise", "Total"),
        ),
        rows=rows,
        totals=totals,
    )


# ---- HSN summary (S4: GSTR-1 table 12) -----------------------------------------------
#
# Group non-cancelled invoice lines by HSN (the product code the government uses for GST).
# We snapshot HSN on each invoice line at issue time, so a rate change later leaves old invoices
# intact. The qty is the item's base unit (pkt for finished goods), which is also what the
# invoice carries, so no conversion is needed.


def hsn_summary(db: Session, start: date, end: date) -> Report:
    q = (
        select(InvoiceLine, Invoice)
        .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
        .where(
            Invoice.invoice_date >= start,
            Invoice.invoice_date <= end,
            Invoice.status != InvoiceStatus.CANCELLED.value,
        )
    )
    buckets: dict[str, dict] = {}
    for line, _ in db.execute(q):
        hsn = line.hsn or "-"
        key = (hsn, line.uom, line.gst_rate_bp)
        bucket = buckets.setdefault(
            key,
            {
                "hsn": hsn,
                "uom": line.uom,
                "gst_rate": f"{line.gst_rate_bp / 100:.2f}%",
                "qty": Decimal(0),
                "taxable_paise": 0,
                "cgst_paise": 0,
                "sgst_paise": 0,
                "igst_paise": 0,
                "total_paise": 0,
            },
        )
        bucket["qty"] += line.qty
        bucket["taxable_paise"] += line.taxable_paise
        bucket["cgst_paise"] += line.cgst_paise
        bucket["sgst_paise"] += line.sgst_paise
        bucket["igst_paise"] += line.igst_paise
        bucket["total_paise"] += (
            line.taxable_paise + line.cgst_paise + line.sgst_paise + line.igst_paise
        )
    rows = sorted(buckets.values(), key=lambda r: (r["hsn"], r["uom"]))
    for r in rows:
        r["qty"] = _qty(r["qty"])
    totals = {
        k: sum(int(r[k]) for r in rows)
        for k in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise")
    }
    return Report(
        name="hsn-summary",
        from_=start,
        to=end,
        columns=_cols(
            ("hsn", "HSN"),
            ("uom", "UOM"),
            ("gst_rate", "GST"),
            ("qty", "Qty"),
            ("taxable_paise", "Taxable (paise)"),
            ("cgst_paise", "CGST"),
            ("sgst_paise", "SGST"),
            ("igst_paise", "IGST"),
            ("total_paise", "Total"),
        ),
        rows=rows,
        totals=totals,
    )


# ---- Payments register (S2) ----------------------------------------------------------
#
# Every receipt of the period with its allocations spelled out ("applied to INV-x, INV-y ..."),
# so a quick audit can match deposits to invoices without opening each payment.


def payments_register(db: Session, start: date, end: date) -> Report:
    payments = db.scalars(
        select(Payment)
        .where(Payment.payment_date >= start, Payment.payment_date <= end)
        .order_by(Payment.payment_date, Payment.id)
    ).all()
    # One query for the invoice numbers all these payments touch.
    alloc_rows = (
        db.execute(
            select(PaymentAllocation.payment_id, Invoice.invoice_no, PaymentAllocation.amount_paise)
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .where(PaymentAllocation.payment_id.in_([p.id for p in payments]))
            .order_by(PaymentAllocation.id)
        ).all()
        if payments
        else []
    )
    applied: dict[int, list[str]] = {}
    for pid, inv_no, amount in alloc_rows:
        applied.setdefault(pid, []).append(f"{inv_no} ({amount})")
    rows = []
    total_amount = 0
    for p in payments:
        customer = masters.get_customer(db, p.customer_id)
        rows.append(
            {
                "payment_date": p.payment_date.isoformat(),
                "customer_code": customer.code,
                "reference": p.reference or "",
                "amount_paise": p.amount_paise,
                "applied_to": ", ".join(applied.get(p.id, [])),
            }
        )
        total_amount += p.amount_paise
    return Report(
        name="payments-register",
        from_=start,
        to=end,
        columns=_cols(
            ("payment_date", "Date"),
            ("customer_code", "Customer"),
            ("reference", "Reference"),
            ("amount_paise", "Amount (paise)"),
            ("applied_to", "Applied to"),
        ),
        rows=rows,
        totals={"amount_paise": total_amount},
    )


# ---- Ageing (S2: receivables bucketed by how old the invoice is) ---------------------
#
# As of the period's `to` date, for each non-cancelled invoice with an unpaid balance, place
# that balance in a bucket by (to - invoice_date). Outstanding is derived here the same way
# payments.service does it (invoice.total - SUM(allocations)), so a single source of truth.


AGE_BUCKETS = (
    ("b0_30_paise", 0, 30),
    ("b31_60_paise", 31, 60),
    ("b61_90_paise", 61, 90),
    ("b91plus_paise", 91, 10**9),
)


def ageing(db: Session, start: date, end: date) -> Report:
    invoices = db.scalars(
        select(Invoice)
        .where(
            Invoice.status != InvoiceStatus.CANCELLED.value,
            Invoice.invoice_date <= end,
        )
        .order_by(Invoice.customer_id, Invoice.invoice_date, Invoice.id)
    ).all()
    allocated_rows = db.execute(
        select(
            PaymentAllocation.invoice_id, func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)
        ).group_by(PaymentAllocation.invoice_id)
    ).all()
    allocated = {inv_id: int(total) for inv_id, total in allocated_rows}
    rows = []
    totals = {name: 0 for name, _, _ in AGE_BUCKETS}
    totals["outstanding_paise"] = 0
    for inv in invoices:
        paid = allocated.get(inv.id, 0)
        owing = inv.total_paise - paid
        if owing <= 0:
            continue
        customer = masters.get_customer(db, inv.customer_id)
        age = (end - inv.invoice_date).days
        row = {
            "customer_code": customer.code,
            "invoice_no": inv.invoice_no,
            "invoice_date": inv.invoice_date.isoformat(),
            "age_days": age,
            "total_paise": inv.total_paise,
            "paid_paise": paid,
            "outstanding_paise": owing,
        }
        for name, lo, hi in AGE_BUCKETS:
            row[name] = owing if lo <= age <= hi else 0
            totals[name] += row[name]
        totals["outstanding_paise"] += owing
        rows.append(row)
    return Report(
        name="ageing",
        from_=start,
        to=end,
        columns=_cols(
            ("customer_code", "Customer"),
            ("invoice_no", "Invoice"),
            ("invoice_date", "Date"),
            ("age_days", "Age (days)"),
            ("total_paise", "Invoice total (paise)"),
            ("paid_paise", "Paid"),
            ("outstanding_paise", "Outstanding"),
            ("b0_30_paise", "0-30 days"),
            ("b31_60_paise", "31-60 days"),
            ("b61_90_paise", "61-90 days"),
            ("b91plus_paise", "91+ days"),
        ),
        rows=rows,
        totals=totals,
    )


# ---- Owner dashboard (S6) ------------------------------------------------------------
#
# A handful of numbers the owner can scan in a second: finished-goods stock on hand, pending
# orders, sales and collections for the period, total receivables, and production runs done.
# Every figure is computed from the same tables the detailed reports read, so no number here
# can drift from a report (or from the ledger) by construction.


def dashboard(db: Session, start: date, end: date) -> dict:
    fg_items = db.scalars(
        select(Item).where(Item.kind == ItemKind.FG.value).order_by(Item.code)
    ).all()
    fg_qty = Decimal(0)
    fg_value = 0
    fg_lines = []
    for item in fg_items:
        qty, value = inventory.balance(db, item.id, as_of=end)
        fg_qty += qty
        fg_value += value
        fg_lines.append(
            {
                "item_code": item.code,
                "name": item.name,
                "qty": _qty(qty),
                "uom": item.base_uom,
                "value_paise": int(value),
            }
        )
    pending_orders = int(
        db.scalar(
            select(func.count(SalesOrder.id)).where(
                SalesOrder.status == OrderStatus.PENDING.value,
                SalesOrder.order_date <= end,
            )
        )
        or 0
    )
    sales_paise = int(
        db.scalar(
            select(func.coalesce(func.sum(Invoice.total_paise), 0)).where(
                Invoice.invoice_date >= start,
                Invoice.invoice_date <= end,
                Invoice.status != InvoiceStatus.CANCELLED.value,
            )
        )
        or 0
    )
    invoices_count = int(
        db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.invoice_date >= start,
                Invoice.invoice_date <= end,
                Invoice.status != InvoiceStatus.CANCELLED.value,
            )
        )
        or 0
    )
    collections_paise = int(
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(
                Payment.payment_date >= start,
                Payment.payment_date <= end,
            )
        )
        or 0
    )
    non_cancelled_total = int(
        db.scalar(
            select(func.coalesce(func.sum(Invoice.total_paise), 0)).where(
                Invoice.status != InvoiceStatus.CANCELLED.value,
                Invoice.invoice_date <= end,
            )
        )
        or 0
    )
    allocated_total = int(
        db.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0))
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .where(
                Invoice.status != InvoiceStatus.CANCELLED.value,
                Invoice.invoice_date <= end,
            )
        )
        or 0
    )
    outstanding_paise = non_cancelled_total - allocated_total
    completed_runs = int(
        db.scalar(
            select(func.count(ProductionRun.id)).where(
                ProductionRun.run_date >= start,
                ProductionRun.run_date <= end,
                ProductionRun.status == RunStatus.COMPLETED.value,
            )
        )
        or 0
    )
    # Flagged variances for the dashboard banner — re-use the variance-alerts report so the
    # headline can't disagree with the detail page.
    flagged_variances = len(variance_alerts(db, start, end).rows)
    customers_count = int(db.scalar(select(func.count(Customer.id))) or 0)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "fg_qty_total": _qty(fg_qty),
        "fg_value_paise": int(fg_value),
        "fg_lines": fg_lines,
        "pending_orders": pending_orders,
        "sales_paise": sales_paise,
        "invoices_count": invoices_count,
        "collections_paise": collections_paise,
        "outstanding_paise": outstanding_paise,
        "completed_runs": completed_runs,
        "flagged_variances": flagged_variances,
        "active_customers": customers_count,
    }


# ---- Purchase register (S1) ----------------------------------------------------------
#
# Every goods-received note of the period with its supplier, line count and tax split. Purchase
# totals are stored on the document (like invoices), so the sums here match what the ledger
# capitalised at receipt. Input GST is informational (A15 — never costed into stock value).


def purchase_register(db: Session, start: date, end: date) -> Report:
    purchases = db.scalars(
        select(Purchase)
        .where(Purchase.purchase_date >= start, Purchase.purchase_date <= end)
        .order_by(Purchase.purchase_date, Purchase.id)
    ).all()
    line_counts = (
        dict(
            db.execute(
                select(PurchaseLine.purchase_id, func.count(PurchaseLine.id))
                .where(PurchaseLine.purchase_id.in_([p.id for p in purchases]))
                .group_by(PurchaseLine.purchase_id)
            ).all()
        )
        if purchases
        else {}
    )
    rows = []
    totals = {
        k: 0 for k in ("taxable_paise", "cgst_paise", "sgst_paise", "igst_paise", "total_paise")
    }
    for p in purchases:
        supplier = masters.get_supplier(db, p.supplier_id)
        rows.append(
            {
                "purchase_date": p.purchase_date.isoformat(),
                "bill_no": p.bill_no or "",
                "supplier_code": supplier.code,
                "gstin": supplier.gstin or "",
                "supply_type": p.supply_type,
                "lines": int(line_counts.get(p.id, 0)),
                "taxable_paise": p.taxable_paise,
                "cgst_paise": p.cgst_paise,
                "sgst_paise": p.sgst_paise,
                "igst_paise": p.igst_paise,
                "total_paise": p.total_paise,
            }
        )
        for k in totals:
            totals[k] += getattr(p, k)
    return Report(
        name="purchase-register",
        from_=start,
        to=end,
        columns=_cols(
            ("purchase_date", "Date"),
            ("bill_no", "Bill no."),
            ("supplier_code", "Supplier"),
            ("gstin", "GSTIN"),
            ("supply_type", "Supply"),
            ("lines", "Lines"),
            ("taxable_paise", "Taxable (paise)"),
            ("cgst_paise", "CGST"),
            ("sgst_paise", "SGST"),
            ("igst_paise", "IGST"),
            ("total_paise", "Total"),
        ),
        rows=rows,
        totals=totals,
    )


# ---- Variance alerts (S5) ------------------------------------------------------------
#
# Every completed run of the period, one row per flagged line (yield or a material) — the ones
# whose |variance| exceeded the item's tolerance (A2). Nothing new is computed: this re-uses
# production.run_variance(), so the alerts can't disagree with the per-run variance screen.


def variance_alerts(db: Session, start: date, end: date) -> Report:
    runs = db.scalars(
        select(ProductionRun)
        .where(
            ProductionRun.run_date >= start,
            ProductionRun.run_date <= end,
            ProductionRun.status == RunStatus.COMPLETED.value,
        )
        .order_by(ProductionRun.run_date, ProductionRun.id)
    ).all()
    rows = []
    for run in runs:
        var = production.run_variance(db, run.id)
        product = masters.get_item(db, run.item_id)
        if var.yield_.flagged:
            rows.append(
                {
                    "run_no": run.run_no,
                    "run_date": run.run_date.isoformat(),
                    "product": product.code,
                    "kind": "yield",
                    "item_code": product.code,
                    "uom": product.base_uom,
                    "planned_qty": _qty(var.yield_.planned_qty),
                    "actual_qty": _qty(var.yield_.actual_qty),
                    "variance_bp": var.yield_.variance_bp,
                    "variance_pct": f"{var.yield_.variance_bp / 100:.2f}%",
                }
            )
        for line in var.lines:
            if line.flagged:
                rows.append(
                    {
                        "run_no": run.run_no,
                        "run_date": run.run_date.isoformat(),
                        "product": product.code,
                        "kind": "consumption",
                        "item_code": line.item_code,
                        "uom": line.uom,
                        "planned_qty": _qty(line.planned_qty),
                        "actual_qty": _qty(line.actual_qty),
                        "variance_bp": line.variance_bp,
                        "variance_pct": f"{line.variance_bp / 100:.2f}%",
                    }
                )
    return Report(
        name="variance-alerts",
        from_=start,
        to=end,
        columns=_cols(
            ("run_no", "Run"),
            ("run_date", "Date"),
            ("product", "Product"),
            ("kind", "Kind"),
            ("item_code", "Item"),
            ("uom", "Unit"),
            ("planned_qty", "Planned"),
            ("actual_qty", "Actual"),
            ("variance_pct", "Variance"),
        ),
        rows=rows,
        totals={"flagged_count": len(rows)},
    )


BUILDERS = {
    "sales-register": sales_register,
    "stock-summary": stock_summary,
    "stock-ledger": stock_ledger,
    "production": production_report,
    "gst-summary": gst_summary,
    "hsn-summary": hsn_summary,
    "payments-register": payments_register,
    "ageing": ageing,
    "purchase-register": purchase_register,
    "variance-alerts": variance_alerts,
}
