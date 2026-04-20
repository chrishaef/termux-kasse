from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app import ledger_service
from app.ledger_service import add_purchase, user_balance_cents
from app.main import app


def _master_env(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("KASSE_DATA_DIR", str(data))
    mp = tmp_path / "master_secret.txt"
    mp.write_text("year-end-master-xyz", encoding="utf-8")
    monkeypatch.setenv("KASSE_MASTER_PASSWORD_FILE", str(mp))


def test_year_end_post_requires_master_and_confirm(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.post(
            "/admin/settlements/year-end",
            data={"master_password": "wrong", "confirm_irreversible": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "err=master" in r.headers["location"]

        r2 = client.post(
            "/admin/settlements/year-end",
            data={"master_password": "year-end-master-xyz"},
            follow_redirects=False,
        )
        assert r2.status_code == 303
        assert "err=noconfirm" in r2.headers["location"]


def test_year_end_archive_purge_keeps_open_ledger(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Clara", "group_id": str(gid)})
        client.post("/admin/products", data={"name": "Wasser", "price_eur": "1.50"})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "Wasser", 150)
            add_purchase(conn, uid, pid, "Wasser", 150)
        with db.get_connection() as conn:
            assert user_balance_cents(conn, uid) == 300
        with db.get_connection() as conn:
            sid = ledger_service.create_settlement_for_user(
                conn, uid, "Test", None, None, received_confirmed=1
            )
        assert sid is not None
        with db.get_connection() as conn:
            add_purchase(conn, uid, pid, "Wasser", 150)
        with db.get_connection() as conn:
            assert user_balance_cents(conn, uid) == 150
            n_settle = int(conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0])
            assert n_settle >= 1

        r = client.post(
            "/admin/settlements/year-end",
            data={"master_password": "year-end-master-xyz", "confirm_irreversible": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        assert r.content[:2] == b"PK"

        with db.get_connection() as conn:
            assert int(conn.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]) == 0
            assert int(
                conn.execute("SELECT COUNT(*) FROM ledger_entries WHERE settlement_id IS NOT NULL").fetchone()[0]
            ) == 0
            assert int(conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]) == 1
            assert user_balance_cents(conn, uid) == 150

        export_dir = Path(os.environ["KASSE_DATA_DIR"]) / "jahresabschluss"
        assert export_dir.is_dir()
        pdfs = list(export_dir.glob("Jahresabschluss_*.pdf"))
        xlsxs = list(export_dir.glob("Jahresabschluss_*.xlsx"))
        zips = list(export_dir.glob("Jahresabschluss_*.zip"))
        assert len(pdfs) == 1 and len(xlsxs) == 1 and len(zips) == 1
