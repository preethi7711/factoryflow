"""Health check: is the API up, and can it reach the database?"""

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response, db: DbSession) -> dict[str, str]:
    # Public on purpose (no login): the host and uptime checks call it.
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": "error"}
    return {"status": "ok", "db": "ok"}
