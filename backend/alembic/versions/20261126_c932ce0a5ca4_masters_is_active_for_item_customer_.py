"""masters: is_active on item, customer, supplier (P11).

Soft-deactivation for masters. Existing rows become active (the default), so no behaviour change
until an admin edits one. Price list and the list endpoints default to active-only; historical
orders, invoices and lots never change (the ledger and the audit log don't look at is_active).

Revision ID: c932ce0a5ca4
Revises: 7594a71dfb10
Create Date: 2026-11-26 20:19:33.605695
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c932ce0a5ca4"
down_revision: str | None = "7594a71dfb10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MASTERS = ("item", "customer", "supplier")


def upgrade() -> None:
    for table in MASTERS:
        op.add_column(
            table,
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )


def downgrade() -> None:
    for table in MASTERS:
        op.drop_column(table, "is_active")
