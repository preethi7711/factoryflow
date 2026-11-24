"""A uniform report envelope, so every report renders the same way as JSON, CSV or XLSX.

A report is a titled table: ordered columns (key + human label) and rows keyed by column key,
plus optional totals. Money stays integer paise and quantities are decimal strings on the wire,
the same as everywhere else.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Column(BaseModel):
    key: str
    label: str


class Report(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    from_: date = Field(serialization_alias="from")
    to: date
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None = None
