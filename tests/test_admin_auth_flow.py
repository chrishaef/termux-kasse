from fastapi.testclient import TestClient

from app.main import app


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
