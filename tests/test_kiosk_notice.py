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


def test_kiosk_notice_style_options_are_rendered() -> None:
    with TestClient(app) as c:
        kiosk_notice.set_custom_message(
            "Antreten um 18 Uhr.",
            alignment="right",
            size="large",
            icon="warning",
        )
        r = c.get("/")
        assert r.status_code == 200
        assert "Antreten um 18 Uhr." in r.text
        assert "trust-banner--align-right" in r.text
        assert "trust-banner--size-large" in r.text
        assert "trust-banner--icon-warning" in r.text
        kiosk_notice.set_custom_message("")


def test_admin_news_uses_icon_buttons_instead_of_icon_dropdown() -> None:
    with TestClient(app) as c:
        login = c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303
        r = c.get("/admin/news")
        assert r.status_code == 200
        assert '<select name="icon">' not in r.text
        assert 'type="radio"' in r.text
        assert 'name="icon"' in r.text
        assert "admin-news-icon-preview__choice" in r.text
