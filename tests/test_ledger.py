from app import db
from app.db import init_db
from app.ledger_service import (
    add_purchase,
    aggregate_ledger_lines,
    create_settlement_for_user,
    finance_overview,
    open_ledger_for_user,
    settlement_count_for_user,
    total_previously_settled_cents,
    user_balance_cents,
)


def test_balance_and_settlement() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'Anna')", (gid,))
        uid = conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute(
            "INSERT INTO products (name, price_cents, active) VALUES ('Riegel', 80, 1)",
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


def test_previously_settled_totals_and_received_flag() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'Carl')", (gid,))
        uid = conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute(
            "INSERT INTO products (name, price_cents, active) VALUES ('Chip', 50, 1)",
        )
        pid = conn.execute("SELECT id FROM products").fetchone()[0]
        add_purchase(conn, uid, pid, "Chip (x1)", 50)
        add_purchase(conn, uid, pid, "Chip (x1)", 50)
        assert total_previously_settled_cents(conn, uid) == 0
        assert settlement_count_for_user(conn, uid) == 0
        sid = create_settlement_for_user(conn, uid, received_confirmed=1)
        assert sid is not None
        assert total_previously_settled_cents(conn, uid) == 100
        assert settlement_count_for_user(conn, uid) == 1
        row = conn.execute(
            "SELECT received_confirmed FROM settlements WHERE id = ?", (sid,)
        ).fetchone()
        assert int(row[0]) == 1

        add_purchase(conn, uid, pid, "Chip (x1)", 50)
        sid2 = create_settlement_for_user(conn, uid, received_confirmed=0)
        assert sid2 is not None
        row2 = conn.execute(
            "SELECT received_confirmed FROM settlements WHERE id = ?", (sid2,)
        ).fetchone()
        assert int(row2[0]) == 0
        assert total_previously_settled_cents(conn, uid) == 150


def test_finance_overview() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'A')", (gid,))
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'B')", (gid,))
        uid_a = conn.execute("SELECT id FROM users WHERE name='A'").fetchone()[0]
        uid_b = conn.execute("SELECT id FROM users WHERE name='B'").fetchone()[0]
        conn.execute(
            "INSERT INTO products (name, price_cents, active) VALUES ('P', 100, 1)",
        )
        pid = conn.execute("SELECT id FROM products").fetchone()[0]
        add_purchase(conn, uid_a, pid, "x", 300)
        add_purchase(conn, uid_b, pid, "x", 100)
        fo = finance_overview(conn)
        assert fo["open_total_cents"] == 400
        assert fo["max_user_open_cents"] == 300
        assert fo["settled_total_cents"] == 0
        create_settlement_for_user(conn, uid_a)
        fo2 = finance_overview(conn)
        assert fo2["open_total_cents"] == 100
        assert fo2["max_user_open_cents"] == 100
        assert fo2["settled_total_cents"] == 300


def test_finance_overview_ignores_user_credit_balances() -> None:
    init_db()
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES ('G1')")
        gid = conn.execute("SELECT id FROM user_groups").fetchone()[0]
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'A')", (gid,))
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, 'B')", (gid,))
        uid_a = conn.execute("SELECT id FROM users WHERE name='A'").fetchone()[0]
        uid_b = conn.execute("SELECT id FROM users WHERE name='B'").fetchone()[0]

        conn.execute(
            """
            INSERT INTO ledger_entries (user_id, product_id, description, amount_cents, created_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (uid_a, "Debt", 500, "2026-01-01T10:00:00"),
        )
        conn.execute(
            """
            INSERT INTO ledger_entries (user_id, product_id, description, amount_cents, created_at)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (uid_b, "Credit", -700, "2026-01-01T10:00:00"),
        )

        fo = finance_overview(conn)
        assert fo["open_total_cents"] == -200
        assert fo["max_user_open_cents"] == 500


def test_aggregate_ledger_lines_merges_same_product_and_amount() -> None:
    lines = [
        {
            "product_id": 1,
            "product_name": "Riegel",
            "description": "Riegel (x1)",
            "amount_cents": 80,
        },
        {
            "product_id": 1,
            "product_name": "Riegel",
            "description": "Riegel (x1)",
            "amount_cents": 80,
        },
        {
            "product_id": 2,
            "product_name": "Cola",
            "description": "Cola (x1)",
            "amount_cents": 200,
        },
    ]
    agg = aggregate_ledger_lines(lines)  # type: ignore[arg-type]
    assert len(agg) == 2
    by_label = {a["label"]: a for a in agg}
    assert by_label["Cola"]["quantity"] == 1
    assert by_label["Riegel"]["quantity"] == 2
    assert by_label["Riegel"]["total_cents"] == 160
