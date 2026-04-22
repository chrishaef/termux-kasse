from __future__ import annotations

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase, user_balance_cents
from app.main import app


def _seed_open_balance(client: TestClient) -> int:
    client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
    client.post("/admin/groups", data={"name": "G1"})
    with db.get_connection() as conn:
        gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
    client.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
    with db.get_connection() as conn:
        uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
    client.post(
        "/admin/products",
        data={"name": "Cola", "price_eur": "2.00"},
    )
    with db.get_connection() as conn:
        pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
        add_purchase(conn, uid, pid, "Cola (x1)", 200)
    return uid


def test_settlement_confirm_requires_quittance() -> None:
    with TestClient(app) as client:
        uid = _seed_open_balance(client)
        client.post("/admin/settlements/start", data={"user_id": str(uid)}, follow_redirects=False)
        r = client.post(
            "/admin/settlements/confirm",
            data={"user_id": str(uid), "note": ""},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "err=noconfirm" in r.headers["location"]


def test_settlement_confirm_pdf_and_clears_balance() -> None:
    with TestClient(app) as client:
        uid = _seed_open_balance(client)
        client.post("/admin/settlements/start", data={"user_id": str(uid)}, follow_redirects=False)
        r = client.post(
            "/admin/settlements/confirm",
            data={"user_id": str(uid), "note": "Bar", "received_confirmed": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert urlparse(r.headers["location"]).path == "/admin"
        assert "settlement_done=1" in r.headers["location"]
        with db.get_connection() as conn:
            sid = int(conn.execute("SELECT id FROM settlements ORDER BY id DESC LIMIT 1").fetchone()[0])
        pdf = client.get(f"/admin/settlements/{sid}/pdf")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        disp = pdf.headers.get("content-disposition", "")
        assert "Abrechnung_Anna_" in disp
        assert ".pdf" in disp
        with db.get_connection() as conn:
            assert user_balance_cents(conn, uid) == 0


def test_settlement_confirm_no_open_redirects() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        client.post("/admin/users", data={"name": "Bob", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
        r = client.get(f"/admin/settlements/confirm?user_id={uid}", follow_redirects=False)
        assert r.status_code == 303
        assert "err=no_open" in r.headers["location"]


def test_settlement_start_filters_users_by_group() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        client.post("/admin/groups", data={"name": "G2"})
        with db.get_connection() as conn:
            g1 = int(conn.execute("SELECT id FROM user_groups WHERE name='G1'").fetchone()[0])
            g2 = int(conn.execute("SELECT id FROM user_groups WHERE name='G2'").fetchone()[0])
        client.post("/admin/users", data={"name": "Anna", "group_id": str(g1)})
        client.post("/admin/users", data={"name": "Ben", "group_id": str(g2)})
        r = client.get(f"/admin/settlements/start?group_id={g1}")
        assert r.status_code == 200
        assert "Anna" in r.text
        assert "Ben" not in r.text


def test_settlement_start_shows_selected_user_balance() -> None:
    with TestClient(app) as client:
        uid = _seed_open_balance(client)
        r = client.get(f"/admin/settlements/start?user_id={uid}")
        assert r.status_code == 200
        assert "Kontostand" in r.text
        assert "-2,00 €" in r.text
        assert "Bisher abgerechnet" in r.text
        assert "Letzte Abrechnung" in r.text
        assert 'name="user_id" onchange="this.form.submit()"' in r.text
