from fastapi.testclient import TestClient
import json
import zipfile

from app.main import app
from app.routers import admin as admin_router


def test_admin_login_accepts_default_password() -> None:
    with TestClient(app) as client:
        r = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


def test_admin_login_accepts_master_password(monkeypatch, tmp_path) -> None:
    master_file = tmp_path / "master_pwd"
    master_file.write_text("master", encoding="utf-8")
    monkeypatch.setenv("KASSE_MASTER_PASSWORD_FILE", str(master_file))
    with TestClient(app) as client:
        r = client.post("/admin/login", data={"password": "master"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/admin"


def test_admin_password_change_requires_master_password(monkeypatch) -> None:
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda raw: raw == "master")
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)

        bad = client.post(
            "/admin/password",
            data={
                "master_password": "wrong",
                "new_password": "neu1234",
                "new_password2": "neu1234",
            },
        )
        assert bad.status_code == 400
        assert "Master-Passwort falsch" in bad.text

        ok = client.post(
            "/admin/password",
            data={
                "master_password": "master",
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
        assert (
            ("latest" in r.text)
            or ("outdated" in r.text)
            or ("new-commit" in r.text)
            or ("unknown" in r.text)
        )


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
        assert "Verfügbar:" in r.text
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

    def fake_trigger(update_channel: str = "release") -> None:
        calls.append(update_channel)

    monkeypatch.setattr(admin_router, "_trigger_background_update", fake_trigger)
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda raw: raw == "master")
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post("/admin/system-update", data={"master_password": "master"}, follow_redirects=False)
        assert r.status_code == 200
        assert "Update und Neustart laufen" in r.text
        assert "/admin/system-update/result" in r.text
    assert calls == ["release"]


def test_background_update_creates_backup_and_rollback_state(monkeypatch, tmp_path) -> None:
    commit = "a" * 40
    root = admin_router._root_dir()
    log_path = root / "update-trigger.log"
    pid_path = root / "update-trigger.pid"
    old_log = log_path.read_bytes() if log_path.exists() else None
    old_pid = pid_path.read_bytes() if pid_path.exists() else None

    class FakeProcess:
        pid = 12345

    monkeypatch.setattr(admin_router, "_is_update_running", lambda: False)
    monkeypatch.setattr(admin_router, "_git_head_full", lambda _root: commit)
    monkeypatch.setattr(admin_router.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    try:
        with TestClient(app):
            admin_router._trigger_background_update("commit")
    finally:
        if old_log is None:
            log_path.unlink(missing_ok=True)
        else:
            log_path.write_bytes(old_log)
        if old_pid is None:
            pid_path.unlink(missing_ok=True)
        else:
            pid_path.write_bytes(old_pid)

    state = json.loads(admin_router._rollback_state_path().read_text(encoding="utf-8"))
    assert state["previous_commit"] == commit
    assert state["previous_commit_short"] == commit[:7]
    assert state["update_channel"] == "commit"
    assert state["backup_name"]

    backup_path = tmp_path / "data" / "system_backups" / state["backup_name"]
    assert backup_path.is_file()
    with zipfile.ZipFile(backup_path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["automatic"] is True
    assert manifest["purpose"] == "pre_update"
    assert manifest["source_commit"] == commit


def test_admin_system_update_page_shows_rollback_target(monkeypatch) -> None:
    commit = "b" * 40
    monkeypatch.setattr(
        admin_router,
        "_read_update_rollback_state",
        lambda: {
            "created_at": "2026-06-24T20:00:00",
            "previous_commit": commit,
            "previous_commit_short": commit[:7],
            "previous_branch": "main",
            "update_channel": "commit",
            "backup_name": "kasse-system-backup-test.zip",
            "backup_exists": "1",
        },
    )
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/system-update")
    assert r.status_code == 200
    assert "Rollback auf bbbbbbb starten" in r.text
    assert "kasse-system-backup-test.zip" in r.text


def test_admin_system_rollback_post_triggers_background_runner(monkeypatch) -> None:
    commit = "c" * 40
    calls: list[str] = []
    state = {
        "created_at": "2026-06-24T20:00:00",
        "previous_commit": commit,
        "previous_commit_short": commit[:7],
        "previous_branch": "main",
        "update_channel": "release",
        "backup_name": "backup.zip",
        "backup_exists": "1",
    }

    def fake_trigger(received_state: dict[str, str]) -> None:
        calls.append(received_state["previous_commit"])

    monkeypatch.setattr(admin_router, "_read_update_rollback_state", lambda: state)
    monkeypatch.setattr(admin_router, "_trigger_background_rollback", fake_trigger)
    monkeypatch.setattr(admin_router, "_is_update_running", lambda: False)
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda raw: raw == "master")
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post(
            "/admin/system-update/rollback",
            data={"master_password": "master"},
            follow_redirects=False,
        )
    assert r.status_code == 200
    assert "Rollback und Neustart laufen" in r.text
    assert calls == [commit]


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
            "commit_update_available": False,
            "release_update_available": False,
            "commit_only_update_available": False,
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
            "commit_update_available": False,
            "release_update_available": False,
            "commit_only_update_available": False,
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


def test_admin_system_update_post_rejects_when_update_already_running(monkeypatch) -> None:
    monkeypatch.setattr(admin_router, "_is_update_running", lambda: True)
    monkeypatch.setattr(admin_router, "read_master_password", lambda: "master")
    monkeypatch.setattr(admin_router.admin_auth, "is_master_password", lambda _raw: True)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post("/admin/system-update", data={"master_password": "master"}, follow_redirects=False)
        assert r.status_code == 409
        assert "läuft bereits" in r.text
