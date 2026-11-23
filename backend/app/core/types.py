"""Field types for API schemas, so every module follows the same wire rules (CLAUDE.md section 3):
money is an integer number of paise, quantities are decimal strings, never JSON floats."""

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, Strict

from app.core.units import parse_qty


def _qty(value: object) -> Decimal:
    if isinstance(value, float | bool):
        raise ValueError('send quantities as decimal strings, e.g. "10.5", not JSON numbers')
    if not isinstance(value, str | int | Decimal):
        raise ValueError("quantity must be a decimal string")
    return parse_qty(value)


Qty = Annotated[Decimal, BeforeValidator(_qty)]
PositiveQty = Annotated[Decimal, BeforeValidator(_qty), Field(gt=0)]
Paise = Annotated[int, Strict(), Field(ge=0)]
BasisPoints = Annotated[int, Strict(), Field(ge=0, le=10_000)]
Code = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,31}$")]
StateCode = Annotated[str, Field(pattern=r"^[0-9]{2}$")]
Gstin = Annotated[str, Field(pattern=r"^[0-9]{2}[0-9A-Z]{13}$")]
