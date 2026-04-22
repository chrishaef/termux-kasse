from fastapi.testclient import TestClient

from app.main import app
from app.routers import admin as admin_router


def test_admin_login_accepts_default_password() -> None:
    with TestClient(app) as client:
        r = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


def test_admin_login_accepts_master_password() -> None:
    with TestClient(app) as client:
        r = client.post("/admin/login", data={"password": "master"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


def test_admin_password_change_requires_old_password() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)

        bad = client.post(
            "/admin/password",
            data={
                "old_password": "wrong",
                "new_password": "neu1234",
                "new_password2": "neu1234",
            },
        )
        assert bad.status_code == 400
        assert "Altes Passwort falsch" in bad.text

        ok = client.post(
            "/admin/password",
            data={
                "old_password": "admin",
                "new_password": "neu1234",
                "new_password2": "neu1234",
            },
            follow_redirects=False,
        )
        assert ok.status_code == 303
        assert ok.headers["location"] == "/admin/password?saved=1"

        relog_old = client.post("/admin/login", data={"password": "admin"})
        assert relog_old.status_code == 401
        relog_new = client.post("/admin/login", data={"password": "neu1234"}, follow_redirects=False)
        assert relog_new.status_code == 303


def test_admin_session_is_closed_when_leaving_admin_panel() -> None:
    with TestClient(app) as client:
        login = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303

        leave = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
        assert leave.status_code == 200

        admin_again = client.get("/admin", follow_redirects=False)
        assert admin_again.status_code == 303
        assert admin_again.headers["location"] == "/admin/login"


def test_admin_session_not_cleared_on_non_kiosk_paths_even_with_html_accept() -> None:
    """Avoids logging out on odd clients (e.g. WebView) that send text/html for subresources."""
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        weird = client.get(
            "/static/pico.min.css",
            headers={"accept": "text/html;q=0.8,text/css,*/*;q=0.1"},
            follow_redirects=False,
        )
        assert weird.status_code == 200
        admin_again = client.get("/admin", follow_redirects=False)
        assert admin_again.status_code == 200


def test_admin_dashboard_shows_telemetry_data() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin")
        assert r.status_code == 200
        assert "Version:" in r.text
        assert "Start:" in r.text
        assert "Backup:" in r.text
        assert "Buchungen heute" in r.text
        assert "Umsatz heute" in r.text
        assert "Speicher:" in r.text
        assert "GB frei /" in r.text
        assert ("latest" in r.text) or ("outdated" in r.text) or ("unknown" in r.text)


def test_admin_dashboard_shows_system_update_button() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin")
        assert r.status_code == 200
        assert 'href="/admin/system-update"' in r.text
        assert 'id="admin-update-link"' in r.text
        assert "admin-version-state--action" in r.text
        assert ">update / reboot</a>" in r.text


def test_admin_system_update_page_is_available() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/system-update")
        assert r.status_code == 200
        assert "System-Update Vorbereitung" in r.text
        assert "Netzwerk:" in r.text
        assert "Installiert:" in r.text
        assert "Neueste verfügbare Version:" in r.text
        assert 'name="master_password"' in r.text
        assert "Bisherige Update-Logzeilen" in r.text
        assert ("admin-update-log-box" in r.text) or ("Noch keine Update-Logs vorhanden." in r.text)


def test_admin_system_update_result_page_is_available() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/system-update/result")
        assert r.status_code == 200
        assert "System-Update Protokoll" in r.text
        assert "Aktuelle Update-Logzeilen nach dem Neustart" in r.text
        assert ("admin-update-log-box" in r.text) or ("Noch keine Update-Logs vorhanden." in r.text)
        assert "Zurück zum System" in r.text


def test_admin_system_update_post_triggers_background_runner(monkeypatch) -> None:
    calls: list[str] = []

    def fake_trigger() -> None:
        calls.append("called")

    monkeypatch.setattr(admin_router, "_trigger_background_update", fake_trigger)
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda raw: raw == "master")
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post("/admin/system-update", data={"master_password": "master"}, follow_redirects=False)
        assert r.status_code == 200
        assert "Update und Neustart laufen" in r.text
        assert "/admin/system-update/result" in r.text
    assert calls == ["called"]


def test_admin_system_update_page_shows_restart_button_without_update(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_router,
        "_system_update_precheck",
        lambda: {
            "online": True,
            "online_label": "Ja",
            "online_badge": "online",
            "installed_version_commit": "1.1.0 (abc1234)",
            "latest_version_commit": "1.1.0 (abc1234)",
            "update_available": False,
        },
    )
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/system-update")
        assert r.status_code == 200
        assert "Neustart starten" in r.text


def test_admin_system_update_page_shows_offline_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        admin_router,
        "_system_update_precheck",
        lambda: {
            "online": False,
            "online_label": "Nein",
            "online_badge": "offline",
            "installed_version_commit": "1.1.0 (abc1234)",
            "latest_version_commit": "unbekannt (unbekannt)",
            "update_available": False,
        },
    )
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/system-update")
        assert r.status_code == 200
        assert "Es besteht keine Internetverbindung." in r.text
        assert "Versionscheck konnte nicht durchgeführt werden" in r.text
        assert "Neustart starten" in r.text


def test_admin_system_update_post_rejects_wrong_master_password(monkeypatch) -> None:
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda _raw: False)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post("/admin/system-update", data={"master_password": "wrong"}, follow_redirects=False)
        assert r.status_code == 400
        assert "Master-Passwort ist falsch." in r.text
