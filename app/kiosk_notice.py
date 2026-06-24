"""Kiosk-Hinweiszeile: vom Admin gesetzte Nachricht mit Darstellung."""

from __future__ import annotations

import json
from typing import Any

from app import db

KEY = "kiosk_notice"

DEFAULT_KIOSK_NOTICE = ""
DEFAULT_ALIGNMENT = "center"
DEFAULT_SIZE = "normal"
DEFAULT_ICON = "info-blue"

ALIGNMENTS = ("left", "center", "right")
SIZES = ("small", "normal", "large", "xlarge")
ICONS = ("announcement", "info-blue", "info-green", "warning", "none")

ICON_LABELS = {
    "announcement": "Durchsage",
    "info-blue": "Info blau",
    "info-green": "Info gruen",
    "warning": "Warnung",
    "none": "Kein Icon",
}

ICON_FILES = {
    "announcement": "announcement.png",
    "info-blue": "info-blue.png",
    "info-green": "info-green.png",
    "warning": "warning.png",
    "none": "",
}

ICON_ALIASES = {
    "info": "info-blue",
    "megaphone": "announcement",
    "star": "info-green",
}


def _normalize_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in allowed else default


def _normalize_icon(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = ICON_ALIASES.get(raw, raw)
    return raw if raw in ICONS else DEFAULT_ICON


def _with_icon_file(settings: dict[str, str]) -> dict[str, str]:
    return {**settings, "icon_file": ICON_FILES.get(settings["icon"], "")}


def _default_settings(message: str = "") -> dict[str, str]:
    return _with_icon_file(
        {
            "message": message,
            "alignment": DEFAULT_ALIGNMENT,
            "size": DEFAULT_SIZE,
            "icon": DEFAULT_ICON,
        }
    )


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
    return _with_icon_file(
        {
            "message": str(payload.get("message") or "").strip(),
            "alignment": _normalize_choice(
                payload.get("alignment"),
                ALIGNMENTS,
                DEFAULT_ALIGNMENT,
            ),
            "size": _normalize_choice(payload.get("size"), SIZES, DEFAULT_SIZE),
            "icon": _normalize_icon(payload.get("icon")),
        }
    )


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
        "icon": _normalize_icon(icon),
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
