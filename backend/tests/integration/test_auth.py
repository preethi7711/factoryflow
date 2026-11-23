"""Login, tokens and role checks (spec section 2). Deny by default."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.main import app

pytestmark = pytest.mark.usefixtures("seeded_db")

PUBLIC_ROUTES = {"/api/v1/health", "/api/v1/auth/login"}


def _guarded(dependant) -> bool:
    return any(hasattr(d.call, "allowed_roles") or _guarded(d) for d in dependant.dependencies)


def test_every_route_declares_its_roles() -> None:
    """Deny by default, proven: a new route without require_roles(...) fails this test."""
    unguarded = [
        f"{sorted(route.methods)} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and not _guarded(route.dependant)
    ]
    assert unguarded == []


def test_login_returns_a_token_and_the_role(client) -> None:
    password = get_settings().seed_demo_password
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": password})
    assert r.status_code == 200
    body = r.json()
    assert (body["role"], body["token_type"]) == ("admin", "bearer")
    assert body["access_token"]


def test_wrong_password_and_unknown_user_get_the_same_answer(client) -> None:
    wrong = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope"})
    unknown = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # no hint about which usernames exist
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_needs_a_valid_token(client, as_user) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
    junk = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer junk"})
    assert junk.status_code == 401
    assert junk.json()["error"]["code"] == "UNAUTHENTICATED"
    assert client.get("/api/v1/auth/me", headers=as_user("accountant")).json()["role"] == "auditor"


def test_expired_and_forged_tokens_are_rejected(client) -> None:
    key = get_settings().jwt_secret_key
    now = datetime.now(UTC)
    expired = jwt.encode({"sub": "1", "exp": now - timedelta(minutes=1)}, key, algorithm="HS256")
    forged = jwt.encode(
        {"sub": "1", "exp": now + timedelta(hours=1)}, "wrong-key", algorithm="HS256"
    )
    for token in (expired, forged):
        r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


@pytest.mark.parametrize(
    ("username", "method", "path", "status"),
    [
        ("salesman_a", "GET", "/api/v1/price-list", 200),
        ("salesman_a", "GET", "/api/v1/customers", 200),
        ("salesman_a", "GET", "/api/v1/items", 403),  # raw materials and costs aren't theirs
        ("salesman_a", "GET", "/api/v1/stock/reconcile", 403),
        ("production", "GET", "/api/v1/boms", 200),
        ("production", "GET", "/api/v1/customers", 403),  # production never sees sales data
        ("accountant", "GET", "/api/v1/items", 200),
        ("accountant", "POST", "/api/v1/customers", 403),  # the auditor is read-only
        ("owner", "POST", "/api/v1/items", 403),
        ("admin", "GET", "/api/v1/stock/reconcile", 200),
    ],
)
def test_role_matrix(client, as_user, username, method, path, status) -> None:
    r = client.request(method, path, headers=as_user(username), json={})
    assert r.status_code == status, r.text
