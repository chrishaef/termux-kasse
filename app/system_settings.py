from __future__ import annotations

import sqlite3

from app import db

KEY_ADMIN_LOGOUT_SECONDS = "admin_logout_seconds"
KEY_KIOSK_PREISLISTE_SECONDS = "kiosk_preisliste_seconds"
KEY_KIOSK_HOME_SECONDS = "kiosk_home_seconds"

DEFAULT_ADMIN_LOGOUT_SECONDS = 25
DEFAULT_KIOSK_PREISLISTE_SECONDS = 60
DEFAULT_KIOSK_HOME_SECONDS = 30

MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 3600


def _read_int(conn: sqlite3.Connection, key: str) -> int | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None:
        return None
    raw = str(row["value"]).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _normalize_timeout(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, int(value)))


def _save_int(conn: sqlite3.Connection, key: str, value: int) -> int:
    normalized = _normalize_timeout(value, DEFAULT_ADMIN_LOGOUT_SECONDS)
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(normalized)),
    )
    return normalized


def default_timeout_settings() -> dict[str, int]:
    return {
        "admin_logout_seconds": DEFAULT_ADMIN_LOGOUT_SECONDS,
        "kiosk_preisliste_seconds": DEFAULT_KIOSK_PREISLISTE_SECONDS,
        "kiosk_home_seconds": DEFAULT_KIOSK_HOME_SECONDS,
    }


def get_timeout_settings(conn: sqlite3.Connection) -> dict[str, int]:
    defaults = default_timeout_settings()
    return {
        "admin_logout_seconds": _normalize_timeout(
            _read_int(conn, KEY_ADMIN_LOGOUT_SECONDS),
            defaults["admin_logout_seconds"],
        ),
        "kiosk_preisliste_seconds": _normalize_timeout(
            _read_int(conn, KEY_KIOSK_PREISLISTE_SECONDS),
            defaults["kiosk_preisliste_seconds"],
        ),
        "kiosk_home_seconds": _normalize_timeout(
            _read_int(conn, KEY_KIOSK_HOME_SECONDS),
            defaults["kiosk_home_seconds"],
        ),
    }


def save_timeout_settings(
    conn: sqlite3.Connection,
    *,
    admin_logout_seconds: int,
    kiosk_preisliste_seconds: int,
    kiosk_home_seconds: int,
) -> dict[str, int]:
    admin_seconds = _normalize_timeout(admin_logout_seconds, DEFAULT_ADMIN_LOGOUT_SECONDS)
    preisliste_seconds = _normalize_timeout(
        kiosk_preisliste_seconds,
        DEFAULT_KIOSK_PREISLISTE_SECONDS,
    )
    home_seconds = _normalize_timeout(kiosk_home_seconds, DEFAULT_KIOSK_HOME_SECONDS)
    _save_int(conn, KEY_ADMIN_LOGOUT_SECONDS, admin_seconds)
    _save_int(conn, KEY_KIOSK_PREISLISTE_SECONDS, preisliste_seconds)
    _save_int(conn, KEY_KIOSK_HOME_SECONDS, home_seconds)
    return {
        "admin_logout_seconds": admin_seconds,
        "kiosk_preisliste_seconds": preisliste_seconds,
        "kiosk_home_seconds": home_seconds,
    }
