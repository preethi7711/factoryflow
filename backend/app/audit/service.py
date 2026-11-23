from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AuditLog


def record(
    db: Session,
    *,
    entity: str,
    entity_id: int,
    action: str,
    user_id: int | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    """Add one audit row to the caller's transaction, so the change and its audit row
    commit together or not at all. before/after must be JSON-ready (model_dump(mode="json"))."""
    db.add(
        AuditLog(
            entity=entity,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            before=before,
            after=after,
        )
    )
