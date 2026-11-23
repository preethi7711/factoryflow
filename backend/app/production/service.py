"""Production runs (docs/architecture.md section 5, "Production post").

Stock moves only through inventory.post_movements(). Each public function is one transaction:
the run, its movements and its audit row commit together or not at all.
"""

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import AppUser
from app.core.clock import now_ist, start_of_day
from app.core.errors import AppError, not_found
from app.core.units import check_qty_scale
from app.core.variance import planned_qty, variance
from app.core.wac import cost_per_unit_paise
from app.inventory import service as inventory
from app.inventory.models import MovementType, SourceType
from app.inventory.service import MovementLine
from app.masters import service as masters
from app.production.models import ProductionRun, RunConsumption, RunOverhead, RunStatus
from app.production.schemas import (
    CostOut,
    OverheadCreate,
    OverheadOut,
    OverheadsOut,
    QtyLine,
    RunComplete,
    RunCreate,
    RunLineOut,
    RunOut,
    VarianceLineOut,
    VarianceOut,
    VarianceRow,
)

RUN = SourceType.PRODUCTION_RUN
_QTY_STEP = Decimal("0.001")


def _plan(per_batch: Decimal, batches: Decimal) -> Decimal:
    """BOM quantity x batches, half-up to the quantity scale (a plan, not a measurement)."""
    return planned_qty(per_batch, batches).quantize(_QTY_STEP, rounding=ROUND_HALF_UP)


def _get(db: Session, run_id: int, *, lock: bool = False) -> ProductionRun:
    q = select(ProductionRun).where(ProductionRun.id == run_id)
    if lock:
        q = q.with_for_update()  # a concurrent complete/overhead call waits here
    run = db.scalar(q)
    if run is None:
        raise not_found("production run", run_id)
    return run


def _require_completed(run: ProductionRun) -> None:
    if run.status != RunStatus.COMPLETED:
        raise AppError(409, "RUN_NOT_COMPLETED", f"{run.run_no} is not completed yet")


def _actuals(db: Session, run: ProductionRun) -> dict[int, Decimal]:
    """Issued quantity per consumption line, read from the ledger (issues are negative there)."""
    issued = inventory.source_qty_by_line(db, RUN, run.id, MovementType.ISSUE)
    return {line_id: -qty for line_id, qty in issued.items()}


def run_out(db: Session, run: ProductionRun) -> RunOut:
    actual = _actuals(db, run)
    lines = []
    for consumption in run.lines:
        item = masters.get_item(db, consumption.item_id)
        lines.append(
            RunLineOut(
                item_id=item.id,
                item_code=item.code,
                uom=item.base_uom,
                planned_qty=consumption.planned_qty,
                actual_qty=actual.get(consumption.id, Decimal(0)),
                damaged_qty=consumption.damaged_qty,
            )
        )
    lot_no = inventory.get_lot(db, run.output_lot_id).lot_no if run.output_lot_id else None
    return RunOut(
        id=run.id,
        run_no=run.run_no,
        bom_id=run.bom_id,
        item_id=run.item_id,
        item_code=masters.get_item(db, run.item_id).code,
        batches=run.batches,
        run_date=run.run_date,
        status=run.status,
        planned_qty=run.planned_qty,
        good_qty=run.good_qty,
        output_lot_no=lot_no,
        lines=lines,
    )


def _resolve(db: Session, run: ProductionRun, line_in: QtyLine) -> tuple[RunConsumption, Decimal]:
    """The run's BOM line for this item, and the quantity in the item's base unit."""
    consumption = next((c for c in run.lines if c.item_id == line_in.item_id), None)
    if consumption is None:
        raise AppError(422, "NOT_IN_BOM", f"item {line_in.item_id} is not in {run.run_no}'s BOM")
    item = masters.get_item(db, line_in.item_id)
    return consumption, masters.base_qty(line_in.qty, line_in.uom, item)


