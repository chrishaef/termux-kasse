"""Gemeinsame Sortier-Logik für Admin-Listen (Nutzergruppen, Nutzer, Artikel)."""

from __future__ import annotations

import sqlite3
from typing import Literal

from app import db

Direction = Literal["up", "down"]
_ALLOWED = frozenset({"user_groups", "users", "products"})


def next_sort_order(conn: sqlite3.Connection, table: str) -> int:
    if table not in _ALLOWED:
        raise ValueError(table)
    row = db.fetch_one(conn, f"SELECT COALESCE(MAX(sort_order), 0) AS m FROM {table}", ())
    return int(row["m"]) + 10 if row else 10


def swap_sort_order(
    conn: sqlite3.Connection,
    table: str,
    row_id: int,
    direction: Direction,
) -> None:
    if table not in _ALLOWED:
        raise ValueError(table)
    if direction not in ("up", "down"):
        raise ValueError(direction)
    rows = db.fetch_all(
        conn,
        f"SELECT id, sort_order FROM {table} ORDER BY sort_order, id",
        (),
    )
    if not rows:
        return
    ids = [int(r["id"]) for r in rows]
    if row_id not in ids:
        return
    idx = ids.index(row_id)
    j = idx - 1 if direction == "up" else idx + 1
    if j < 0 or j >= len(ids):
        return
    id_a, id_b = ids[idx], ids[j]
    sa = db.fetch_one(conn, f"SELECT sort_order FROM {table} WHERE id = ?", (id_a,))
    sb = db.fetch_one(conn, f"SELECT sort_order FROM {table} WHERE id = ?", (id_b,))
    if not sa or not sb:
        return
    conn.execute(
        f"UPDATE {table} SET sort_order = ? WHERE id = ?",
        (int(sb["sort_order"]), id_a),
    )
    conn.execute(
        f"UPDATE {table} SET sort_order = ? WHERE id = ?",
        (int(sa["sort_order"]), id_b),
    )


def next_user_sort_order_in_group(conn: sqlite3.Connection, group_id: int) -> int:
    row = db.fetch_one(
        conn,
        "SELECT COALESCE(MAX(sort_order), 0) AS m FROM users WHERE group_id = ?",
        (group_id,),
    )
    return int(row["m"]) + 10 if row else 10


def swap_user_sort_in_group(
    conn: sqlite3.Connection,
    user_id: int,
    direction: Direction,
) -> None:
    g = db.fetch_one(conn, "SELECT group_id FROM users WHERE id = ?", (user_id,))
    if not g:
        return
    gid = int(g["group_id"])
    rows = db.fetch_all(
        conn,
        """
        SELECT id, sort_order FROM users
        WHERE group_id = ?
        ORDER BY sort_order, id
        """,
        (gid,),
    )
    if not rows:
        return
    ids = [int(r["id"]) for r in rows]
    if user_id not in ids:
        return
    idx = ids.index(user_id)
    j = idx - 1 if direction == "up" else idx + 1
    if j < 0 or j >= len(ids):
        return
    id_a, id_b = ids[idx], ids[j]
    sa = db.fetch_one(conn, "SELECT sort_order FROM users WHERE id = ?", (id_a,))
    sb = db.fetch_one(conn, "SELECT sort_order FROM users WHERE id = ?", (id_b,))
    if not sa or not sb:
        return
    conn.execute(
        "UPDATE users SET sort_order = ? WHERE id = ?",
        (int(sb["sort_order"]), id_a),
    )
    conn.execute(
        "UPDATE users SET sort_order = ? WHERE id = ?",
        (int(sa["sort_order"]), id_b),
    )
