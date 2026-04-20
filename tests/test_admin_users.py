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
