from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import AppUser
from app.core import gst
from app.core.clock import start_of_day
from app.core.errors import AppError, not_found
from app.core.units import check_qty_scale
from app.core.wac import receipt_value
from app.inventory import service as inventory
from app.inventory.models import MovementType, SourceType
from app.inventory.service import MovementLine
from app.masters import service as masters
from app.masters.models import ItemKind
from app.purchasing.models import Purchase, PurchaseLine
from app.purchasing.schemas import PurchaseCreate, PurchaseLineOut, PurchaseOut


def _out(db: Session, purchase: Purchase) -> PurchaseOut:
    return PurchaseOut(
        id=purchase.id,
        supplier_id=purchase.supplier_id,
        supplier_code=masters.get_supplier(db, purchase.supplier_id).code,
        purchase_date=purchase.purchase_date,
        bill_no=purchase.bill_no,
        supply_type=purchase.supply_type,
        taxable_paise=purchase.taxable_paise,
        cgst_paise=purchase.cgst_paise,
        sgst_paise=purchase.sgst_paise,
        igst_paise=purchase.igst_paise,
        total_paise=purchase.total_paise,
        lines=[
            PurchaseLineOut(
                id=line.id,
                item_id=line.item_id,
                item_code=masters.get_item(db, line.item_id).code,
                qty=line.qty,
                uom=line.uom,
                entered_qty=line.entered_qty,
                entered_uom=line.entered_uom,
                rate_paise=line.rate_paise,
                value_paise=line.value_paise,
                gst_rate_bp=line.gst_rate_bp,
                cgst_paise=line.cgst_paise,
                sgst_paise=line.sgst_paise,
                igst_paise=line.igst_paise,
                lot_id=line.lot_id,
                lot_no=inventory.get_lot(db, line.lot_id).lot_no,
            )
            for line in purchase.lines
        ],
    )


def create_purchase(db: Session, data: PurchaseCreate, user: AppUser) -> PurchaseOut:
    """Record goods received: one lot per line, PURCHASE movements valued at the line's taxable
    value, input GST recorded but not added to stock value (A15). One transaction."""
    supplier = masters.get_supplier(db, data.supplier_id)
    supply = gst.supply_type(masters.get_company(db).state_code, supplier.state_code)
    # Lock the items before inserting lots/lines that reference them, to avoid the lock-upgrade
    # deadlock two concurrent posts would otherwise hit (see production.start_run).
    masters.lock_items(db, (line.item_id for line in data.lines))
    purchase = Purchase(
        supplier_id=supplier.id,
        purchase_date=data.purchase_date,
        bill_no=data.bill_no,
        supply_type=supply.value,
        created_by=user.id,
    )
    db.add(purchase)
    db.flush()

    taxes: list[gst.LineTax] = []
    movements: list[MovementLine] = []
    for n, line_in in enumerate(data.lines, start=1):
        item = masters.get_item(db, line_in.item_id)
        if item.kind not in (ItemKind.RAW, ItemKind.PACKAGING):
            raise AppError(422, "NOT_PURCHASABLE", f"{item.code} is a finished good")
        try:
            entered = check_qty_scale(line_in.qty)
        except ValueError as exc:
            raise AppError(422, "INVALID_QUANTITY", str(exc)) from None
        qty = masters.base_qty(entered, line_in.uom, item)
        # Value in the quoted unit (60 kg x Rs 45), not per gram: 4.5 paise/g isn't a whole paisa.
        value = receipt_value(entered, line_in.rate_paise)
        rate_bp = item.gst_rate_bp if line_in.gst_rate_bp is None else line_in.gst_rate_bp
        tax = gst.line_tax(value, rate_bp, supply)
        lot = inventory.create_lot(
            db,
            item_id=item.id,
            lot_no=f"PUR-{purchase.id:04d}-{n}",
            received_at=start_of_day(data.purchase_date),
            source_type=SourceType.PURCHASE,
            source_id=purchase.id,
            expiry_date=line_in.expiry_date,
        )
        line = PurchaseLine(
            purchase_id=purchase.id,
            item_id=item.id,
            qty=qty,
            uom=item.base_uom,
            entered_qty=entered,
            entered_uom=line_in.uom,
            rate_paise=line_in.rate_paise,
            value_paise=value,
            gst_rate_bp=rate_bp,
            cgst_paise=tax.cgst_paise,
            sgst_paise=tax.sgst_paise,
            igst_paise=tax.igst_paise,
            lot_id=lot.id,
        )
        db.add(line)
        db.flush()
        taxes.append(tax)
        movements.append(
            MovementLine(
                item.id,
                qty,
                MovementType.PURCHASE,
                source_line_id=line.id,
                lot_id=lot.id,
                value_paise=value,
            )
        )

    inventory.post_movements(
        db,
        source_type=SourceType.PURCHASE,
        source_id=purchase.id,
        movement_date=data.purchase_date,
        user_id=user.id,
        lines=movements,
    )
    totals = gst.invoice_totals(taxes)
    purchase.taxable_paise = totals.taxable_paise
    purchase.cgst_paise = totals.cgst_paise
    purchase.sgst_paise = totals.sgst_paise
    purchase.igst_paise = totals.igst_paise
    purchase.total_paise = totals.total_paise
    db.flush()
    db.refresh(purchase)  # load the lines just added
    out = _out(db, purchase)
    after = out.model_dump(mode="json")
    audit.record(
        db, entity="purchase", entity_id=purchase.id, action="POST", user_id=user.id, after=after
    )
    db.commit()
    return out


def get_purchase(db: Session, purchase_id: int) -> PurchaseOut:
    purchase = db.get(Purchase, purchase_id)
    if purchase is None:
        raise not_found("purchase", purchase_id)
    return _out(db, purchase)
