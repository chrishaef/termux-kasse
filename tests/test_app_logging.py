from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi.testclient import TestClient

from app import app_logging
from app.routers import admin
from app.main import app


def test_app_logging_writes_rotating_http_error_log(tmp_path) -> None:
    with TestClient(app) as client:
        response = client.get("/does-not-exist")
        assert response.status_code == 404

    log_path = tmp_path / "data" / "logs" / "app.log"
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "HTTP-Fehler" in text
    assert "status_code=404" in text

    logger = logging.getLogger("shopkasse")
    handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert handlers
    assert handlers[0].maxBytes == app_logging.LOG_MAX_BYTES
    assert handlers[0].backupCount == app_logging.LOG_BACKUP_COUNT


def test_admin_syslogs_are_linked_and_visible(tmp_path) -> None:
    with TestClient(app) as client:
        login = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303

        dashboard = client.get("/admin")
        assert dashboard.status_code == 200
        assert 'href="/admin/syslogs"' in dashboard.text
        assert "syslogs" in dashboard.text

        page = client.get("/admin/syslogs")
        assert page.status_code == 200
        assert "Syslogs" in page.text
        assert "app.log" in page.text
        assert "Admin-Login erfolgreich" in page.text
        assert "syslogs_viewed" not in page.text


def test_admin_syslogs_reject_unknown_log_key() -> None:
    with TestClient(app) as client:
        login = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303

        response = client.get("/admin/syslogs?log=../../secret")
        assert response.status_code == 404


def test_syslog_tail_shows_newest_entries_first(tmp_path) -> None:
    log_file = tmp_path / "example.log"
    log_file.write_text("alt\nmittel\nneu\n", encoding="utf-8")

    assert admin._read_syslog_tail(log_file) == ["neu", "mittel", "alt"]


def test_favicon_404_is_not_written_to_app_log(tmp_path) -> None:
    with TestClient(app) as client:
        response = client.get("/favicon.ico")
        assert response.status_code == 404

    log_path = tmp_path / "data" / "logs" / "app.log"
    text = log_path.read_text(encoding="utf-8")
    assert "/favicon.ico" not in text


def test_run_script_disables_uvicorn_access_log() -> None:
    run_script = Path(__file__).resolve().parent.parent / "run.sh"
    assert "--no-access-log" in run_script.read_text(encoding="utf-8")
