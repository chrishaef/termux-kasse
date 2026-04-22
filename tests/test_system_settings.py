from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app import backup_service
from app import db
from app import system_settings
from app.main import app


def test_weekly_backup_runs_only_once_per_interval(tmp_path) -> None:
    archive_dir = tmp_path / "data" / "system_backups"

    with TestClient(app) as client:
        first = client.get("/")
        assert first.status_code == 200

        stored_files = sorted(archive_dir.glob("kasse-system-backup-*.zip"))
        assert len(stored_files) == 1

        second = client.get("/top-ten")
        assert second.status_code == 200
        stored_again = sorted(archive_dir.glob("kasse-system-backup-*.zip"))
        assert len(stored_again) == 1

        with db.get_connection() as conn:
            backup_service.set_last_auto_backup_at(conn, datetime.now() - timedelta(days=8))

        third = client.get("/")
        assert third.status_code == 200
        stored_after_due = sorted(archive_dir.glob("kasse-system-backup-*.zip"))
        assert len(stored_after_due) == 2

        newest = max(stored_after_due, key=lambda path: path.stat().st_mtime)
        with zipfile.ZipFile(newest, "r") as zf:
            manifest = zf.read("manifest.json").decode("utf-8")
        assert '"automatic": true' in manifest


def test_weekly_backup_deletes_only_auto_backups_older_than_four_weeks(tmp_path) -> None:
    archive_dir = tmp_path / "data" / "system_backups"

    with TestClient(app) as client:
        first = client.get("/")
        assert first.status_code == 200

        old_auto = backup_service.create_system_backup_archive(
            datetime.now() - timedelta(days=35),
            automatic=True,
        )
        recent_auto = backup_service.create_system_backup_archive(
            datetime.now() - timedelta(days=21),
            automatic=True,
        )
        manual_backup = backup_service.create_system_backup_archive(
            datetime.now() - timedelta(days=60),
            automatic=False,
        )

        assert old_auto is not None
        assert recent_auto is not None
        assert manual_backup is not None
        assert old_auto.exists()
        assert recent_auto.exists()
        assert manual_backup.exists()

        with db.get_connection() as conn:
            backup_service.set_last_auto_backup_at(conn, datetime.now() - timedelta(days=8))

        due = client.get("/top-ten")
        assert due.status_code == 200

        assert not old_auto.exists()
        assert recent_auto.exists()
        assert manual_backup.exists()

        stored_files = sorted(archive_dir.glob("kasse-system-backup-*.zip"))
        assert len(stored_files) >= 3


def test_admin_system_settings_can_be_saved_and_are_used_in_base_template() -> None:
    with TestClient(app) as client:
        login = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303

        page = client.get("/admin/system-settings")
        assert page.status_code == 200
        assert re.search(r'name="admin_logout_seconds"[^>]*value="25"', page.text)
        assert re.search(r'name="kiosk_preisliste_seconds"[^>]*value="60"', page.text)
        assert re.search(r'name="kiosk_home_seconds"[^>]*value="30"', page.text)

        save = client.post(
            "/admin/system-settings",
            data={
                "admin_logout_seconds": "25",
                "kiosk_preisliste_seconds": "75",
                "kiosk_home_seconds": "45",
            },
            follow_redirects=False,
        )
        assert save.status_code == 303
        assert save.headers["location"] == "/admin/system-settings?saved=1"

        with db.get_connection() as conn:
            assert system_settings.get_timeout_settings(conn) == {
                "admin_logout_seconds": 25,
                "kiosk_preisliste_seconds": 75,
                "kiosk_home_seconds": 45,
            }

        admin_page = client.get("/admin")
        assert admin_page.status_code == 200
        assert "adminLogoutSeconds: 25" in admin_page.text
        assert "kioskPreislisteSeconds: 75" in admin_page.text
        assert "kioskHomeSeconds: 45" in admin_page.text


def test_last_auto_backup_is_none_when_auto_backup_files_are_deleted(tmp_path) -> None:
    with TestClient(app) as client:
        first = client.get("/")
        assert first.status_code == 200

        with db.get_connection() as conn:
            stored_before = backup_service.get_last_auto_backup_at(conn)
            assert stored_before is not None
        existing_before = backup_service.get_last_existing_auto_backup_at()
        assert existing_before is not None

        archive_dir = tmp_path / "data" / "system_backups"
        for path in archive_dir.glob("*.zip"):
            path.unlink(missing_ok=True)

        with db.get_connection() as conn:
            stored_after = backup_service.get_last_auto_backup_at(conn)
            assert stored_after is not None
        existing_after = backup_service.get_last_existing_auto_backup_at()
        assert existing_after is None
