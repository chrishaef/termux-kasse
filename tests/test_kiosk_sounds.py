from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import kiosk_sounds
from app.main import app

_STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
_SAMPLE_MP3 = (_STATIC / "click.mp3").read_bytes()


def test_kiosk_user_uses_default_static_sound_urls() -> None:
    from app import db

    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "U1", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])

        page = client.get(f"/u/{uid}")
        assert page.status_code == 200
        assert 'src="/static/click.mp3"' in page.text
        assert 'src="/static/warn1.mp3"' in page.text
        assert 'src="/static/warn2.mp3"' in page.text
        assert 'src="/static/warn3.mp3"' in page.text


def test_admin_can_upload_and_reset_kiosk_sounds() -> None:
    from app import db

    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "U1", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])

        settings = client.get("/admin/debt-thresholds")
        assert settings.status_code == 200
        assert "Audio</button>" in settings.text
        assert 'name="click_sound"' in settings.text
        assert 'name="warn_sound_1"' in settings.text

        save = client.post(
            "/admin/debt-thresholds",
            data={
                "threshold_a_eur": "5",
                "threshold_b_eur": "15",
                "threshold_c_eur": "30",
                "age_threshold_a_days": "7",
                "age_threshold_b_days": "21",
                "age_threshold_c_days": "45",
                "volume_1_percent": "75",
                "volume_2_percent": "85",
                "volume_3_percent": "95",
            },
            files={
                "warn_sound_1": ("warn1.mp3", _SAMPLE_MP3, "audio/mpeg"),
                "click_sound": ("click.mp3", _SAMPLE_MP3, "audio/mpeg"),
            },
            follow_redirects=False,
        )
        assert save.status_code == 303
        assert save.headers["location"] == "/admin/debt-thresholds?saved=1"
        assert kiosk_sounds.has_custom_sound("warn1") is True
        assert kiosk_sounds.has_custom_sound("click") is True
        assert str(kiosk_sounds.sound_url("warn1")).startswith("/kiosk-sound/warn1")
        assert str(kiosk_sounds.sound_url("click")).startswith("/kiosk-sound/click")

        served = client.get("/kiosk-sound/warn1")
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("audio/mpeg")

        page = client.get(f"/u/{uid}")
        assert page.status_code == 200
        assert "/kiosk-sound/warn1" in page.text
        assert "/kiosk-sound/click" in page.text
        assert 'src="/static/warn2.mp3"' in page.text

        reset = client.post(
            "/admin/debt-thresholds",
            data={
                "threshold_a_eur": "5",
                "threshold_b_eur": "15",
                "threshold_c_eur": "30",
                "age_threshold_a_days": "7",
                "age_threshold_b_days": "21",
                "age_threshold_c_days": "45",
                "volume_1_percent": "75",
                "volume_2_percent": "85",
                "volume_3_percent": "95",
                "remove_warn1": "1",
                "remove_click": "1",
            },
            follow_redirects=False,
        )
        assert reset.status_code == 303
        assert kiosk_sounds.has_custom_sound("warn1") is False
        assert kiosk_sounds.has_custom_sound("click") is False
        assert kiosk_sounds.sound_url("warn1") == "/static/warn1.mp3"
        assert kiosk_sounds.sound_url("click") == "/static/click.mp3"


def test_invalid_kiosk_sound_upload_is_rejected() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        bad = client.post(
            "/admin/debt-thresholds",
            data={
                "threshold_a_eur": "5",
                "threshold_b_eur": "15",
                "threshold_c_eur": "30",
                "age_threshold_a_days": "7",
                "age_threshold_b_days": "21",
                "age_threshold_c_days": "45",
                "volume_1_percent": "75",
                "volume_2_percent": "85",
                "volume_3_percent": "95",
            },
            files={"click_sound": ("bad.mp3", b"not-an-mp3", "audio/mpeg")},
            follow_redirects=False,
        )
        assert bad.status_code == 303
        assert bad.headers["location"] == "/admin/debt-thresholds?err=sound_invalid"
        assert kiosk_sounds.has_custom_sound("click") is False
