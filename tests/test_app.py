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


def test_kiosk_top_ten_shows_active_users() -> None:
    with TestClient(app) as c:
        c.post(
            "/admin/setup",
            data={"username": "adm", "password": "pw12345", "password2": "pw12345"},
            follow_redirects=False,
        )
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
