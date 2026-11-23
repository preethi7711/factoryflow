from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.auth.deps import require_roles
from app.auth.models import AppUser, Role
from app.core.db import DbSession
from app.production import service
from app.production.schemas import (
    CostOut,
    OverheadCreate,
    OverheadsOut,
    RunComplete,
    RunCreate,
    RunOut,
    VarianceOut,
)

router = APIRouter(prefix="/production-runs", tags=["production"])

# Spec section 2: the production supervisor records runs, issues, output, wastage and overheads.
Producer = Annotated[AppUser, Depends(require_roles(Role.PRODUCTION))]
RunReader = Annotated[
    AppUser, Depends(require_roles(Role.PRODUCTION, Role.ADMIN, Role.AUDITOR, Role.OWNER))
]


@router.post("", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def start_run(body: RunCreate, db: DbSession, user: Producer) -> RunOut:
    return service.start_run(db, body, user)


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: DbSession, user: RunReader) -> RunOut:
    return service.get_run(db, run_id)


@router.post("/{run_id}/complete", response_model=RunOut)
def complete_run(run_id: int, body: RunComplete, db: DbSession, user: Producer) -> RunOut:
    return service.complete_run(db, run_id, body, user)


@router.post(
    "/{run_id}/overheads", response_model=OverheadsOut, status_code=status.HTTP_201_CREATED
)
def add_overheads(run_id: int, body: OverheadCreate, db: DbSession, user: Producer) -> OverheadsOut:
    return service.add_overheads(db, run_id, body, user)


@router.get("/{run_id}/variance", response_model=VarianceOut)
def run_variance(run_id: int, db: DbSession, user: RunReader) -> VarianceOut:
    return service.run_variance(db, run_id)


@router.get("/{run_id}/cost", response_model=CostOut)
def run_cost(run_id: int, db: DbSession, user: RunReader) -> CostOut:
    return service.run_cost(db, run_id)
