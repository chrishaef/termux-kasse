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
        WITH per_user AS (
            SELECT user_id, COALESCE(SUM(amount_cents), 0) AS bal
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
        )
        SELECT
            COALESCE(SUM(bal), 0) AS open_total,
            COALESCE(MAX(CASE WHEN bal > 0 THEN bal ELSE 0 END), 0) AS max_open
        FROM per_user
        """,
        (),
    )
    open_total = int(row_open["open_total"]) if row_open else 0
    max_user_open = int(row_open["max_open"]) if row_open else 0
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


def users_open_balance_gte_details(
    conn: sqlite3.Connection,
    min_cents: int,
) -> list[dict[str, Any]]:
    """Nutzer mit offenem Saldo >= min_cents inkl. Summen und letzter Abrechnung."""
    if min_cents <= 0:
        return []
    rows = db.fetch_all(
        conn,
        """
        SELECT
            g.name AS group_name,
            u.name AS user_name,
            COALESCE(o.open_balance_cents, 0) AS open_balance_cents,
            COALESCE(allb.all_bookings_cents, 0) AS all_bookings_cents,
            ls.last_settlement_at AS last_settlement_at
        FROM users u
        JOIN user_groups g ON g.id = u.group_id
        JOIN (
            SELECT user_id, SUM(amount_cents) AS open_balance_cents
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
            HAVING SUM(amount_cents) >= ?
        ) o ON o.user_id = u.id
        LEFT JOIN (
            SELECT user_id, SUM(amount_cents) AS all_bookings_cents
            FROM ledger_entries
            GROUP BY user_id
        ) allb ON allb.user_id = u.id
        LEFT JOIN (
            SELECT user_id, MAX(created_at) AS last_settlement_at
            FROM settlements
            GROUP BY user_id
        ) ls ON ls.user_id = u.id
        ORDER BY o.open_balance_cents DESC, u.name COLLATE NOCASE
        """,
        (min_cents,),
    )
    return [
        {
            "group_name": str(r["group_name"]),
            "user_name": str(r["user_name"]),
            "all_bookings_cents": int(r["all_bookings_cents"]),
            "open_balance_cents": int(r["open_balance_cents"]),
            "last_settlement_at": str(r["last_settlement_at"] or ""),
        }
        for r in rows
    ]


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


def period_user_stats(
    conn: sqlite3.Connection,
    period_start: str | None,
    period_end: str | None,
    group_id: int | None = None,
) -> list[sqlite3.Row]:
    sql = """
        SELECT
            g.name AS group_name,
            u.name AS user_name,
            COUNT(le.id) AS entries_count,
            COALESCE(SUM(le.amount_cents), 0) AS total_cents
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        WHERE 1=1
    """
    params: list[Any] = []
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    if group_id is not None:
        sql += " AND g.id = ?"
        params.append(group_id)
    sql += """
        GROUP BY u.id, g.id
        ORDER BY g.sort_order, g.name COLLATE NOCASE, u.sort_order, u.name COLLATE NOCASE
    """
    return db.fetch_all(conn, sql, params)


def period_user_toplist(
    conn: sqlite3.Connection,
    period_start: str | None,
    period_end: str | None,
    group_id: int | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            g.id AS group_id,
            g.name AS group_name,
            u.id AS user_id,
            u.name AS user_name,
            le.product_id,
            p.name AS product_name,
            le.description,
            le.amount_cents
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN products p ON p.id = le.product_id
        WHERE 1=1
    """
    params: list[Any] = []
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    if group_id is not None:
        sql += " AND g.id = ?"
        params.append(group_id)
    sql += " ORDER BY g.sort_order, g.name COLLATE NOCASE, u.sort_order, u.name COLLATE NOCASE"
    rows = db.fetch_all(conn, sql, params)

    per_user: dict[int, dict[str, Any]] = {}
    for r in rows:
        uid = int(r["user_id"])
        if uid not in per_user:
            per_user[uid] = {
                "group_name": str(r["group_name"]),
                "user_name": str(r["user_name"]),
                "entries_count": 0,
                "total_cents": 0,
                "_products": {},
            }
        item = per_user[uid]
        item["entries_count"] += 1
        item["total_cents"] += int(r["amount_cents"])
        label = str((r["product_name"] or "").strip() or (r["description"] or "").strip())
        pmap: dict[str, int] = item["_products"]
        pmap[label] = pmap.get(label, 0) + 1

    out: list[dict[str, Any]] = []
    for u in per_user.values():
        prods = sorted(u["_products"].items(), key=lambda x: (-x[1], x[0].casefold()))
        summary = ", ".join(f"{n}x {name}" for name, n in prods)
        out.append(
            {
                "group_name": u["group_name"],
                "user_name": u["user_name"],
                "entries_count": int(u["entries_count"]),
                "total_cents": int(u["total_cents"]),
                "purchases_summary": summary,
            }
        )
    out.sort(key=lambda x: (-int(x["total_cents"]), -int(x["entries_count"]), str(x["user_name"]).casefold()))
    return out


