from app.core.config import Settings


def test_cors_origins_are_split_and_trimmed() -> None:
    s = Settings(database_url="postgresql+psycopg://x", cors_origins=" http://a , http://b,")
    assert s.cors_origin_list == ["http://a", "http://b"]
