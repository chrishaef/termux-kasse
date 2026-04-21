from fastapi.testclient import TestClient

from app import kiosk_notice
from app.main import app


def test_kiosk_home_hides_notice_when_empty() -> None:
    with TestClient(app) as c:
        kiosk_notice.set_custom_message("")
        r = c.get("/")
        assert r.status_code == 200
        assert "trust-banner" not in r.text


def test_kiosk_home_shows_custom_notice() -> None:
    with TestClient(app) as c:
        kiosk_notice.set_custom_message("Heute: Apfelkuchen im Angebot.")
        r = c.get("/")
        assert r.status_code == 200
        assert "Apfelkuchen" in r.text
        assert "Vertrauensbasis" not in r.text
        kiosk_notice.set_custom_message("")