def open_balance_toplist(
    conn: sqlite3.Connection,
    period_start: str | None,
    period_end: str | None,
    group_id: int | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            g.name AS group_name,
            u.name AS user_name,
            COUNT(le.id) AS open_entries_count,
            COALESCE(SUM(le.amount_cents), 0) AS open_balance_cents
        FROM users u
        JOIN user_groups g ON g.id = u.group_id
        JOIN ledger_entries le ON le.user_id = u.id AND le.settlement_id IS NULL
        WHERE 1=1
    """
    params: list[Any] = []
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    if group_id is not None:
        sql += " AND g.id = ?"
        params.append(group_id)
    sql += """
        GROUP BY u.id, g.id
        HAVING COALESCE(SUM(le.amount_cents), 0) > 0
        ORDER BY COALESCE(SUM(le.amount_cents), 0) DESC, COUNT(le.id) DESC, u.name COLLATE NOCASE
    """
    rows = db.fetch_all(conn, sql, params)
    return [
        {
            "group_name": str(r["group_name"]),
            "user_name": str(r["user_name"]),
            "open_entries_count": int(r["open_entries_count"]),
            "open_balance_cents": int(r["open_balance_cents"]),
        }
        for r in rows
    ]


def period_product_stats(
    conn: sqlite3.Connection,
    period_start: str | None,
    period_end: str | None,
    group_id: int | None = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT le.product_id, p.name AS product_name, le.description, le.amount_cents
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN products p ON p.id = le.product_id
        WHERE 1=1
    """
    params: list[Any] = []
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    if group_id is not None:
        sql += " AND g.id = ?"
        params.append(group_id)
    sql += " ORDER BY datetime(le.created_at)"
    rows = db.fetch_all(conn, sql, params)
    return aggregate_ledger_lines(rows)


def top_ten_active_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return db.fetch_all(
        conn,
        """
        SELECT
            g.name AS group_name,
            u.name AS user_name,
            COUNT(le.id) AS entries_count,
            COALESCE(SUM(le.amount_cents), 0) AS total_cents
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        GROUP BY u.id, g.id
        ORDER BY entries_count DESC, total_cents DESC, u.name COLLATE NOCASE
        LIMIT 10
        """,
        (),
    )


def period_totals(
    conn: sqlite3.Connection,
    period_start: str | None,
    period_end: str | None,
    group_id: int | None = None,
) -> dict[str, int]:
    sql = """
        SELECT
            COUNT(*) AS entries_count,
            COUNT(DISTINCT user_id) AS users_count,
            COALESCE(SUM(amount_cents), 0) AS total_cents
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        WHERE 1=1
    """
    params: list[Any] = []
    if period_start:
        sql += " AND datetime(le.created_at) >= datetime(?)"
        params.append(period_start)
    if period_end:
        sql += " AND datetime(le.created_at) <= datetime(?)"
        params.append(period_end)
    if group_id is not None:
        sql += " AND u.group_id = ?"
        params.append(group_id)
    row = db.fetch_one(conn, sql, params)
    if not row:
        return {"entries_count": 0, "users_count": 0, "total_cents": 0}
    return {
        "entries_count": int(row["entries_count"]),
        "users_count": int(row["users_count"]),
        "total_cents": int(row["total_cents"]),
    }


def admin_exists(conn: sqlite3.Connection) -> bool:
    row = db.fetch_one(conn, "SELECT COUNT(*) AS c FROM admin_users", ())
    return bool(row and int(row["c"]) > 0)


def year_end_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Liest alle Kennzahlen für den Jahresabschluss-Bericht (vor Datenbereinigung)."""
    created_at = utc_now_iso()
    row_all = db.fetch_one(
        conn,
        "SELECT COUNT(*) AS c, COALESCE(SUM(amount_cents), 0) AS s FROM ledger_entries",
        (),
    )
    row_open = db.fetch_one(
        conn,
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(amount_cents), 0) AS s
        FROM ledger_entries
        WHERE settlement_id IS NULL
        """,
        (),
    )
    row_settled_lines = db.fetch_one(
        conn,
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(amount_cents), 0) AS s
        FROM ledger_entries
        WHERE settlement_id IS NOT NULL
        """,
        (),
    )
    row_settlements = db.fetch_one(
        conn,
        "SELECT COUNT(*) AS c, COALESCE(SUM(total_cents), 0) AS s FROM settlements",
        (),
    )
    users = db.fetch_all(
        conn,
        """
        SELECT u.id AS user_id, u.name AS user_name, g.name AS group_name,
            COALESCE(o.open_cents, 0) AS open_balance_cents,
            COALESCE(o.open_n, 0) AS open_entries_count,
            COALESCE(st.n, 0) AS settlements_count,
            COALESCE(st.sum_cents, 0) AS settlements_sum_cents,
            COALESCE(ua.all_n, 0) AS ledger_all_count,
            COALESCE(ua.all_sum, 0) AS ledger_all_sum_cents
        FROM users u
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN (
            SELECT user_id,
                SUM(amount_cents) AS open_cents,
                COUNT(*) AS open_n
            FROM ledger_entries
            WHERE settlement_id IS NULL
            GROUP BY user_id
        ) o ON o.user_id = u.id
        LEFT JOIN (
            SELECT user_id,
                COUNT(*) AS n,
                SUM(total_cents) AS sum_cents
            FROM settlements
            GROUP BY user_id
        ) st ON st.user_id = u.id
        LEFT JOIN (
            SELECT user_id,
                COUNT(*) AS all_n,
                SUM(amount_cents) AS all_sum
            FROM ledger_entries
            GROUP BY user_id
        ) ua ON ua.user_id = u.id
        ORDER BY g.sort_order, g.name COLLATE NOCASE, u.sort_order, u.name COLLATE NOCASE
        """,
        (),
    )
    user_rows = [dict(r) for r in users]
    user_stats_by_id = {int(u["user_id"]): dict(u) for u in user_rows}
    user_product_rows = db.fetch_all(
        conn,
        """
        SELECT
            u.id AS user_id,
            u.name AS user_name,
            g.name AS group_name,
            le.product_id,
            p.name AS product_name,
            le.description,
            COUNT(*) AS quantity
        FROM ledger_entries le
        JOIN users u ON u.id = le.user_id
        JOIN user_groups g ON g.id = u.group_id
        LEFT JOIN products p ON p.id = le.product_id
        GROUP BY u.id, g.id, le.product_id, p.name, le.description
        ORDER BY g.sort_order, g.name COLLATE NOCASE, u.sort_order, u.name COLLATE NOCASE
        """,
        (),
    )
    per_user_products: dict[int, dict[str, Any]] = {}
    for r in user_product_rows:
        uid = int(r["user_id"])
        if uid not in per_user_products:
            st = user_stats_by_id.get(uid, {})
            paid_cents = int(st.get("settlements_sum_cents", 0))
            open_cents = int(st.get("open_balance_cents", 0))
            per_user_products[uid] = {
                "user_name": str(r["user_name"]),
                "group_name": str(r["group_name"]),
                "entries_count": 0,
                "paid_cents": paid_cents,
                "open_cents": open_cents,
                "total_cents": paid_cents + open_cents,
                "items": [],
            }
        item = per_user_products[uid]
        qty = int(r["quantity"])
        item["entries_count"] += qty
        label = str((r["product_name"] or "").strip() or (r["description"] or "").strip() or "Unbekannt")
        item["items"].append({"label": label, "quantity": qty})

    user_product_tables: list[dict[str, Any]] = []
    for row in per_user_products.values():
        row["items"].sort(key=lambda x: (-int(x["quantity"]), str(x["label"]).casefold()))
        if int(row["entries_count"]) > 0:
            user_product_tables.append(row)
    user_product_tables.sort(
        key=lambda x: (-int(x["entries_count"]), str(x["user_name"]).casefold())
    )
    product_rows = period_product_stats(conn, None, None, None)
    return {
        "created_at_iso": created_at,
        "totals": {
            "ledger_entries_all": int(row_all["c"]) if row_all else 0,
            "ledger_sum_all_cents": int(row_all["s"]) if row_all else 0,
            "open_lines_count": int(row_open["c"]) if row_open else 0,
            "open_balance_net_cents": int(row_open["s"]) if row_open else 0,
            "settled_lines_count": int(row_settled_lines["c"]) if row_settled_lines else 0,
            "settled_lines_sum_cents": int(row_settled_lines["s"]) if row_settled_lines else 0,
            "settlements_count": int(row_settlements["c"]) if row_settlements else 0,
            "settlements_sum_cents": int(row_settlements["s"]) if row_settlements else 0,
            "users_count": len(user_rows),
        },
        "users": user_rows,
        "product_rows": product_rows,
        "user_product_tables": user_product_tables,
    }


def purge_settled_ledger_and_settlements(conn: sqlite3.Connection) -> None:
    """Jahresabschluss: abgeschlossene Abrechnungen und zugehörige Buchungszeilen.

    Offene Buchungen (settlement_id IS NULL) und Kontostände bleiben erhalten.
    """
    conn.execute("DELETE FROM ledger_entries WHERE settlement_id IS NOT NULL")
    conn.execute("DELETE FROM settlements")


def purge_ledger_and_settlements(conn: sqlite3.Connection) -> None:
    """Vollständiger Reset: alle Buchungen und Abrechnungen (Kontostände werden 0).

    Stammdaten (Nutzer, Gruppen, Artikel) bleiben unverändert. Nur für Backup-Daten-Reset.
    """
    conn.execute("DELETE FROM ledger_entries")
    conn.execute("DELETE FROM settlements")
