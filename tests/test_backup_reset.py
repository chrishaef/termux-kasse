from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase, user_balance_cents
from app.main import app


def _master_env(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KASSE_DATA_DIR", str(data))
    mp = tmp_path / "master_secret.txt"
    mp.write_text("reset-master-secret", encoding="utf-8")
    monkeypatch.setenv("KASSE_MASTER_PASSWORD_FILE", str(mp))


def test_backup_reset_requires_master_and_confirm(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post(
            "/admin/backup/reset-transactional",
            data={"master_password": "wrong", "confirm_reset": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "reset_err=master" in r.headers["location"]

        r2 = client.post(
            "/admin/backup/reset-transactional",
            data={"master_password": "reset-master-secret"},
            follow_redirects=False,
        )
        assert r2.status_code == 303
        assert "reset_err=noconfirm" in r2.headers["location"]


def test_backup_reset_clears_ledger_keeps_stammdaten(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "U1", "group_id": str(gid)})
        client.post("/admin/products", data={"name": "P1", "price_eur": "2.00"})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "P1", 200)
        with db.get_connection() as conn:
            assert user_balance_cents(conn, uid) == 200

        r = client.post(
            "/admin/backup/reset-transactional",
            data={"master_password": "reset-master-secret", "confirm_reset": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].endswith("/admin/backup?reset=1")

        with db.get_connection() as conn:
            assert int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]) >= 1
            assert int(conn.execute("SELECT COUNT(*) FROM user_groups").fetchone()[0]) >= 1
            assert int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]) >= 1
            assert int(conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]) == 0
            assert int(conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]) == 0
            assert user_balance_cents(conn, uid) == 0
