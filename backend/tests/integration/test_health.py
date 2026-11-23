def test_health_reports_api_and_db_ok(client) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_unknown_route_is_404(client) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
