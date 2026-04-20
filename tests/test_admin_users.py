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
        assert "Offener Saldo" in r.text
        assert "2,00 €" in r.text
        assert "<tfoot>" in r.text
        assert "Summe" in r.text
        assert "4,00 €" in r.text


def test_admin_user_edit_can_adjust_balance_and_show_stats() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='Anna'").fetchone()[0])

        edit_get = client.get(f"/admin/users/{uid}/edit")
        assert edit_get.status_code == 200
        assert "Statistik" in edit_get.text
        assert "Aktueller Kassenstand" in edit_get.text
        assert "Nutzer löschen" in edit_get.text
        assert f"/admin/users/{uid}/delete" in edit_get.text

        edit_post = client.post(
            f"/admin/users/{uid}/edit",
            data={"name": "Anna Neu", "group_id": str(gid), "balance_eur": "-12.50"},
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
            assert int(bal) == 1250
