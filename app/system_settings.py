from __future__ import annotations

import sqlite3

from app import db

KEY_ADMIN_LOGOUT_SECONDS = "admin_logout_seconds"
KEY_KIOSK_PREISLISTE_SECONDS = "kiosk_preisliste_seconds"
KEY_KIOSK_HOME_SECONDS = "kiosk_home_seconds"
KEY_KIOSK_PREISLISTE_ENABLED = "kiosk_preisliste_enabled"
KEY_KIOSK_GROUP_LOGO_ZOOM_ENABLED = "kiosk_group_logo_zoom_enabled"
KEY_KIOSK_GROUP_LOGO_ANIMATION_SPEED = "kiosk_group_logo_animation_speed"

DEFAULT_ADMIN_LOGOUT_SECONDS = 25
DEFAULT_KIOSK_PREISLISTE_SECONDS = 60
DEFAULT_KIOSK_HOME_SECONDS = 30
DEFAULT_KIOSK_PREISLISTE_ENABLED = True
DEFAULT_KIOSK_GROUP_LOGO_ZOOM_ENABLED = True
DEFAULT_KIOSK_GROUP_LOGO_ANIMATION_SPEED = "normal"

MIN_TIMEOUT_SECONDS = 5
MAX_TIMEOUT_SECONDS = 3600
VALID_GROUP_LOGO_ANIMATION_SPEEDS = {"slow", "normal", "fast", "very_fast"}


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


def _read_bool(conn: sqlite3.Connection, key: str) -> bool | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None:
        return None
    raw = str(row["value"]).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _save_bool(conn: sqlite3.Connection, key: str, value: bool) -> bool:
    normalized = bool(value)
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, "1" if normalized else "0"),
    )
    return normalized


def _read_animation_speed(conn: sqlite3.Connection, key: str) -> str | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None:
        return None
    raw = str(row["value"]).strip().lower()
    return raw if raw in VALID_GROUP_LOGO_ANIMATION_SPEEDS else None


def _save_animation_speed(conn: sqlite3.Connection, key: str, value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_GROUP_LOGO_ANIMATION_SPEEDS:
        normalized = DEFAULT_KIOSK_GROUP_LOGO_ANIMATION_SPEED
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, normalized),
    )
    return normalized


def default_timeout_settings() -> dict[str, int | bool | str]:
    return {
        "admin_logout_seconds": DEFAULT_ADMIN_LOGOUT_SECONDS,
        "kiosk_preisliste_seconds": DEFAULT_KIOSK_PREISLISTE_SECONDS,
        "kiosk_home_seconds": DEFAULT_KIOSK_HOME_SECONDS,
        "kiosk_preisliste_enabled": DEFAULT_KIOSK_PREISLISTE_ENABLED,
        "kiosk_group_logo_zoom_enabled": DEFAULT_KIOSK_GROUP_LOGO_ZOOM_ENABLED,
        "kiosk_group_logo_animation_speed": DEFAULT_KIOSK_GROUP_LOGO_ANIMATION_SPEED,
    }


def get_timeout_settings(conn: sqlite3.Connection) -> dict[str, int | bool | str]:
    defaults = default_timeout_settings()
    preisliste_enabled = _read_bool(conn, KEY_KIOSK_PREISLISTE_ENABLED)
    logo_zoom_enabled = _read_bool(conn, KEY_KIOSK_GROUP_LOGO_ZOOM_ENABLED)
    logo_animation_speed = _read_animation_speed(conn, KEY_KIOSK_GROUP_LOGO_ANIMATION_SPEED)
    return {
        "admin_logout_seconds": _normalize_timeout(
            _read_int(conn, KEY_ADMIN_LOGOUT_SECONDS),
            int(defaults["admin_logout_seconds"]),
        ),
        "kiosk_preisliste_seconds": _normalize_timeout(
            _read_int(conn, KEY_KIOSK_PREISLISTE_SECONDS),
            int(defaults["kiosk_preisliste_seconds"]),
        ),
        "kiosk_home_seconds": _normalize_timeout(
            _read_int(conn, KEY_KIOSK_HOME_SECONDS),
            int(defaults["kiosk_home_seconds"]),
        ),
        "kiosk_preisliste_enabled": (
            preisliste_enabled
            if preisliste_enabled is not None
            else bool(defaults["kiosk_preisliste_enabled"])
        ),
        "kiosk_group_logo_zoom_enabled": (
            logo_zoom_enabled
            if logo_zoom_enabled is not None
            else bool(defaults["kiosk_group_logo_zoom_enabled"])
        ),
        "kiosk_group_logo_animation_speed": (
            logo_animation_speed
            if logo_animation_speed is not None
            else str(defaults["kiosk_group_logo_animation_speed"])
        ),
    }


def save_timeout_settings(
    conn: sqlite3.Connection,
    *,
    admin_logout_seconds: int,
    kiosk_preisliste_seconds: int,
    kiosk_home_seconds: int,
    kiosk_preisliste_enabled: bool = DEFAULT_KIOSK_PREISLISTE_ENABLED,
    kiosk_group_logo_zoom_enabled: bool = DEFAULT_KIOSK_GROUP_LOGO_ZOOM_ENABLED,
    kiosk_group_logo_animation_speed: str = DEFAULT_KIOSK_GROUP_LOGO_ANIMATION_SPEED,
) -> dict[str, int | bool | str]:
    admin_seconds = _normalize_timeout(admin_logout_seconds, DEFAULT_ADMIN_LOGOUT_SECONDS)
    preisliste_seconds = _normalize_timeout(
        kiosk_preisliste_seconds,
        DEFAULT_KIOSK_PREISLISTE_SECONDS,
    )
    home_seconds = _normalize_timeout(kiosk_home_seconds, DEFAULT_KIOSK_HOME_SECONDS)
    _save_int(conn, KEY_ADMIN_LOGOUT_SECONDS, admin_seconds)
    _save_int(conn, KEY_KIOSK_PREISLISTE_SECONDS, preisliste_seconds)
    _save_int(conn, KEY_KIOSK_HOME_SECONDS, home_seconds)
    preisliste_enabled = _save_bool(
        conn,
        KEY_KIOSK_PREISLISTE_ENABLED,
        kiosk_preisliste_enabled,
    )
    logo_zoom_enabled = _save_bool(
        conn,
        KEY_KIOSK_GROUP_LOGO_ZOOM_ENABLED,
        kiosk_group_logo_zoom_enabled,
    )
    logo_animation_speed = _save_animation_speed(
        conn,
        KEY_KIOSK_GROUP_LOGO_ANIMATION_SPEED,
        kiosk_group_logo_animation_speed,
    )
    return {
        "admin_logout_seconds": admin_seconds,
        "kiosk_preisliste_seconds": preisliste_seconds,
        "kiosk_home_seconds": home_seconds,
        "kiosk_preisliste_enabled": preisliste_enabled,
        "kiosk_group_logo_zoom_enabled": logo_zoom_enabled,
        "kiosk_group_logo_animation_speed": logo_animation_speed,
    }
