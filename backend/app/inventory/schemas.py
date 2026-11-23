from decimal import Decimal

from pydantic import BaseModel


class StockBalanceOut(BaseModel):
    item_id: int
    item_code: str
    qty: Decimal  # serialised as a decimal string, in the item's base unit
    uom: str
    value_paise: int


class ReconcileOut(BaseModel):
    ok: bool
    problems: list[str]
