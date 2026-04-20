from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app import debt_thresholds
from app.ledger_service import add_purchase, count_users_open_balance_gte
from app.main import app


def test_reminder_level_bands() -> None:
    t1, t2, t3 = 100, 200, 300
    assert debt_thresholds.reminder_level(0, t1, t2, t3) == 0
    assert debt_thresholds.reminder_level(50, t1, t2, t3) == 0
    assert debt_thresholds.reminder_level(100, t1, t2, t3) == 1
    assert debt_thresholds.reminder_level(199, t1, t2, t3) == 1
    assert debt_thresholds.reminder_level(200, t1, t2, t3) == 2
    assert debt_thresholds.reminder_level(299, t1, t2, t3) == 2
    assert debt_thresholds.reminder_level(300, t1, t2, t3) == 3
    assert debt_thresholds.reminder_level(5000, t1, t2, t3) == 3


def test_count_users_open_balance_gte() -> None:
    with TestClient(app):
        with db.get_connection() as conn:
            assert count_users_open_balance_gte(conn, 1) == 0
            assert count_users_open_balance_gte(conn, 0) == 0


def test_admin_shows_global_alert_when_balance_reaches_t3() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/debt-thresholds", data={"threshold_a_eur": "1", "threshold_b_eur": "2", "threshold_c_eur": "3"})
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Max", "group_id": str(gid)})
        client.post(
            "/admin/products",
            data={"name": "Teuer", "price_eur": "5.00"},
        )
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "Teuer (x1)", 500)

        r = client.get("/admin")
        assert r.status_code == 200
        assert "Schwelle 3:" in r.text
        assert "admin-debt-global-alert" in r.text

        ru = client.get(f"/u/{uid}")
        assert ru.status_code == 200
        assert "k-debt-banner" in ru.text
        assert "-5,00 €" in ru.text


def test_admin_can_store_custom_threshold_messages() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post(
            "/admin/debt-thresholds",
            data={
                "threshold_a_eur": "1",
                "threshold_b_eur": "2",
                "threshold_c_eur": "3",
                "message_1": "Bitte zeitnah zahlen",
                "message_2": "Bitte diese Woche zahlen",
                "message_3": "Bitte sofort mit Admin klaeren",
            },
            follow_redirects=False,
        )
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Lea", "group_id": str(gid)})
        client.post("/admin/products", data={"name": "Wasser", "price_eur": "3.00"})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
            add_purchase(conn, uid, pid, "Wasser (x1)", 300)
        ru = client.get(f"/u/{uid}")
        assert ru.status_code == 200
        assert "Bitte sofort mit Admin klaeren" in ru.text
