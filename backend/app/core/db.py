"""Database engine, session factory and the declarative base for all models.

Sync SQLAlchemy on purpose: FastAPI runs sync endpoints in a thread pool, which is
plenty for ~20 users, and sync code is easier to read and debug than async.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import MetaData, Numeric, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Fixed constraint names, so Alembic migrations name things the same way on every machine.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Every quantity column: exact decimal, 3 places, in the item's base unit (g, ml, pcs, pkt).
QTY = Numeric(18, 3)


class Base(DeclarativeBase):
    """Every model inherits this, so Alembic can see all tables via Base.metadata."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# pool_pre_ping: test a pooled connection before use (free Postgres hosts drop idle ones).
engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
