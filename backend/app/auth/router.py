from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.deps import require_roles
from app.auth.models import ALL_ROLES, AppUser
from app.auth.schemas import LoginIn, LoginOut, UserOut
from app.auth.service import authenticate
from app.core.db import DbSession
from app.core.errors import AppError
from app.core.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: DbSession) -> LoginOut:
    # Public by design: you can't be logged in before you log in.
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise AppError(401, "INVALID_CREDENTIALS", "Wrong username or password")
    token = create_access_token(user.id, user.role)
    return LoginOut(access_token=token, username=user.username, role=user.role)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[AppUser, Depends(require_roles(*ALL_ROLES))]) -> AppUser:
    return user
