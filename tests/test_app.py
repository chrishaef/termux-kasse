from fastapi.testclient import TestClient

from app.main import app


def test_kiosk_home() -> None:
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "k-tiles" in r.text or "k-empty" in r.text
        assert "kasse.css" in r.text
