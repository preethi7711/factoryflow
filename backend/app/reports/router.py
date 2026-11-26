from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.core.errors import not_found
from app.reports import service
from app.reports.export import CSV_MEDIA, XLSX_MEDIA, to_csv, to_xlsx

router = APIRouter(prefix="/reports", tags=["reports"])

# Spec section 2: the auditor exports all reports; admin and owner read them too.
ReportReader = Annotated[AppUser, Depends(require_roles(Role.AUDITOR, Role.ADMIN, Role.OWNER))]

Fmt = Literal["json", "csv", "xlsx"]
EXT = {"csv": "csv", "xlsx": "xlsx"}


@router.get("/dashboard")
def get_dashboard(
    db: DbSession,
    user: ReportReader,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
) -> JSONResponse:
    # The owner's at-a-glance numbers. All figures are computed from the same tables the detailed
    # reports read, so nothing here can drift from the ledger or the sales/payments records.
    return JSONResponse(service.dashboard(db, from_, to))


@router.get("/{name}")
def get_report(
    name: str,
    db: DbSession,
    user: ReportReader,
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
    format: Fmt = "json",
) -> Response:
    builder = service.BUILDERS.get(name)
    if builder is None:
        raise not_found("report", name)
    report = builder(db, from_, to)
    if format == "json":
        return JSONResponse(report.model_dump(by_alias=True, mode="json"))
    body, media = (to_csv(report), CSV_MEDIA) if format == "csv" else (to_xlsx(report), XLSX_MEDIA)
    filename = f"{name}_{from_.isoformat()}_{to.isoformat()}.{EXT[format]}"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
