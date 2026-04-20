from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase
from app.main import app


def test_kiosk_home() -> None:
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "k-tiles" in r.text or "k-empty" in r.text
        assert "kasse.css" in r.text
        assert "Top Ten" in r.text
        assert "Preisliste" in r.text


def test_kiosk_top_ten_shows_active_users() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        c.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        c.post("/admin/users", data={"name": "Ben", "group_id": str(gid)})
        c.post("/admin/products", data={"name": "Cola", "price_eur": "2.00"})
        with db.get_connection() as conn:
            users = conn.execute("SELECT id FROM users ORDER BY name").fetchall()
            uid_anna = int(users[0][0])
            uid_ben = int(users[1][0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid_anna, pid, "Cola (x1)", 200)
            add_purchase(conn, uid_ben, pid, "Cola (x1)", 200)
            add_purchase(conn, uid_ben, pid, "Cola (x1)", 200)
        r = c.get("/top-ten")
        assert r.status_code == 200
        assert "Top Ten" in r.text
        # Ben hat mehr Buchungen und sollte vor Anna erscheinen.
        assert r.text.find("Ben") < r.text.find("Anna")


def test_kiosk_preisliste_shows_products() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/products", data={"name": "Wasser", "price_eur": "1.20"})
        r = c.get("/preisliste")
        assert r.status_code == 200
        assert "Preisliste" in r.text
        assert "Wasser" in r.text


def test_kiosk_user_shows_credit_with_plus_and_green_class() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        c.post("/admin/users", data={"name": "Lea", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='Lea'").fetchone()[0])
            conn.execute(
                """
                INSERT INTO ledger_entries (user_id, product_id, description, amount_cents, created_at)
                VALUES (?, NULL, ?, ?, ?)
                """,
                (uid, "Admin-Guthaben", -500, "2026-01-01T10:00:00"),
            )
        r = c.get(f"/u/{uid}")
        assert r.status_code == 200
        assert "+5,00 €" in r.text
        assert "k-user-head__balance-value--credit" in r.text
