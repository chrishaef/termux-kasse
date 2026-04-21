from __future__ import annotations

import io
import json
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from app import db
from app.config import db_path
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


def test_system_backup_export_contains_db_and_year_end_files(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    export_dir = tmp_path / "data" / "jahresabschluss"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "Jahresabschluss_20260101.pdf").write_bytes(b"pdf-demo")
    (export_dir / "Jahresabschluss_20260101.xlsx").write_bytes(b"xlsx-demo")
    (export_dir / "Jahresabschluss_20260101.zip").write_bytes(b"zip-demo")
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        r = client.get("/admin/backup/export")
        assert r.status_code == 200
        assert "application/zip" in r.headers.get("content-type", "")
        with zipfile.ZipFile(io.BytesIO(r.content), "r") as zf:
            names = set(zf.namelist())
            assert "manifest.json" in names
            assert "kasse.db" in names
            assert "jahresabschluss/Jahresabschluss_20260101.pdf" in names
            assert "jahresabschluss/Jahresabschluss_20260101.xlsx" in names
            assert "jahresabschluss/Jahresabschluss_20260101.zip" in names
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["format"] == "kasse-system-backup"
            assert manifest["version"] == 1
            assert manifest["files"]["db"]["path"] == "kasse.db"


def test_system_backup_import_rejects_invalid_manifest(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        backup_buf = io.BytesIO()
        with zipfile.ZipFile(backup_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", '{"format":"wrong"}')
            zf.writestr("kasse.db", db_path().read_bytes())
        files = {"backup_file": ("kasse-system-backup.zip", backup_buf.getvalue(), "application/zip")}
        r = client.post("/admin/backup/import", files=files, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].endswith("/admin/backup?err=invalid")


def test_system_backup_preview_returns_manifest_details(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        backup_buf = io.BytesIO()
        with zipfile.ZipFile(backup_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": "kasse-system-backup",
                        "version": 1,
                        "created_at": "2026-04-21T12:00:00",
                        "files": {"db": {"path": "kasse.db", "bytes": 1}, "year_end_exports": []},
                    }
                ),
            )
            zf.writestr("kasse.db", db_path().read_bytes())
            zf.writestr("jahresabschluss/a.pdf", b"a")
        files = {"backup_file": ("kasse-system-backup.zip", backup_buf.getvalue(), "application/zip")}
        r = client.post("/admin/backup/preview", files=files)
        assert r.status_code == 200
        out = r.json()
        assert out["ok"] is True
        assert out["preview"]["kind"] == "system_zip"
        assert out["preview"]["has_manifest"] is True
        assert out["preview"]["manifest_created_at"] == "2026-04-21T12:00:00"
        assert "jahresabschluss/a.pdf" in out["preview"]["year_end_files"]


def test_system_backup_import_replaces_db_and_year_end_files(tmp_path, monkeypatch) -> None:
    _master_env(tmp_path, monkeypatch)
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "ALT"})
        old_export_dir = tmp_path / "data" / "jahresabschluss"
        old_export_dir.mkdir(parents=True, exist_ok=True)
        (old_export_dir / "old.pdf").write_bytes(b"old")

        source_db = tmp_path / "source.db"
        with db.connect() as conn:
            conn.execute("INSERT INTO user_groups (name, sort_order) VALUES (?, ?)", ("NEU", 10))
            conn.commit()
        source_db.write_bytes(db_path().read_bytes())

        backup_buf = io.BytesIO()
        with zipfile.ZipFile(backup_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("kasse.db", source_db.read_bytes())
            zf.writestr("jahresabschluss/new.pdf", b"new-pdf")
            zf.writestr("jahresabschluss/new.xlsx", b"new-xlsx")
            zf.writestr("jahresabschluss/new.zip", b"new-zip")

        files = {"backup_file": ("kasse-system-backup.zip", backup_buf.getvalue(), "application/zip")}
        r = client.post("/admin/backup/import", files=files, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].endswith("/admin/backup?saved=1")

        with db.get_connection() as conn:
            names = [str(row[0]) for row in conn.execute("SELECT name FROM user_groups").fetchall()]
            assert "NEU" in names
        files_after = sorted(p.name for p in old_export_dir.glob("*") if p.is_file())
        assert files_after == ["new.pdf", "new.xlsx", "new.zip"]
