"""Kiosk-Hinweiszeile: vom Admin gesetzte Nachricht mit Darstellung."""

from __future__ import annotations

import json
from typing import Any

from app import db

KEY = "kiosk_notice"

DEFAULT_KIOSK_NOTICE = ""
DEFAULT_ALIGNMENT = "center"
DEFAULT_SIZE = "normal"
DEFAULT_ICON = "info"

ALIGNMENTS = ("left", "center", "right")
SIZES = ("small", "normal", "large", "xlarge")
ICONS = ("info", "megaphone", "warning", "star", "none")

ICON_LABELS = {
    "info": "Info",
    "megaphone": "Durchsage",
    "warning": "Warnung",
    "star": "Stern",
    "none": "Kein Icon",
}

ICON_SYMBOLS = {
    "info": "i",
    "megaphone": "!",
    "warning": "!",
    "star": "*",
    "none": "",
}


def _normalize_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in allowed else default


def _default_settings(message: str = "") -> dict[str, str]:
    return {
        "message": message,
        "alignment": DEFAULT_ALIGNMENT,
        "size": DEFAULT_SIZE,
        "icon": DEFAULT_ICON,
    }


def _parse_stored(raw: str) -> dict[str, str]:
    if not raw:
        return _default_settings()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Legacy installations stored only the plain message text.
        return _default_settings(raw)
    if not isinstance(payload, dict):
        return _default_settings()
    return {
        "message": str(payload.get("message") or "").strip(),
        "alignment": _normalize_choice(
            payload.get("alignment"),
            ALIGNMENTS,
            DEFAULT_ALIGNMENT,
        ),
        "size": _normalize_choice(payload.get("size"), SIZES, DEFAULT_SIZE),
        "icon": _normalize_choice(payload.get("icon"), ICONS, DEFAULT_ICON),
    }


def get_stored_custom() -> str:
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (KEY,))
    if not row:
        return ""
    return _parse_stored(str(row["value"] or ""))["message"]


def get_settings() -> dict[str, str]:
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (KEY,))
    if not row:
        return _default_settings()
    return _parse_stored(str(row["value"] or ""))


def get_display_text() -> str:
    custom = get_settings()["message"].strip()
    if custom:
        return custom
    return ""


def set_custom_message(
    text: str,
    *,
    alignment: str = DEFAULT_ALIGNMENT,
    size: str = DEFAULT_SIZE,
    icon: str = DEFAULT_ICON,
) -> None:
    body = text.strip()
    settings = {
        "message": body,
        "alignment": _normalize_choice(alignment, ALIGNMENTS, DEFAULT_ALIGNMENT),
        "size": _normalize_choice(size, SIZES, DEFAULT_SIZE),
        "icon": _normalize_choice(icon, ICONS, DEFAULT_ICON),
    }
    stored = json.dumps(settings, ensure_ascii=True, separators=(",", ":"))
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (KEY, stored),
        )
