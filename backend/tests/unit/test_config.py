import pytest

from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    s = Settings(database_url="postgresql+psycopg://x", cors_origins=" http://a , http://b,")
    assert s.cors_origin_list == ["http://a", "http://b"]


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@host/db?sslmode=require",
        "postgresql://u:p@host/db?sslmode=require",
        "postgresql+psycopg://u:p@host/db?sslmode=require",
    ],
)
def test_host_database_urls_use_psycopg3(given: str) -> None:
    s = Settings(database_url=given)
    assert s.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_production_refuses_a_weak_jwt_secret() -> None:
    url = "postgresql+psycopg://user:hunter2@host/db"
    for weak in ("dev-only-not-secret", "short"):
        settings = Settings(database_url=url, app_env="production", jwt_secret_key=weak)
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY") as exc:
            settings.check_production_secrets()
        assert "hunter2" not in str(exc.value) and weak not in str(exc.value)  # nothing leaks
    Settings(
        database_url=url, app_env="production", jwt_secret_key="k" * 32
    ).check_production_secrets()
    Settings(database_url=url, app_env="development").check_production_secrets()  # dev default ok
