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
