import sqlite3
from contextlib import contextmanager
from typing import Generator, Iterable

from app.config import data_dir, db_path


def connect() -> sqlite3.Connection:
    data_dir().mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                pin_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS product_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES product_categories(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS settlements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                total_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT,
                period_start TEXT,
                period_end TEXT
            );

            CREATE TABLE IF NOT EXISTS ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                description TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                settlement_id INTEGER REFERENCES settlements(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_ledger_user_open
                ON ledger_entries(user_id) WHERE settlement_id IS NULL;
            CREATE INDEX IF NOT EXISTS idx_ledger_settlement
                ON ledger_entries(settlement_id);
            """
        )


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
    cur = conn.execute(sql, tuple(params))
    return cur.fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    cur = conn.execute(sql, tuple(params))
    return cur.fetchall()
