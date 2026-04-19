from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from app import db


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def users_admin_overview(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Alle Nutzer mit Gruppe und Finanz-Kennzahlen für die Admin-Übersicht."""
    return db.fetch_all(
        conn,
        """
        SELECT u.id, u.name, g.id AS group_id, g.name AS group_name,
            COALESCE(lo.open_cents, 0) AS open_balance_cents,
            COALESCE(lo.open_n, 0) AS open_entries_count,
            COALESCE(st.settled_cents, 0) AS settled_total_cents,
            COALESCE(st.settlements_n, 0) AS settlements_count
        FROM users u
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN (
            SELECT user_id,
                SUM(amount_cents) AS open_cents,
                COUNT(*) AS open_n
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
        ) lo ON lo.user_id = u.id
        LEFT JOIN (
            SELECT user_id,
                SUM(total_cents) AS settled_cents,
                COUNT(*) AS settlements_n
            FROM settlements
            GROUP BY user_id
        ) st ON st.user_id = u.id
        ORDER BY g.sort_order, g.name COLLATE NOCASE, u.sort_order, u.name COLLATE NOCASE
        """,
        (),
    )


def aggregate_ledger_lines(
    lines: Sequence[sqlite3.Row | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Mehrere gleiche Buchungen (z. B. gleicher Artikel & gleicher Einzelbetrag) zu einer Zeile."""
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in lines:
        amt = int(r["amount_cents"])
        pid = r["product_id"] if r["product_id"] is not None else None
        if pid is not None:
            key = ("p", int(pid), amt)
            pname = (r["product_name"] or "").strip()
            label = pname or str(r["description"] or "").strip()
        else:
            desc = str(r["description"] or "").strip()
            key = ("m", desc, amt)
            label = desc
        if key not in groups:
            groups[key] = {
                "quantity": 0,
                "label": label,
                "unit_cents": amt,
                "total_cents": 0,
            }
        g = groups[key]
        g["quantity"] += 1
        g["total_cents"] += amt
    out = list(groups.values())
    out.sort(key=lambda x: (str(x["label"]).casefold(), int(x["unit_cents"])))
    return out


def finance_overview(conn: sqlite3.Connection) -> dict[str, int]:
    """Kennzahlen für die Admin-Übersicht: offene Posten gesamt, höchster Nutzer-Saldo, Summe abgeschlossener Abrechnungen."""
    row_open = db.fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS s
        FROM ledger_entries
        WHERE settlement_id IS NULL
        """,
        (),
    )
    open_total = int(row_open["s"]) if row_open else 0
    row_max = db.fetch_one(
        conn,
        """
        SELECT COALESCE(MAX(per_user), 0) AS m
        FROM (
            SELECT COALESCE(SUM(amount_cents), 0) AS per_user
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
        ) AS t
        """,
        (),
    )
    max_user_open = int(row_max["m"]) if row_max else 0
    row_settled = db.fetch_one(
        conn,
        "SELECT COALESCE(SUM(total_cents), 0) AS s FROM settlements",
        (),
    )
    settled_total = int(row_settled["s"]) if row_settled else 0
    return {
        "open_total_cents": open_total,
        "max_user_open_cents": max_user_open,
        "settled_total_cents": settled_total,
    }


def count_users_open_balance_gte(conn: sqlite3.Connection, min_cents: int) -> int:
    """Anzahl Nutzer, deren offener Saldo (Summe offener Buchungen) >= min_cents ist."""
    if min_cents <= 0:
        return 0
    row = db.fetch_one(
        conn,
        """
        SELECT COUNT(*) AS c FROM (
            SELECT user_id
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
            HAVING SUM(amount_cents) >= ?
        ) AS t
        """,
        (min_cents,),
    )
    return int(row["c"]) if row else 0


def user_balance_cents(conn: sqlite3.Connection, user_id: int) -> int:
    row = db.fetch_one(
        conn,
        """
        SELECT COALESCE(SUM(amount_cents), 0) AS b
        FROM ledger_entries
        WHERE user_id = ? AND settlement_id IS NULL
        """,
        (user_id,),
    )
    return int(row["b"]) if row else 0


def total_previously_settled_cents(conn: sqlite3.Connection, user_id: int) -> int:
    row = db.fetch_one(
        conn,
        "SELECT COALESCE(SUM(total_cents), 0) AS s FROM settlements WHERE user_id = ?",
        (user_id,),
    )
    return int(row["s"]) if row else 0


def settlement_count_for_user(conn: sqlite3.Connection, user_id: int) -> int:
    row = db.fetch_one(
        conn,
        "SELECT COUNT(*) AS c FROM settlements WHERE user_id = ?",
        (user_id,),
    )
    return int(row["c"]) if row else 0


def last_settlement(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return db.fetch_one(
        conn,
        """
        SELECT id, total_cents, created_at, note
        FROM settlements
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 1
        """,
        (user_id,),
    )


def open_ledger_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT le.*, p.name AS product_name
        FROM ledger_entries le
        LEFT JOIN products p ON p.id = le.product_id
        WHERE le.user_id = ? AND le.settlement_id IS NULL
    """
    params: list = [user_id]
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    sql += " ORDER BY datetime(le.created_at)"
    return db.fetch_all(conn, sql, params)


def add_purchase(
    conn: sqlite3.Connection,
    user_id: int,
    product_id: int,
    description: str,
    amount_cents: int,
) -> None:
    conn.execute(
        """
        INSERT INTO ledger_entries (user_id, product_id, description, amount_cents, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, product_id, description, amount_cents, utc_now_iso()),
    )


def create_settlement_for_user(
    conn: sqlite3.Connection,
    user_id: int,
    note: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    *,
    received_confirmed: int = 1,
) -> int | None:
    lines = open_ledger_for_user(conn, user_id, period_start, period_end)
    if not lines:
        return None
    total = sum(int(r["amount_cents"]) for r in lines)
    created = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO settlements (user_id, total_cents, created_at, note, period_start, period_end, received_confirmed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, total, created, note, period_start, period_end, 1 if received_confirmed else 0),
    )
    sid = int(cur.lastrowid)
    ids = [int(r["id"]) for r in lines]
    conn.executemany(
        "UPDATE ledger_entries SET settlement_id = ? WHERE id = ?",
        [(sid, i) for i in ids],
    )
    return sid


def settlement_lines(conn: sqlite3.Connection, settlement_id: int) -> list[sqlite3.Row]:
    return db.fetch_all(
        conn,
        """
        SELECT le.*, u.name AS user_name, g.name AS group_name, p.name AS product_name
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN products p ON p.id = le.product_id
        WHERE le.settlement_id = ?
        ORDER BY datetime(le.created_at)
        """,
        (settlement_id,),
    )


def settlement_header(conn: sqlite3.Connection, settlement_id: int) -> sqlite3.Row | None:
    return db.fetch_one(
        conn,
        """
        SELECT s.*, u.name AS user_name, g.name AS group_name
        FROM settlements s
        JOIN users u ON u.id = s.user_id
        JOIN user_groups g ON g.id = u.group_id
        WHERE s.id = ?
        """,
        (settlement_id,),
    )


def admin_exists(conn: sqlite3.Connection) -> bool:
    row = db.fetch_one(conn, "SELECT COUNT(*) AS c FROM admin_users", ())
    return bool(row and int(row["c"]) > 0)