def _issue(db: Session, run: ProductionRun, issues: list[QtyLine], user: AppUser) -> None:
    if not issues:
        return
    lines = []
    for line_in in issues:
        consumption, qty = _resolve(db, run, line_in)
        lines.append(
            MovementLine(
                consumption.item_id, -qty, MovementType.ISSUE, source_line_id=consumption.id
            )
        )
    inventory.post_movements(
        db,
        source_type=RUN,
        source_id=run.id,
        movement_date=run.run_date,
        user_id=user.id,
        lines=lines,
    )


def get_run(db: Session, run_id: int) -> RunOut:
    return run_out(db, _get(db, run_id))


def start_run(db: Session, data: RunCreate, user: AppUser) -> RunOut:
    """Create the run with its planned lines and issue what is issued at the start."""
    bom = masters.get_bom(db, data.bom_id)
    if not bom.is_active:
        raise AppError(422, "BOM_INACTIVE", f"{bom.code} is not the active BOM")
    try:
        batches = check_qty_scale(data.batches)
    except ValueError as exc:
        raise AppError(422, "INVALID_QUANTITY", str(exc)) from None
    run = ProductionRun(
        bom_id=bom.id,
        item_id=bom.item_id,
        batches=batches,
        run_date=data.run_date,
        status=RunStatus.DRAFT.value,
        planned_qty=_plan(bom.output_qty, batches),
        created_by=user.id,
    )
    db.add(run)
    db.flush()
    for bom_line in bom.lines:
        planned = _plan(bom_line.qty, batches)
        db.add(RunConsumption(run_id=run.id, item_id=bom_line.item_id, planned_qty=planned))
    db.flush()
    db.expire(run, ["lines"])  # reload the lines just inserted
    _issue(db, run, data.issues, user)
    out = run_out(db, run)
    after = out.model_dump(mode="json")
    audit.record(
        db, entity="production_run", entity_id=run.id, action="START", user_id=user.id, after=after
    )
    db.commit()
    return out


def complete_run(db: Session, run_id: int, data: RunComplete, user: AppUser) -> RunOut:
    """Issue the rest, record damage, create the FG lot and post OUTPUT at material cost."""
    run = _get(db, run_id, lock=True)
    if run.status != RunStatus.DRAFT:
        raise AppError(409, "RUN_ALREADY_COMPLETED", f"{run.run_no} is already completed")
    before = run_out(db, run).model_dump(mode="json")

    _issue(db, run, data.issues, user)
    actual = _actuals(db, run)
    if not actual:
        raise AppError(422, "NOTHING_ISSUED", f"{run.run_no} has no issues to make output from")
    for line_in in data.damaged:
        consumption, qty = _resolve(db, run, line_in)
        damaged = consumption.damaged_qty + qty
        issued = actual.get(consumption.id, Decimal(0))
        if damaged > issued:
            raise AppError(
                422,
                "DAMAGED_EXCEEDS_ISSUED",
                f"damaged {damaged} is more than the {issued} issued (item {consumption.item_id})",
            )
        consumption.damaged_qty = damaged  # info only: the damaged units are already in the issue

    product = masters.get_item(db, run.item_id)
    good = masters.base_qty(data.output_qty, data.output_uom or product.base_uom, product)
    expiry = (
        run.run_date + timedelta(days=product.shelf_life_days) if product.shelf_life_days else None
    )
    lot = inventory.create_lot(
        db,
        item_id=product.id,
        lot_no=run.run_no,
        received_at=start_of_day(run.run_date),
        source_type=RUN,
        source_id=run.id,
        mfg_date=run.run_date,
        expiry_date=expiry,
    )
    # The output carries exactly what was issued (materials); overheads come later (A7, A14).
    material = -inventory.source_value(db, RUN, run.id, MovementType.ISSUE)
    output = MovementLine(
        product.id,
        good,
        MovementType.OUTPUT,
        source_line_id=run.id,
        lot_id=lot.id,
        value_paise=material,
    )
    inventory.post_movements(
        db,
        source_type=RUN,
        source_id=run.id,
        movement_date=run.run_date,
        user_id=user.id,
        lines=[output],
    )
    run.status = RunStatus.COMPLETED.value
    run.good_qty = good
    run.output_lot_id = lot.id
    run.completed_by = user.id
    run.completed_at = now_ist()
    db.flush()
    out = run_out(db, run)
    audit.record(
        db,
        entity="production_run",
        entity_id=run.id,
        action="COMPLETE",
        user_id=user.id,
        before=before,
        after=out.model_dump(mode="json"),
    )
    db.commit()
    return out


