from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase
from app.main import app


def test_admin_users_overview_shows_balances_and_totals() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        client.post("/admin/users", data={"name": "Ben", "group_id": str(gid)})
        with db.get_connection() as conn:
            uids = [int(r[0]) for r in conn.execute("SELECT id FROM users ORDER BY name").fetchall()]
        client.post(
            "/admin/products",
            data={"name": "Cola", "price_eur": "2.00"},
        )
        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uids[0], pid, "Cola (x1)", 200)
            add_purchase(conn, uids[1], pid, "Cola (x1)", 200)

        r = client.get("/admin/users")
        assert r.status_code == 200
        assert "Nutzer" in r.text
        assert "admin-user-overview" in r.text
        assert "admin-action-btn" in r.text
        assert "Saldo" in r.text
        assert "2,00 €" in r.text
        assert "<tfoot>" in r.text
        assert "Summe" in r.text
        assert "4,00 €" in r.text


def test_admin_users_can_be_filtered_by_group() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        client.post("/admin/groups", data={"name": "G2"})
        with db.get_connection() as conn:
            groups = conn.execute("SELECT id, name FROM user_groups ORDER BY name").fetchall()
            g1 = next(int(r[0]) for r in groups if str(r[1]) == "G1")
            g2 = next(int(r[0]) for r in groups if str(r[1]) == "G2")
        client.post("/admin/users", data={"name": "Anna", "group_id": str(g1)})
        client.post("/admin/users", data={"name": "Ben", "group_id": str(g2)})

        r = client.get(f"/admin/users?group_id={g1}")
        assert r.status_code == 200
        assert "Anna" in r.text
        assert "Ben" not in r.text
        assert f'<option value="{g1}" selected>' in r.text


def test_admin_user_edit_name_and_group_keeps_ledger() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='Anna'").fetchone()[0])
        client.post("/admin/products", data={"name": "Cola", "price_eur": "1.00"})
        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "Cola", 100)

        edit_get = client.get(f"/admin/users/{uid}/edit")
        assert edit_get.status_code == 200
        assert "Statistik" in edit_get.text
        assert "Nutzer löschen" in edit_get.text
        assert "balance_eur" not in edit_get.text

        edit_post = client.post(
            f"/admin/users/{uid}/edit",
            data={"name": "Anna Neu", "group_id": str(gid)},
            follow_redirects=False,
        )
        assert edit_post.status_code == 303
        assert edit_post.headers["location"] == "/admin/users"

        with db.get_connection() as conn:
            row = conn.execute("SELECT name FROM users WHERE id = ?", (uid,)).fetchone()
            assert row[0] == "Anna Neu"
            bal = conn.execute(
                "SELECT COALESCE(SUM(amount_cents), 0) FROM ledger_entries WHERE user_id = ? AND settlement_id IS NULL",
                (uid,),
            ).fetchone()[0]
            assert int(bal) == 100


def test_over_limit_users_page_lists_affected_users() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES ('debt_threshold_3_cents', '300')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES ('debt_threshold_1_cents', '100')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
            conn.execute(
                """
                INSERT INTO app_settings (key, value) VALUES ('debt_threshold_2_cents', '200')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
        client.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='Anna'").fetchone()[0])
        client.post("/admin/products", data={"name": "Cola", "price_eur": "2.00"})
        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "Cola", 200)
            add_purchase(conn, uid, pid, "Cola", 200)
            conn.execute(
                "INSERT INTO settlements (user_id, total_cents, created_at, note, period_start, period_end, received_confirmed) VALUES (?, ?, ?, ?, ?, ?, 1)",
                (uid, 400, "2026-04-21T10:00:00", None, None, None),
            )

        r = client.get("/admin/users/over-limit")
        assert r.status_code == 200
        assert "Nutzer über Warnstufe 3" in r.text
        assert "Anna" in r.text
        assert "4,00 €" in r.text
        assert "21.04.2026" in r.text
