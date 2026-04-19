from __future__ import annotations

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase, user_balance_cents
from app.main import app


def _seed_open_balance(client: TestClient) -> int:
    client.post(
        "/admin/setup",
        data={"username": "adm", "password": "pw12345", "password2": "pw12345"},
        follow_redirects=False,
    )
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
        path = urlparse(r.headers["location"]).path
        assert path.endswith("/done")
        done = client.get(path)
        assert done.status_code == 200
        assert "PDF wird geladen" in done.text
        pdf = client.get(path.replace("/done", "/pdf"))
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        disp = pdf.headers.get("content-disposition", "")
        assert "Abrechnung_Anna_" in disp
        assert ".pdf" in disp
        with db.get_connection() as conn:
            assert user_balance_cents(conn, uid) == 0


def test_settlement_confirm_no_open_redirects() -> None:
    with TestClient(app) as client:
        client.post(
            "/admin/setup",
            data={"username": "adm", "password": "pw12345", "password2": "pw12345"},
            follow_redirects=False,
        )
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
        client.post(
            "/admin/setup",
            data={"username": "adm", "password": "pw12345", "password2": "pw12345"},
            follow_redirects=False,
        )
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
