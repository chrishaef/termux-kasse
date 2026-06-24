from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from fastapi.testclient import TestClient

from app import app_logging
from app.main import app


def test_app_logging_writes_rotating_http_error_log(tmp_path) -> None:
    with TestClient(app) as client:
        response = client.get("/does-not-exist")
        assert response.status_code == 404

    log_path = tmp_path / "data" / "logs" / "app.log"
    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert '"event":"http_error"' in text
    assert '"status_code":404' in text

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
        assert "admin_login_success" in page.text


def test_admin_syslogs_reject_unknown_log_key() -> None:
    with TestClient(app) as client:
        login = client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        assert login.status_code == 303

        response = client.get("/admin/syslogs?log=../../secret")
        assert response.status_code == 404
