"""Ledger invariants that must hold after every benchmark step and after every integration test
(decision recorded in docs/project_status.md: reconcile and orphans are invariants, not one-off
checks). Invariant numbers refer to CLAUDE.md section 4."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory import service as stock

MOVEMENTS = text("SELECT COUNT(*) FROM stock_movement")
ORPHANS = text(
    "SELECT COUNT(*) FROM stock_movement"
    " WHERE source_type IS NULL OR source_id IS NULL OR source_line_id IS NULL"
)
LEDGER_SUM = text("SELECT COALESCE(SUM(qty), 0) FROM stock_movement WHERE item_id = :item_id")


def ledger_problems(session: Session) -> list[str]:
    """[] when the committed ledger is healthy: reconcile() is clean (no negative stock, no value
    stranded on zero stock) and every movement names its source document (invariant 6)."""
    problems = stock.reconcile(session)
    orphans = session.execute(ORPHANS).scalar_one()
    if orphans:
        problems.append(f"{orphans} movement(s) without a source document")
    return problems
