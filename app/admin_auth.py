"""Admin-Zugang: Master-Passwort (Datei) und regulaeres Passwort (DB)."""

from __future__ import annotations

import hmac
import sqlite3

from app import db
from app.auth import hash_password, verify_password
from app.config import read_master_password

ADMIN_PASSWORD_HASH_KEY = "admin_password_hash"
DEFAULT_ADMIN_PASSWORD = "admin"


def _get_stored_hash(conn: sqlite3.Connection) -> str | None:
    row = db.fetch_one(
        conn,
        "SELECT value FROM app_settings WHERE key = ?",
        (ADMIN_PASSWORD_HASH_KEY,),
    )
    if not row:
        return None
    value = str(row["value"] or "").strip()
    return value or None


def _store_hash(conn: sqlite3.Connection, new_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (ADMIN_PASSWORD_HASH_KEY, new_hash),
    )


def ensure_default_password(conn: sqlite3.Connection) -> None:
    """Erste Installation: Standardpasswort 'admin' setzen, falls noch keins hinterlegt ist.

    Hat eine bestehende Installation noch einen alten Admin in `admin_users`,
    wird dessen Hash uebernommen, damit niemand ausgesperrt wird.
    """
    if _get_stored_hash(conn):
        return

    legacy_hash: str | None = None
    try:
        row = db.fetch_one(
            conn,
            "SELECT password_hash FROM admin_users ORDER BY id DESC LIMIT 1",
        )
        if row and str(row["password_hash"] or "").strip():
            legacy_hash = str(row["password_hash"]).strip()
    except sqlite3.Error:
        legacy_hash = None

    if legacy_hash:
        _store_hash(conn, legacy_hash)
    else:
        _store_hash(conn, hash_password(DEFAULT_ADMIN_PASSWORD))


def is_master_password(password: str) -> bool:
    master = read_master_password()
    if master is None or not password:
        return False
    return hmac.compare_digest(master, password)


def verify_regular_password(conn: sqlite3.Connection, password: str) -> bool:
    if not password:
        return False
    stored = _get_stored_hash(conn)
    if not stored:
        return False
    return verify_password(password, stored)


def verify_admin_password(conn: sqlite3.Connection, password: str) -> tuple[bool, bool]:
    """Prueft Passwort gegen Master- und DB-Passwort.

    Rueckgabe: (ok, is_master).
    """
    if is_master_password(password):
        return (True, True)
    if verify_regular_password(conn, password):
        return (True, False)
    return (False, False)


def set_regular_password(conn: sqlite3.Connection, new_password: str) -> None:
    _store_hash(conn, hash_password(new_password))
