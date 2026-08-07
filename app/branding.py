"""Instanz-Branding (Logo + Anzeigename) mit Fallback auf das Standard-WSG-Logo."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import db
from app import group_logo_util
from app.config import data_dir

KEY_SHOP_DISPLAY_NAME = "shop_display_name"
DEFAULT_SHOP_DISPLAY_NAME = "Shopkasse"
DEFAULT_LOGO_URL = "/static/wsg-logo.png"
LOGO_FILENAME = "logo.png"
_MAX_DISPLAY_NAME_LEN = 64


def branding_dir() -> Path:
    path = data_dir() / "branding"
    path.mkdir(parents=True, exist_ok=True)
    return path


def custom_logo_path() -> Path:
    return branding_dir() / LOGO_FILENAME


def default_static_logo_path() -> Path:
    return Path(__file__).resolve().parent / "static" / "wsg-logo.png"


def has_custom_logo() -> bool:
    return custom_logo_path().is_file()


def resolve_logo_file_path() -> Path:
    custom = custom_logo_path()
    if custom.is_file():
        return custom
    return default_static_logo_path()


def logo_url() -> str:
    custom = custom_logo_path()
    if custom.is_file():
        try:
            version = int(custom.stat().st_mtime)
        except OSError:
            version = 0
        return f"/branding/logo?v={version}"
    return DEFAULT_LOGO_URL


def _normalize_display_name(raw: str | None) -> str:
    text = (raw or "").strip()
    if not text:
        return DEFAULT_SHOP_DISPLAY_NAME
    return text[:_MAX_DISPLAY_NAME_LEN]


def _read_display_name(conn: sqlite3.Connection) -> str:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (KEY_SHOP_DISPLAY_NAME,))
    if not row or row["value"] is None:
        return DEFAULT_SHOP_DISPLAY_NAME
    return _normalize_display_name(str(row["value"]))


def save_display_name(conn: sqlite3.Connection, value: str | None) -> str:
    normalized = _normalize_display_name(value)
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (KEY_SHOP_DISPLAY_NAME, normalized),
    )
    return normalized


def save_logo_png(data: bytes) -> Path:
    group_logo_util.validate_png_bytes(data)
    normalized = group_logo_util.normalize_logo_png(data)
    path = custom_logo_path()
    path.write_bytes(normalized)
    return path


def delete_custom_logo() -> None:
    path = custom_logo_path()
    if path.is_file():
        path.unlink()


def get_branding(conn: sqlite3.Connection | None = None) -> dict[str, str | bool]:
    if conn is None:
        with db.get_connection() as owned:
            return get_branding(owned)
    return {
        "display_name": _read_display_name(conn),
        "logo_url": logo_url(),
        "has_custom_logo": has_custom_logo(),
    }


def default_branding() -> dict[str, str | bool]:
    return {
        "display_name": DEFAULT_SHOP_DISPLAY_NAME,
        "logo_url": DEFAULT_LOGO_URL,
        "has_custom_logo": False,
    }
