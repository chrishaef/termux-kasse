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
    from app.admin_auth import ensure_default_password

    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                pin_hash TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
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

            CREATE TABLE IF NOT EXISTS year_end_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                settlements_count INTEGER NOT NULL DEFAULT 0,
                settlements_sum_cents INTEGER NOT NULL DEFAULT 0,
                zip_filename TEXT NOT NULL,
                pdf_filename TEXT NOT NULL,
                xlsx_filename TEXT NOT NULL
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
        _migrate_schema(conn)
        ensure_default_password(conn)


def _migrate_products_remove_categories(conn: sqlite3.Connection) -> None:
    """Alte DBs: category_id entfernen, Tabelle product_categories löschen."""
    prows = conn.execute("PRAGMA table_info(products)").fetchall()
    if not prows:
        return
    pcols = {r[1] for r in prows}
    if "category_id" in pcols:
        try:
            conn.execute("ALTER TABLE products DROP COLUMN category_id")
        except sqlite3.OperationalError:
            conn.execute("PRAGMA foreign_keys=OFF")
            try:
                conn.executescript(
                    """
                    CREATE TABLE products__flat (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        price_cents INTEGER NOT NULL,
                        active INTEGER NOT NULL DEFAULT 1,
                        sort_order INTEGER NOT NULL DEFAULT 0
                    );
                    INSERT INTO products__flat (id, name, price_cents, active, sort_order)
                        SELECT id, name, price_cents, active,
                            COALESCE(sort_order, 0) FROM products;
                    DROP TABLE products;
                    ALTER TABLE products__flat RENAME TO products;
                    """
                )
            finally:
                conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("DROP TABLE IF EXISTS product_categories")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS year_end_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            settlements_count INTEGER NOT NULL DEFAULT 0,
            settlements_sum_cents INTEGER NOT NULL DEFAULT 0,
            zip_filename TEXT NOT NULL,
            pdf_filename TEXT NOT NULL,
            xlsx_filename TEXT NOT NULL
        );
        """
    )
    sinfo = conn.execute("PRAGMA table_info(settlements)").fetchall()
    if sinfo:
        cols = {r[1] for r in sinfo}
        if "received_confirmed" not in cols:
            conn.execute(
                "ALTER TABLE settlements ADD COLUMN received_confirmed INTEGER NOT NULL DEFAULT 1"
            )
    _migrate_sort_order_columns(conn)
    _migrate_products_remove_categories(conn)


def _migrate_sort_order_columns(conn: sqlite3.Connection) -> None:
    for table in ("user_groups", "users", "products"):
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not info:
            continue
        cols = {r[1] for r in info}
        if "sort_order" not in cols:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
            )
    _backfill_sort_orders(conn)


def _backfill_sort_orders(conn: sqlite3.Connection) -> None:
    """Eindeutige sort_order vergeben, solange MAX(sort_order)=0 (nach Migration)."""
    for table, order_sql in (
        ("user_groups", "SELECT id FROM user_groups ORDER BY name COLLATE NOCASE, id"),
        ("users", "SELECT id FROM users ORDER BY group_id, name COLLATE NOCASE, id"),
        ("products", "SELECT id FROM products ORDER BY name COLLATE NOCASE, id"),
    ):
        meta = conn.execute(
            f"SELECT COUNT(*) AS c, COALESCE(MAX(sort_order), 0) AS mx FROM {table}",
        ).fetchone()
        if not meta or int(meta["c"]) == 0 or int(meta["mx"]) > 0:
            continue
        rows = conn.execute(order_sql).fetchall()
        for i, r in enumerate(rows):
            conn.execute(
                f"UPDATE {table} SET sort_order = ? WHERE id = ?",
                ((i + 1) * 10, r[0]),
            )


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
    cur = conn.execute(sql, tuple(params))
    return cur.fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
    cur = conn.execute(sql, tuple(params))
    return cur.fetchall()
