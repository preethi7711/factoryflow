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
