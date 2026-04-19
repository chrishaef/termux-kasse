from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.main import app


def test_admin_group_edit_flow() -> None:
    with TestClient(app) as client:
        client.post(
            "/admin/setup",
            data={"username": "adm", "password": "pw12345", "password2": "pw12345"},
            follow_redirects=False,
        )
        client.post("/admin/groups", data={"name": "Alpha"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups WHERE name='Alpha'").fetchone()[0])
        r = client.get(f"/admin/groups/{gid}/edit")
        assert r.status_code == 200
        assert "Alpha" in r.text
        r2 = client.post(
            f"/admin/groups/{gid}/edit",
            data={"name": "Beta"},
            follow_redirects=False,
        )
        assert r2.status_code == 303
        with db.get_connection() as conn:
            name = conn.execute("SELECT name FROM user_groups WHERE id = ?", (gid,)).fetchone()[0]
        assert name == "Beta"
