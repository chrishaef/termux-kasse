from app import db
from app.db import init_db
from app.ledger_service import (
    add_purchase,
    create_settlement_for_user,
    open_ledger_for_user,
    user_balance_cents,
)


def test_balance_and_settlement() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'Anna')", (gid,))
        uid = conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute("INSERT INTO product_categories (name, sort_order) VALUES ('Snacks', 0)")
        cid = conn.execute("SELECT id FROM product_categories").fetchone()[0]
        conn.execute(
            "INSERT INTO products (category_id, name, price_cents, active) VALUES (?, 'Riegel', 80, 1)",
            (cid,),
        )
        pid = conn.execute("SELECT id FROM products").fetchone()[0]
        add_purchase(conn, uid, pid, "Riegel (x1)", 80)
        add_purchase(conn, uid, pid, "Riegel (x1)", 80)
        assert user_balance_cents(conn, uid) == 160
        open_lines = open_ledger_for_user(conn, uid)
        assert len(open_lines) == 2
        sid = create_settlement_for_user(conn, uid, note="Januar")
        assert sid is not None
        assert user_balance_cents(conn, uid) == 0
        assert open_ledger_for_user(conn, uid) == []
        lines = conn.execute(
            "SELECT settlement_id FROM ledger_entries WHERE user_id = ?", (uid,)
        ).fetchall()
        assert all(r[0] == sid for r in lines)


def test_settlement_empty_returns_none() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'Bob')", (gid,))
        uid = conn.execute("SELECT id FROM users").fetchone()[0]
        assert create_settlement_for_user(conn, uid) is None
