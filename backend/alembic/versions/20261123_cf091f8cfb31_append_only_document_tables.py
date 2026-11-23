"""Make posted documents immutable (invariant 7, P4 audit findings).

The ledger and audit log were already append-only (P3). This extends the guarantee to the
documents behind the movements, so a posted purchase or run can't be silently deleted or edited
into disagreeing with the ledger:

- Fully append-only (no UPDATE, DELETE or TRUNCATE): purchase, purchase_line, stock_lot,
  stock_adjustment, stock_adjustment_line, run_overhead. None of these ever change after insert.
- production_run: no DELETE/TRUNCATE ever, and no UPDATE once it is COMPLETED. The one legal
  update is the DRAFT -> COMPLETED transition (the row is still DRAFT at that point).
- run_consumption: no DELETE/TRUNCATE (its damaged_qty is set during completion, so UPDATE stays).

Revision ID: cf091f8cfb31
Revises: 2a1d9a80be92 (P4)
Create Date: 2026-11-23 18:48:39.045710
"""

from collections.abc import Sequence

from alembic import op

revision: str = "cf091f8cfb31"
down_revision: str | None = "2a1d9a80be92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# forbid_update_delete() already exists (P3). Fully append-only tables reuse it: they are never
# updated after insert.
APPEND_ONLY = [
    "purchase_line",
    "stock_lot",
    "stock_adjustment",
    "stock_adjustment_line",
    "run_overhead",
]
# These keep UPDATE but must never be deleted: `purchase` is updated once to write its totals,
# `run_consumption` once to record damage (both while the document is being posted).
NO_DELETE = ["purchase", "run_consumption"]

# No '%' in this SQL: the driver would read it as a parameter placeholder.
FORBID_DELETE_FN = """
CREATE FUNCTION forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION USING
        MESSAGE = TG_TABLE_NAME || ' is append-only: ' || TG_OP
                  || ' is not allowed, post a correcting entry instead',
        ERRCODE = 'restrict_violation';
END;
$$
"""

# A completed run is a posted document: only the DRAFT -> COMPLETED write is allowed.
FORBID_COMPLETED_RUN_FN = """
CREATE FUNCTION forbid_completed_run_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.status = 'COMPLETED' THEN
        RAISE EXCEPTION USING
            MESSAGE = 'production_run ' || OLD.id
                      || ' is completed and cannot be changed; reverse it instead',
            ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION USING
        MESSAGE = 'production_run is append-only: ' || TG_OP || ' is not allowed',
        ERRCODE = 'restrict_violation';
END;
$$
"""


def _append_only(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION forbid_update_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_update_delete()"
    )


def _no_delete(table: str) -> None:
    op.execute(
        f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION forbid_delete()"
    )
    op.execute(
        f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_delete()"
    )


def upgrade() -> None:
    op.execute(FORBID_DELETE_FN)
    op.execute(FORBID_COMPLETED_RUN_FN)
    for table in APPEND_ONLY:
        _append_only(table)
    for table in NO_DELETE:
        _no_delete(table)
    # production_run: block DELETE/TRUNCATE and UPDATE-after-COMPLETED, allow the DRAFT update.
    op.execute(
        "CREATE TRIGGER production_run_immutable BEFORE UPDATE OR DELETE ON production_run "
        "FOR EACH ROW EXECUTE FUNCTION forbid_completed_run_change()"
    )
    op.execute(
        "CREATE TRIGGER production_run_no_truncate BEFORE TRUNCATE ON production_run "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_delete()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER production_run_no_truncate ON production_run")
    op.execute("DROP TRIGGER production_run_immutable ON production_run")
    for table in NO_DELETE:
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_no_delete ON {table}")
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER {table}_no_truncate ON {table}")
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION forbid_completed_run_change()")
    op.execute("DROP FUNCTION forbid_delete()")
