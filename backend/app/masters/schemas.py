from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.types import BasisPoints, Code, Gstin, Paise, PositiveQty, StateCode
from app.core.units import GLOBAL_UNITS
from app.masters.models import ItemKind

BaseUom = Literal["g", "ml", "pcs", "pkt"]


# ---- items ---------------------------------------------------------------------------


class ItemUnitIn(BaseModel):
    uom: str = Field(pattern=r"^[a-z]{2,16}$")
    factor: PositiveQty  # base units in one pack

    @field_validator("uom")
    @classmethod
    def not_a_standard_unit(cls, uom: str) -> str:
        if uom in GLOBAL_UNITS:
            raise ValueError(f"'{uom}' is a standard unit; name the pack instead (e.g. carton)")
        return uom


class ItemCreate(BaseModel):
    code: Code
    name: str = Field(min_length=1, max_length=120)
    kind: ItemKind
    base_uom: BaseUom
    hsn: str | None = Field(default=None, pattern=r"^[0-9]{4,8}$")
    gst_rate_bp: BasisPoints = 0
    sale_price_paise: Paise | None = None
    pack_size: str | None = Field(default=None, max_length=40)
    variance_tol_bp: BasisPoints = 300
    shelf_life_days: int | None = Field(default=None, gt=0)
    units: list[ItemUnitIn] = []

    @model_validator(mode="after")
    def finished_goods_need_a_price(self) -> "ItemCreate":
        if self.kind is ItemKind.FG and self.sale_price_paise is None:
            raise ValueError("a finished good needs sale_price_paise (it is the price list)")
        return self


class ItemUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uom: str
    factor: Decimal


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    kind: str
    base_uom: str
    hsn: str | None
    gst_rate_bp: int
    sale_price_paise: int | None
    pack_size: str | None
    variance_tol_bp: int
    shelf_life_days: int | None
    units: list[ItemUnitOut]


class PriceListRow(BaseModel):
    item_id: int
    code: str
    name: str
    pack_size: str | None
    hsn: str | None
    gst_rate_bp: int
    sale_price_paise: int
    uom: str


# ---- customers and suppliers ---------------------------------------------------------


class PartyCreate(BaseModel):
    code: Code
    name: str = Field(min_length=1, max_length=120)
    gstin: Gstin | None = None
    state_code: StateCode


class CustomerCreate(PartyCreate):
    address: str | None = None
    salesman_id: int | None = None


class SupplierCreate(PartyCreate):
    pass


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    gstin: str | None
    state_code: str
    address: str | None
    salesman_id: int | None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    gstin: str | None
    state_code: str


class CustomerCreated(CustomerOut):
    warnings: list[str] = []  # soft GSTIN checks: saved anyway, shown to the admin


class SupplierCreated(SupplierOut):
    warnings: list[str] = []


# ---- BOMs ----------------------------------------------------------------------------


class BomLineIn(BaseModel):
    item_id: int
    qty: PositiveQty
    uom: str  # any unit of the ingredient's dimension; stored converted to its base unit


class BomCreate(BaseModel):
    code: Code
    item_id: int
    output_qty: PositiveQty  # expected good output of one batch
    output_uom: str = "pkt"
    lines: list[BomLineIn] = Field(min_length=1)


class BomLineOut(BaseModel):
    item_id: int
    item_code: str
    qty: Decimal
    uom: str


class BomOut(BaseModel):
    id: int
    code: str
    item_id: int
    item_code: str
    output_qty: Decimal
    output_uom: str
    is_active: bool
    lines: list[BomLineOut]
