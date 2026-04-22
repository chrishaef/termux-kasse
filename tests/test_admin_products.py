from __future__ import annotations

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
        assert ">Aktiv</button>" in page.text

        toggle = client.post(f"/admin/products/{pid}/toggle", follow_redirects=False)
        assert toggle.status_code == 303
        assert toggle.headers["location"] == "/admin/products"

        page_after = client.get("/admin/products")
        assert page_after.status_code == 200
        assert ">Inaktiv</button>" in page_after.text
