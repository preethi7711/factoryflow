"""Read-only reports over the ledger and the documents. Nothing here writes.

The stock summary is computed from the same ledger the balances come from, so
opening + receipts - issues +/- adjustments == closing, and closing == SUM(ledger as of `to`);
a test asserts both (docs/project_status.md, M7).
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.billing.models import Invoice
from app.inventory import service as inventory
from app.inventory.models import MovementType, StockLot, StockMovement
from app.masters import service as masters
from app.masters.models import Item
from app.production import service as production
from app.production.models import ProductionRun, RunStatus
from app.reports.schemas import Column, Report

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


BUILDERS = {
    "sales-register": sales_register,
    "stock-summary": stock_summary,
    "stock-ledger": stock_ledger,
    "production": production_report,
}
