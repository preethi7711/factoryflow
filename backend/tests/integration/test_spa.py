"""The production image serves the built React app; these tests use a fake build in tmp_path."""

from fastapi.testclient import TestClient

from app.core.spa import SPAStaticFiles
from app.main import create_app


def _client(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<h1>FactoryFlow</h1>")
    app = create_app()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="web")
    return TestClient(app)


def test_root_serves_index_html(tmp_path) -> None:
    r = _client(tmp_path).get("/")
    assert r.status_code == 200
    assert "FactoryFlow" in r.text


def test_client_side_route_falls_back_to_index_html(tmp_path) -> None:
    r = _client(tmp_path).get("/orders/12")
    assert r.status_code == 200
    assert "FactoryFlow" in r.text


def test_api_routes_win_over_static_files(tmp_path) -> None:
    c = _client(tmp_path)
    assert c.get("/api/v1/health").json()["status"] == "ok"
    assert c.get("/api/v1/does-not-exist").status_code == 404
