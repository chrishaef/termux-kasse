from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient

from app import branding
from app import db
from app import system_settings
from app.main import app

_MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lQGTWQAAAABJRU5ErkJggg=="
)


def test_kiosk_home_defaults_to_group_selection() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "NurEine"})
        home = client.get("/", follow_redirects=False)
        assert home.status_code == 200
        assert "k-tiles" in home.text or "NurEine" in home.text
        assert "/static/wsg-logo.png" in home.text
        assert "Shopkasse" in home.text
        assert "OF Hünger" in home.text


def test_kiosk_home_skip_shows_all_users_with_letter_filter() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "A"})
        client.post("/admin/groups", data={"name": "B"})
        with db.get_connection() as conn:
            gid_a = int(conn.execute("SELECT id FROM user_groups WHERE name='A'").fetchone()[0])
            gid_b = int(conn.execute("SELECT id FROM user_groups WHERE name='B'").fetchone()[0])
        client.post("/admin/users", data={"name": "Anna", "group_id": str(gid_a)})
        client.post("/admin/users", data={"name": "Bernd", "group_id": str(gid_b)})
        with db.get_connection() as conn:
            system_settings.save_timeout_settings(
                conn,
                admin_logout_seconds=25,
                kiosk_preisliste_seconds=60,
                kiosk_home_seconds=30,
                kiosk_skip_group_selection=True,
            )
            uid = int(conn.execute("SELECT id FROM users WHERE name='Anna'").fetchone()[0])

        home = client.get("/", follow_redirects=False)
        assert home.status_code == 200
        assert "Anna" in home.text
        assert "Bernd" in home.text
        assert 'data-letter-filter' in home.text
        assert 'data-letter="A"' in home.text
        assert 'data-letter="B"' in home.text
        assert "← Zurück" not in home.text
        assert "data-letter-filter" in home.text
        assert "Anna" in home.text and "Bernd" in home.text
        # Flat home has no group back link in the member header.
        assert 'class="admin-back"' not in home.text

        user_page = client.get(f"/u/{uid}")
        assert user_page.status_code == 200
        assert 'href="/"' in user_page.text
        assert "← Zurück" in user_page.text


def test_kiosk_group_page_keeps_back_button_when_skip_disabled() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "Team"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups WHERE name='Team'").fetchone()[0])
        client.post("/admin/users", data={"name": "Chris", "group_id": str(gid)})
        page = client.get(f"/g/{gid}")
        assert page.status_code == 200
        assert "← Zurück" in page.text
        assert "Team" in page.text
        assert "Chris" in page.text


def test_admin_branding_display_name_and_logo_upload() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        save = client.post(
            "/admin/system-settings",
            data={
                "admin_logout_seconds": "25",
                "kiosk_preisliste_seconds": "60",
                "kiosk_home_seconds": "30",
                "kiosk_preisliste_enabled": "1",
                "kiosk_group_logo_zoom_enabled": "1",
                "kiosk_group_logo_animation_speed": "normal",
                "shop_display_name": "Zweiter Shop",
                "shop_powered_by": "Team Nord",
                "kiosk_skip_group_selection": "1",
            },
            files={"logo_png": ("logo.png", io.BytesIO(_MINI_PNG), "image/png")},
            follow_redirects=False,
        )
        assert save.status_code == 303
        assert save.headers["location"] == "/admin/system-settings?saved=1"

        with db.get_connection() as conn:
            info = branding.get_branding(conn)
            settings = system_settings.get_timeout_settings(conn)
        assert info["display_name"] == "Zweiter Shop"
        assert info["powered_by"] == "Team Nord"
        assert info["has_custom_logo"] is True
        assert str(info["logo_url"]).startswith("/branding/logo")
        assert settings["kiosk_skip_group_selection"] is True

        home = client.get("/")
        assert home.status_code == 200
        assert "Zweiter Shop" in home.text
        assert "Team Nord" in home.text
        assert "OF Hünger" not in home.text
        assert "/branding/logo" in home.text

        logo = client.get("/branding/logo")
        assert logo.status_code == 200
        assert logo.headers["content-type"].startswith("image/png")
