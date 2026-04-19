"""Schwellenwerte für offene Ausstände (Kiosk-Hinweise, Admin-Warnung)."""

from __future__ import annotations

import sqlite3

from app import db

KEY_T1 = "debt_threshold_1_cents"
KEY_T2 = "debt_threshold_2_cents"
KEY_T3 = "debt_threshold_3_cents"

# Standard: 5 € / 15 € / 30 € offener Saldo (intern positiv = Schuld)
DEFAULT_T1 = 500
DEFAULT_T2 = 1500
DEFAULT_T3 = 3000


def _normalize_triple(t1: int, t2: int, t3: int) -> tuple[int, int, int]:
    a, b, c = sorted((max(1, int(t1)), max(1, int(t2)), max(1, int(t3))))
    b = max(b, a + 1)
    c = max(c, b + 1)
    return (a, b, c)


def _read_cents(conn: sqlite3.Connection, key: str) -> int | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None or str(row["value"]).strip() == "":
        return None
    try:
        return int(str(row["value"]).strip())
    except ValueError:
        return None


def get_thresholds(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Drei aufsteigende Schwellen in Cent (Stufe 1 &lt; Stufe 2 &lt; Stufe 3)."""
    a, b, c = (_read_cents(conn, KEY_T1), _read_cents(conn, KEY_T2), _read_cents(conn, KEY_T3))
    if a is None or b is None or c is None:
        return _normalize_triple(DEFAULT_T1, DEFAULT_T2, DEFAULT_T3)
    return _normalize_triple(a, b, c)


def save_thresholds_cents(conn: sqlite3.Connection, a: int, b: int, c: int) -> tuple[int, int, int]:
    t1, t2, t3 = _normalize_triple(a, b, c)
    for key, val in ((KEY_T1, t1), (KEY_T2, t2), (KEY_T3, t3)):
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(val)),
        )
    return (t1, t2, t3)


def reminder_level(open_balance_cents: int, t1: int, t2: int, t3: int) -> int:
    """0 = unter Stufe 1, 1 = Stufe 1–2 (Erinnerung), 2 = Stufe 2–3 (dringlicher), 3 = ab Stufe 3 (Admin + Kiosk)."""
    owed = max(0, int(open_balance_cents))
    if owed < t1:
        return 0
    if owed < t2:
        return 1
    if owed < t3:
        return 2
    return 3
