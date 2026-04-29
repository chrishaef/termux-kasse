from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import db
from app.main import app


def test_admin_products_status_is_shown_on_toggle_button() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/products", data={"name": "Cola", "price_eur": "2.00"})

        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products WHERE name = 'Cola'").fetchone()[0])

        page = client.get("/admin/products")
        assert page.status_code == 200
        assert "<th>Aktiv</th>" not in page.text
        assert "admin-products-table" in page.text
        assert re.search(r">\s*Aktiv\s*</button>", page.text)
        assert "admin-btn-status--active" in page.text
        assert "confirm('Artikel wirklich löschen?')" in page.text

        toggle = client.post(f"/admin/products/{pid}/toggle", follow_redirects=False)
        assert toggle.status_code == 303
        assert toggle.headers["location"] == "/admin/products"

        page_after = client.get("/admin/products")
        assert page_after.status_code == 200
        assert re.search(r">\s*Inaktiv\s*</button>", page_after.text)
        assert "admin-btn-status--inactive" in page_after.text


def test_admin_products_toggle_returns_json_for_fetch_requests() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/products", data={"name": "Wasser", "price_eur": "1.00"})

        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products WHERE name = 'Wasser'").fetchone()[0])

        toggle = client.post(
            f"/admin/products/{pid}/toggle",
            headers={"accept": "application/json", "x-requested-with": "fetch"},
        )
        assert toggle.status_code == 200
        assert toggle.json() == {"ok": True, "product_id": pid, "active": False}

        with db.get_connection() as conn:
            active = int(conn.execute("SELECT active FROM products WHERE id = ?", (pid,)).fetchone()[0])
        assert active == 0


def test_product_visibility_can_be_configured_per_group() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "G1"})
        client.post("/admin/groups", data={"name": "G2"})
        with db.get_connection() as conn:
            groups = conn.execute("SELECT id, name FROM user_groups ORDER BY name").fetchall()
            gid1 = int(groups[0][0])
            gid2 = int(groups[1][0])

        client.post("/admin/products", data={"name": "Sonder", "price_eur": "1.50"})
        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products WHERE name = 'Sonder'").fetchone()[0])

        save = client.post(
            f"/admin/products/{pid}/edit",
            data={"name": "Sonder", "price_eur": "1.50", "visible_group_ids": str(gid1)},
            follow_redirects=False,
        )
        assert save.status_code == 303
        assert save.headers["location"] == "/admin/products"

        with db.get_connection() as conn:
            hidden = conn.execute(
                "SELECT group_id FROM product_group_hidden WHERE product_id = ? ORDER BY group_id",
                (pid,),
            ).fetchall()
            hidden_ids = [int(r[0]) for r in hidden]
        assert hidden_ids == [gid2]
