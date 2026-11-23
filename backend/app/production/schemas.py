from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, Strict

from app.core.types import PositiveQty
from app.production.models import OverheadKind


class QtyLine(BaseModel):
    item_id: int
    qty: PositiveQty
    uom: str  # any unit of the item's dimension


class RunCreate(BaseModel):
    bom_id: int
    batches: PositiveQty
    run_date: date
    issues: list[QtyLine] = []  # usually the raw materials, issued at the start


class RunComplete(BaseModel):
    output_qty: PositiveQty  # good output
    output_uom: str | None = None  # defaults to the product's base unit
    issues: list[QtyLine] = []  # usually the packaging, counted at the end
    damaged: list[QtyLine] = []  # already included in the issues; recorded for information


class OverheadLineIn(BaseModel):
    kind: OverheadKind
    amount_paise: Annotated[int, Strict(), Field(gt=0)]
    note: str | None = None


class OverheadCreate(BaseModel):
    lines: list[OverheadLineIn] = Field(min_length=1)


class RunLineOut(BaseModel):
    item_id: int
    item_code: str
    uom: str
    planned_qty: Decimal
    actual_qty: Decimal  # from the ledger
    damaged_qty: Decimal


class RunOut(BaseModel):
    id: int
    run_no: str
    bom_id: int
    item_id: int
    item_code: str
    batches: Decimal
    run_date: date
    status: str
    planned_qty: Decimal
    good_qty: Decimal | None
    output_lot_no: str | None
    lines: list[RunLineOut]


class OverheadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    amount_paise: int
    note: str | None


class OverheadsOut(BaseModel):
    run_id: int
    overhead_paise: int  # all overheads of the run so far
    lines: list[OverheadOut]


class VarianceRow(BaseModel):
    planned_qty: Decimal
    actual_qty: Decimal
    variance_bp: int  # -600 = -6.00%
    flagged: bool  # |variance| > the item's tolerance (A2)


class VarianceLineOut(VarianceRow):
    item_id: int
    item_code: str
    uom: str
    damaged_qty: Decimal


class VarianceOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: int
    run_no: str
    yield_: VarianceRow = Field(serialization_alias="yield")  # good output vs expected
    lines: list[VarianceLineOut]


class CostOut(BaseModel):
    run_id: int
    run_no: str
    material_paise: int
    overhead_paise: int
    total_paise: int
    good_qty: Decimal
    cost_per_unit_paise: int  # (materials + overheads) / good output, half-up (A7)
