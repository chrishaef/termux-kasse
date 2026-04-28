"""Schwellenwerte für offene Ausstände (Kiosk-Hinweise, Admin-Warnung)."""

from __future__ import annotations

import sqlite3

from app import db

KEY_T1 = "debt_threshold_1_cents"
KEY_T2 = "debt_threshold_2_cents"
KEY_T3 = "debt_threshold_3_cents"
KEY_D1 = "debt_age_threshold_1_days"
KEY_D2 = "debt_age_threshold_2_days"
KEY_D3 = "debt_age_threshold_3_days"
KEY_M1 = "debt_threshold_1_message"
KEY_M2 = "debt_threshold_2_message"
KEY_M3 = "debt_threshold_3_message"
KEY_V1 = "debt_warn_volume_1_percent"
KEY_V2 = "debt_warn_volume_2_percent"
KEY_V3 = "debt_warn_volume_3_percent"

# Standard: 5 € / 15 € / 30 € offener Saldo (intern positiv = Schuld)
DEFAULT_T1 = 500
DEFAULT_T2 = 1500
DEFAULT_T3 = 3000
DEFAULT_D1 = 7
DEFAULT_D2 = 21
DEFAULT_D3 = 45
DEFAULT_M1 = "NaNaNa - wird wohl zeit zu zahlen"
DEFAULT_M2 = "Die Kasse knurrt: Hoeherer Ausstand - bald mal zahlen ?"
DEFAULT_M3 = "Die Kasse wird klamm: ZAHLE ZAHLEN ZAHLEN!!!"
DEFAULT_V1 = 75
DEFAULT_V2 = 85
DEFAULT_V3 = 95


def _normalize_triple(t1: int, t2: int, t3: int) -> tuple[int, int, int]:
    a, b, c = sorted((max(1, int(t1)), max(1, int(t2)), max(1, int(t3))))
    b = max(b, a + 1)
    c = max(c, b + 1)
    return (a, b, c)


def _normalize_volume_percent(v: int) -> int:
    return max(0, min(100, int(v)))


def _read_cents(conn: sqlite3.Connection, key: str) -> int | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None or str(row["value"]).strip() == "":
        return None
    try:
        return int(str(row["value"]).strip())
    except ValueError:
        return None


def _read_text(conn: sqlite3.Connection, key: str) -> str | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (key,))
    if not row or row["value"] is None:
        return None
    val = str(row["value"]).strip()
    return val if val else None


def get_thresholds(conn: sqlite3.Connection) -> tuple[int, int, int]:
    """Drei aufsteigende Schwellen in Cent (Stufe 1 &lt; Stufe 2 &lt; Stufe 3)."""
    a, b, c = (_read_cents(conn, KEY_T1), _read_cents(conn, KEY_T2), _read_cents(conn, KEY_T3))
    if a is None or b is None or c is None:
        return _normalize_triple(DEFAULT_T1, DEFAULT_T2, DEFAULT_T3)
    return _normalize_triple(a, b, c)


def get_threshold_messages(conn: sqlite3.Connection) -> tuple[str, str, str]:
    m1 = _read_text(conn, KEY_M1) or DEFAULT_M1
    m2 = _read_text(conn, KEY_M2) or DEFAULT_M2
    m3 = _read_text(conn, KEY_M3) or DEFAULT_M3
    return (m1, m2, m3)


def get_warn_volumes_percent(conn: sqlite3.Connection) -> tuple[int, int, int]:
    v1 = _read_cents(conn, KEY_V1)
    v2 = _read_cents(conn, KEY_V2)
    v3 = _read_cents(conn, KEY_V3)
    return (
        _normalize_volume_percent(DEFAULT_V1 if v1 is None else v1),
        _normalize_volume_percent(DEFAULT_V2 if v2 is None else v2),
        _normalize_volume_percent(DEFAULT_V3 if v3 is None else v3),
    )


def get_age_thresholds(conn: sqlite3.Connection) -> tuple[int, int, int]:
    d1, d2, d3 = (_read_cents(conn, KEY_D1), _read_cents(conn, KEY_D2), _read_cents(conn, KEY_D3))
    if d1 is None or d2 is None or d3 is None:
        return _normalize_triple(DEFAULT_D1, DEFAULT_D2, DEFAULT_D3)
    return _normalize_triple(d1, d2, d3)


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


def save_age_thresholds_days(conn: sqlite3.Connection, d1: int, d2: int, d3: int) -> tuple[int, int, int]:
    a1, a2, a3 = _normalize_triple(d1, d2, d3)
    for key, val in ((KEY_D1, a1), (KEY_D2, a2), (KEY_D3, a3)):
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(val)),
        )
    return (a1, a2, a3)


def save_threshold_messages(
    conn: sqlite3.Connection,
    m1: str,
    m2: str,
    m3: str,
) -> tuple[str, str, str]:
    out = (
        (m1 or "").strip() or DEFAULT_M1,
        (m2 or "").strip() or DEFAULT_M2,
        (m3 or "").strip() or DEFAULT_M3,
    )
    for key, val in ((KEY_M1, out[0]), (KEY_M2, out[1]), (KEY_M3, out[2])):
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, val),
        )
    return out


def save_warn_volumes_percent(
    conn: sqlite3.Connection,
    v1: int,
    v2: int,
    v3: int,
) -> tuple[int, int, int]:
    out = (
        _normalize_volume_percent(v1),
        _normalize_volume_percent(v2),
        _normalize_volume_percent(v3),
    )
    for key, val in ((KEY_V1, out[0]), (KEY_V2, out[1]), (KEY_V3, out[2])):
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(val)),
        )
    return out


def _level_from_value(value: int, t1: int, t2: int, t3: int) -> int:
    v = max(0, int(value))
    if v < t1:
        return 0
    if v < t2:
        return 1
    if v < t3:
        return 2
    return 3


def reminder_level(
    open_balance_cents: int,
    t1: int,
    t2: int,
    t3: int,
    oldest_open_days: int | None = None,
    d1: int | None = None,
    d2: int | None = None,
    d3: int | None = None,
) -> int:
    """0 = unter Stufe 1, 1 = Stufe 1–2 (Erinnerung), 2 = Stufe 2–3 (dringlicher), 3 = ab Stufe 3 (Admin + Kiosk)."""
    level_amount = _level_from_value(open_balance_cents, t1, t2, t3)
    if oldest_open_days is None or d1 is None or d2 is None or d3 is None:
        return level_amount
    level_age = _level_from_value(oldest_open_days, d1, d2, d3)
    return max(level_amount, level_age)