def add_overheads(db: Session, run_id: int, data: OverheadCreate, user: AppUser) -> OverheadsOut:
    """Labour, gas/power etc. for a completed run: value-only COST_ADJUST on its FG lot (A14)."""
    run = _get(db, run_id, lock=True)
    _require_completed(run)
    assert run.output_lot_id is not None  # guaranteed by the completed_has_output CHECK
    if inventory.balance(db, run.item_id)[0] == 0:
        raise AppError(
            409, "NO_STOCK_FOR_OVERHEAD", "all of this product is sold; overheads can't be stocked"
        )
    rows = []
    for line_in in data.lines:
        row = RunOverhead(
            run_id=run.id,
            kind=line_in.kind.value,
            amount_paise=line_in.amount_paise,
            note=line_in.note,
            created_by=user.id,
        )
        db.add(row)
        db.flush()
        rows.append(row)
    # Dated on the run date, so the run's cost (and its FG lot's value) is complete as of that day.
    inventory.post_movements(
        db,
        source_type=RUN,
        source_id=run.id,
        movement_date=run.run_date,
        user_id=user.id,
        lines=[
            MovementLine(
                run.item_id,
                Decimal(0),
                MovementType.COST_ADJUST,
                source_line_id=row.id,
                lot_id=run.output_lot_id,
                value_paise=row.amount_paise,
            )
            for row in rows
        ],
    )
    db.expire(run, ["overheads"])
    out = OverheadsOut(
        run_id=run.id,
        overhead_paise=sum(o.amount_paise for o in run.overheads),
        lines=[OverheadOut.model_validate(row) for row in rows],
    )
    after = out.model_dump(mode="json")
    audit.record(
        db,
        entity="production_run",
        entity_id=run.id,
        action="OVERHEAD",
        user_id=user.id,
        after=after,
    )
    db.commit()
    return out


def run_variance(db: Session, run_id: int) -> VarianceOut:
    """Planned vs actual per BOM line, plus yield (A1–A4). Actuals come from the ledger."""
    run = _get(db, run_id)
    _require_completed(run)
    assert run.good_qty is not None
    actual = _actuals(db, run)
    lines = []
    for consumption in run.lines:
        item = masters.get_item(db, consumption.item_id)
        v = variance(
            consumption.planned_qty, actual.get(consumption.id, Decimal(0)), item.variance_tol_bp
        )
        lines.append(
            VarianceLineOut(
                item_id=item.id,
                item_code=item.code,
                uom=item.base_uom,
                damaged_qty=consumption.damaged_qty,
                planned_qty=v.planned,
                actual_qty=v.actual,
                variance_bp=v.variance_bp,
                flagged=v.flagged,
            )
        )
    product = masters.get_item(db, run.item_id)
    y = variance(run.planned_qty, run.good_qty, product.variance_tol_bp)
    return VarianceOut(
        run_id=run.id,
        run_no=run.run_no,
        yield_=VarianceRow(
            planned_qty=y.planned, actual_qty=y.actual, variance_bp=y.variance_bp, flagged=y.flagged
        ),
        lines=lines,
    )


def run_cost(db: Session, run_id: int) -> CostOut:
    """(materials issued + overheads) / good output (A7, B13)."""
    run = _get(db, run_id)
    _require_completed(run)
    assert run.good_qty is not None
    material = -inventory.source_value(db, RUN, run.id, MovementType.ISSUE)
    overhead = sum(o.amount_paise for o in run.overheads)
    total = material + overhead
    return CostOut(
        run_id=run.id,
        run_no=run.run_no,
        material_paise=material,
        overhead_paise=overhead,
        total_paise=total,
        good_qty=run.good_qty,
        cost_per_unit_paise=cost_per_unit_paise(total, run.good_qty),
    )
