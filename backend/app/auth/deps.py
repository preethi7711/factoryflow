"""FastAPI dependencies: who is calling, and may they call this route.

Deny by default: every route except /health and /auth/login must depend on
require_roles(...). tests/integration/test_auth.py walks all routes and fails if one forgets.
"""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import AppUser, Role
from app.auth.service import get_active_user
from app.core.db import DbSession
from app.core.errors import AppError
from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)  # we raise our own 401 in the standard error shape
_CHALLENGE = {"WWW-Authenticate": "Bearer"}


def _unauthenticated(message: str) -> AppError:
    return AppError(401, "UNAUTHENTICATED", message, headers=_CHALLENGE)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> AppUser:
    if credentials is None:
        raise _unauthenticated("Log in first")
    try:
        user_id = int(decode_access_token(credentials.credentials)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthenticated("Invalid or expired token") from None
    # Role and active flag come from the database, not the token, so a change takes effect at once.
    user = get_active_user(db, user_id)
    if user is None:
        raise _unauthenticated("Account not found or disabled")
    return user


def require_roles(*roles: Role) -> Callable[..., AppUser]:
    """Dependency that lets only the listed roles through (403 for everyone else)."""
    allowed = frozenset(roles)

    def dependency(user: Annotated[AppUser, Depends(get_current_user)]) -> AppUser:
        if user.role not in allowed:
            raise AppError(403, "FORBIDDEN", f"role '{user.role}' may not do this")
        return user

    dependency.allowed_roles = allowed  # type: ignore[attr-defined]  # read by the route audit test
    return dependency
