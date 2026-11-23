from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Role(StrEnum):
    SALESMAN = "salesman"
    ADMIN = "admin"
    PRODUCTION = "production"
    AUDITOR = "auditor"
    OWNER = "owner"


ALL_ROLES = tuple(Role)


class AppUser(Base):
    # "user" is a reserved word in Postgres, hence app_user.
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint(f"role IN ({', '.join(repr(r.value) for r in Role)})", name="role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
