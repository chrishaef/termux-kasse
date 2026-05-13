from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient

from app import db
from app.main import app

_MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lQGTWQAAAABJRU5ErkJggg=="
)


def test_admin_group_edit_flow() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "Alpha"})
        overview = client.get("/admin/groups")
        assert overview.status_code == 200
        assert "admin-table-groups" in overview.text
        assert "admin-action-btn" in overview.text
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


def test_admin_group_logo_upload_and_kiosk_tile() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "LogoGrp"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups WHERE name='LogoGrp'").fetchone()[0])
        up = client.post(
            f"/admin/groups/{gid}/edit",
            data={"name": "LogoGrp"},
            files={"logo_png": ("logo.png", io.BytesIO(_MINI_PNG), "image/png")},
            follow_redirects=False,
        )
        assert up.status_code == 303
        with db.get_connection() as conn:
            has = int(
                conn.execute(
                    "SELECT has_logo FROM user_groups WHERE id = ?", (gid,)
                ).fetchone()[0]
            )
        assert has == 1
        home = client.get("/")
        assert home.status_code == 200
        assert f'/group-logo/{gid}' in home.text
        assert "k-tile__logo" in home.text
        lg = client.get(f"/group-logo/{gid}")
        assert lg.status_code == 200
        assert lg.headers.get("content-type", "").startswith("image/png")
