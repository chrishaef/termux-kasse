"""Kiosk-Hinweiszeile: Standardtext oder von Admin gesetzte Nachricht."""

from __future__ import annotations

from app import db

KEY = "kiosk_notice"

DEFAULT_KIOSK_NOTICE = (
    "Vertrauensbasis: Buchungen am Kiosk sind nicht passwortgeschützt. "
    "Nur der Admin-Bereich ist geschützt."
)


def get_stored_custom() -> str:
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (KEY,))
    if not row:
        return ""
    return str(row["value"] or "")


def get_display_text() -> str:
    custom = get_stored_custom().strip()
    if custom:
        return custom
    return DEFAULT_KIOSK_NOTICE


def set_custom_message(text: str) -> None:
    body = text.strip()
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (KEY, body),
        )
