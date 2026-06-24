from __future__ import annotations

import base64
import binascii
import io
import struct
import zlib

from fastapi.testclient import TestClient

from app import db
from app import group_logo_util
from app.main import app

_MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lQGTWQAAAABJRU5ErkJggg=="
)


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(ctype)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + ctype + payload + crc.to_bytes(4, "big")


def _rgba_png_with_opaque_square(size: int, square_size: int, offset: int) -> bytes:
    rows: list[bytes] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            inside = offset <= x < offset + square_size and offset <= y < offset + square_size
            row.extend((255, 255, 255, 255 if inside else 0))
        rows.append(bytes(row))
    raw = b"".join(b"\x00" + row for row in rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
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


def test_group_logo_upload_trims_transparent_padding_for_uniform_display() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "PadA"})
        client.post("/admin/groups", data={"name": "PadB"})
        with db.get_connection() as conn:
            gid_a = int(conn.execute("SELECT id FROM user_groups WHERE name='PadA'").fetchone()[0])
            gid_b = int(conn.execute("SELECT id FROM user_groups WHERE name='PadB'").fetchone()[0])

        for gid, canvas, offset in (
            (gid_a, 8, 2),
            (gid_b, 16, 7),
        ):
            up = client.post(
                f"/admin/groups/{gid}/edit",
                data={"name": f"Pad{gid}", "tile_logo_size": "large"},
                files={
                    "logo_png": (
                        "logo.png",
                        io.BytesIO(_rgba_png_with_opaque_square(canvas, 4, offset)),
                        "image/png",
                    )
                },
                follow_redirects=False,
            )
            assert up.status_code == 303

        assert group_logo_util.parse_png_ihdr_dimensions(
            group_logo_util.logo_file_path(gid_a).read_bytes()
        ) == (4, 4)
        assert group_logo_util.parse_png_ihdr_dimensions(
            group_logo_util.logo_file_path(gid_b).read_bytes()
        ) == (4, 4)


def test_admin_group_logo_tile_display_options() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "NurLogo"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups WHERE name='NurLogo'").fetchone()[0])

        edit = client.get(f"/admin/groups/{gid}/edit")
        assert edit.status_code == 200
        assert 'name="tile_logo_size"' in edit.text
        assert 'name="tile_logo_only"' in edit.text

        up = client.post(
            f"/admin/groups/{gid}/edit",
            data={
                "name": "NurLogo",
                "tile_logo_size": "max",
                "tile_logo_only": "1",
            },
            files={"logo_png": ("logo.png", io.BytesIO(_MINI_PNG), "image/png")},
            follow_redirects=False,
        )
        assert up.status_code == 303
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT tile_show_name, tile_logo_size FROM user_groups WHERE id = ?",
                (gid,),
            ).fetchone()
        assert int(row[0]) == 0
        assert row[1] == "max"

        home = client.get("/")
        assert home.status_code == 200
        assert "k-tile--logo-only" in home.text
        assert "k-tile--logo-max" in home.text
        assert "NurLogo" not in home.text


def test_admin_group_logo_remove_checkbox() -> None:
    with TestClient(app) as client:
        client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        client.post("/admin/groups", data={"name": "RmLogoGrp"})
        with db.get_connection() as conn:
            gid = int(
                conn.execute(
                    "SELECT id FROM user_groups WHERE name='RmLogoGrp'"
                ).fetchone()[0]
            )
        client.post(
            f"/admin/groups/{gid}/edit",
            data={"name": "RmLogoGrp"},
            files={"logo_png": ("logo.png", io.BytesIO(_MINI_PNG), "image/png")},
            follow_redirects=False,
        )
        assert group_logo_util.logo_file_path(gid).is_file()
        rm = client.post(
            f"/admin/groups/{gid}/edit",
            data={"name": "RmLogoGrp", "remove_logo": "1"},
            files={"logo_png": ("", io.BytesIO(b""), "application/octet-stream")},
            follow_redirects=False,
        )
        assert rm.status_code == 303
        with db.get_connection() as conn:
            has = int(
                conn.execute(
                    "SELECT has_logo FROM user_groups WHERE id = ?", (gid,)
                ).fetchone()[0]
            )
        assert has == 0
        assert not group_logo_util.logo_file_path(gid).is_file()
