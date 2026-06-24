from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from starlette.requests import Request

from app.config import data_dir

LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5
SERVER_LOG_MAX_BYTES = 2_000_000
UPDATE_LOG_MAX_BYTES = 1_000_000
PLAIN_LOG_BACKUP_COUNT = 5

_HANDLER_MARKER = "_shopkasse_rotating_handler"

EVENT_LABELS = {
    "app_start": "App gestartet",
    "app_stop": "App beendet",
    "http_error": "HTTP-Fehler",
    "admin_login_failed": "Admin-Login fehlgeschlagen",
    "admin_login_success": "Admin-Login erfolgreich",
    "admin_logout": "Admin abgemeldet",
    "admin_password_changed": "Admin-Passwort geaendert",
    "system_update_start": "System-Update gestartet",
    "system_update_start_failed": "System-Update konnte nicht gestartet werden",
    "system_rollback_start": "System-Rollback gestartet",
    "system_rollback_start_failed": "System-Rollback konnte nicht gestartet werden",
    "backup_export_rejected": "Backup-Export abgelehnt",
    "backup_export_created": "Backup erstellt",
    "backup_import_rejected": "Backup-Import abgelehnt",
    "backup_import_invalid": "Backup-Import ungueltig",
    "backup_import_completed": "Backup-Import abgeschlossen",
    "transaction_reset_rejected": "Buchungs-Reset abgelehnt",
    "transaction_reset_completed": "Buchungs-Reset ausgefuehrt",
    "kiosk_notice_saved": "Kiosk-Nachricht gespeichert",
    "system_settings_saved": "Systemzeiten gespeichert",
    "group_logo_invalid": "Gruppenlogo ungueltig",
    "group_logo_saved": "Gruppenlogo gespeichert",
    "group_logo_removed": "Gruppenlogo entfernt",
}


def app_log_path() -> Path:
    log_dir = data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "app.log"


def configure_logging() -> Path:
    path = app_log_path()
    logger = logging.getLogger("shopkasse")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            current = Path(getattr(handler, "baseFilename", ""))
            if current == path:
                return path
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return path


def get_logger(name: str = "app") -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"shopkasse.{name}")


def _client_host(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "-"
    text = str(value)
    if not text:
        return '""'
    if any(ch.isspace() for ch in text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _format_event_message(event: str, fields: dict[str, Any]) -> str:
    label = EVENT_LABELS.get(event, event)
    if not fields:
        return label
    details = " ".join(f"{key}={_format_value(value)}" for key, value in fields.items())
    return f"{label} | {details}"


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    request: Request | None = None,
    **fields: Any,
) -> None:
    payload: dict[str, Any] = dict(fields)
    if request is not None:
        payload.update(
            {
                "method": request.method,
                "path": request.url.path,
                "client": _client_host(request),
            }
        )
    logger.log(level, _format_event_message(event, payload))


def rotate_plain_log(path: Path, *, max_bytes: int, backup_count: int = PLAIN_LOG_BACKUP_COUNT) -> None:
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        for idx in range(backup_count - 1, 0, -1):
            src = path.with_name(f"{path.name}.{idx}")
            dst = path.with_name(f"{path.name}.{idx + 1}")
            if src.exists():
                if dst.exists():
                    dst.unlink()
                src.replace(dst)
        first = path.with_name(f"{path.name}.1")
        if first.exists():
            first.unlink()
        path.replace(first)
    except OSError:
        # Logging must never prevent the kiosk from starting or updating.
        return
