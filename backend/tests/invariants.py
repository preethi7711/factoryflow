"""Ledger invariants that must hold after every benchmark step and after every integration test
(decision recorded in docs/project_status.md: reconcile and orphans are invariants, not one-off
checks). Invariant numbers refer to CLAUDE.md section 4."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.inventory import service as stock

MOVEMENTS = text("SELECT COUNT(*) FROM stock_movement")
# A real orphan check (invariant 6): count movements whose (source_type, source_id) names no
# existing document. source_* are already NOT NULL, so the old "IS NULL" query could never fire.
ORPHANS = text(
    "SELECT COUNT(*) FROM stock_movement m"
    " WHERE NOT EXISTS (SELECT 1 FROM purchase p"
    "                    WHERE m.source_type = 'purchase' AND p.id = m.source_id)"
    "   AND NOT EXISTS (SELECT 1 FROM production_run r"
    "                    WHERE m.source_type = 'production_run' AND r.id = m.source_id)"
    "   AND NOT EXISTS (SELECT 1 FROM stock_adjustment a"
    "                    WHERE m.source_type = 'stock_adjustment' AND a.id = m.source_id)"
    "   AND NOT EXISTS (SELECT 1 FROM dispatch d"
    "                    WHERE m.source_type = 'dispatch' AND d.id = m.source_id)"
    "   AND NOT EXISTS (SELECT 1 FROM credit_note c"
    "                    WHERE m.source_type = 'credit_note' AND c.id = m.source_id)"
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
