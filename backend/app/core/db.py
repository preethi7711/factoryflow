"""Database engine, session factory and the declarative base for all models.

Sync SQLAlchemy on purpose: FastAPI runs sync endpoints in a thread pool, which is
plenty for ~20 users, and sync code is easier to read and debug than async.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Every model inherits this, so Alembic can see all tables via Base.metadata."""


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
