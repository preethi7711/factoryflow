"""Shared test setup.

Tests always run against TEST_DATABASE_URL, never the development database.
The swap happens here, before any `app` module is imported, because the engine
is built from settings at import time.
"""

import os

_test_url = os.environ.get("TEST_DATABASE_URL")
if not _test_url:
    raise RuntimeError("TEST_DATABASE_URL is not set. Tests refuse to run on the dev database.")
if _test_url == os.environ.get("DATABASE_URL"):
    raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL.")
os.environ["DATABASE_URL"] = _test_url
os.environ["APP_ENV"] = "test"
os.environ["BCRYPT_ROUNDS"] = "4"  # the minimum; real logins use 12

from collections.abc import Callable, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import seed  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def reset_database() -> None:
    """Drop everything, then rebuild the schema with the real migrations (not create_all),
    so tests also cover the triggers and constraints that only the migrations create."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _migrated_db() -> None:
    reset_database()


@pytest.fixture(scope="module")
def seeded_db() -> None:
    """Fresh schema + the benchmark seed, shared by the tests of one module."""
    reset_database()
    seed.run()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def as_user(client: TestClient) -> Callable[[str], dict[str, str]]:
    """as_user("admin") -> Authorization header for that seeded login."""

    def headers(username: str) -> dict[str, str]:
        r = client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": get_settings().seed_demo_password},
        )
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return headers


@pytest.fixture
def db() -> Iterator[Session]:
    """A session for calling services directly. Always rolled back: nothing it writes survives."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
