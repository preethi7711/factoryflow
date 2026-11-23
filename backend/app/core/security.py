"""Passwords (bcrypt) and login tokens (JWT signed with HS256)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"
_BCRYPT_MAX_BYTES = (
    72  # bcrypt only looks at the first 72 bytes; refuse longer instead of truncating
)


def hash_password(password: str) -> str:
    raw = password.encode()
    if len(raw) > _BCRYPT_MAX_BYTES:
        raise ValueError("password is longer than 72 bytes")
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(raw, salt).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    if len(raw) > _BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(raw, password_hash.encode())


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,  # informational; the server re-reads the role from the database
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError if the token is forged, malformed or expired."""
    return jwt.decode(token, get_settings().jwt_secret_key, algorithms=[ALGORITHM])
