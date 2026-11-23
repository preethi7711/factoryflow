from functools import cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AppUser
from app.core.security import hash_password, verify_password


@cache
def _dummy_hash() -> str:
    return hash_password("timing-equaliser, not a real password")


def authenticate(db: Session, username: str, password: str) -> AppUser | None:
    """The user if the password matches and the account is active, otherwise None.

    An unknown username still costs one bcrypt check, so the response time doesn't
    reveal which usernames exist.
    """
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    if user is None:
        verify_password(password, _dummy_hash())
        return None
    if not verify_password(password, user.password_hash) or not user.is_active:
        return None
    return user


def get_active_user(db: Session, user_id: int) -> AppUser | None:
    user = db.get(AppUser, user_id)
    return user if user is not None and user.is_active else None
