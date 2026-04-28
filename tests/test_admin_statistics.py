from __future__ import annotations

from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase
from app.main import app
from app.routers import admin as admin_router


def _seed_stats_data(client: TestClient) -> None:
    client.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
    client.post("/admin/groups", data={"name": "G1"})
    client.post("/admin/groups", data={"name": "G2"})
    with db.get_connection() as conn:
        groups = conn.execute("SELECT id, name FROM user_groups ORDER BY name").fetchall()
        gid_1 = int(groups[0][0])
        gid_2 = int(groups[1][0])
    client.post("/admin/users", data={"name": "Anna", "group_id": str(gid_1)})
    client.post("/admin/users", data={"name": "Ben", "group_id": str(gid_1)})
    client.post("/admin/users", data={"name": "Cara", "group_id": str(gid_2)})
    client.post("/admin/products", data={"name": "Cola", "price_eur": "2.00"})
    with db.get_connection() as conn:
        users = conn.execute("SELECT id FROM users ORDER BY name").fetchall()
        uid_anna = int(users[0][0])
        uid_ben = int(users[1][0])
        uid_cara = int(users[2][0])
        pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])
        add_purchase(conn, uid_anna, pid, "Cola (x1)", 200)
        add_purchase(conn, uid_ben, pid, "Cola (x1)", 200)
        add_purchase(conn, uid_ben, pid, "Cola (x1)", 200)
        add_purchase(conn, uid_cara, pid, "Cola (x1)", 500)
        conn.execute(
            "UPDATE ledger_entries SET created_at = ? WHERE user_id = ?",
            ("2026-04-10T10:00:00", uid_anna),
        )
        conn.execute(
            "UPDATE ledger_entries SET created_at = ? WHERE user_id = ?",
            ("2026-04-15T10:00:00", uid_ben),
        )
        conn.execute(
            "UPDATE ledger_entries SET created_at = ? WHERE user_id = ?",
            ("2026-04-15T10:00:00", uid_cara),
        )


def test_admin_statistics_page_pdf_and_xlsx() -> None:
    with TestClient(app) as client:
        _seed_stats_data(client)
        with db.get_connection() as conn:
            gid_1 = int(
                conn.execute("SELECT id FROM user_groups WHERE name = 'G1'").fetchone()[0]
            )
        r = client.get(f"/admin/statistics?start=2026-04-12&end=2026-04-15&group_id={gid_1}")
        assert r.status_code == 200
        assert "Statistik Zeitraum wählen" in r.text
        assert "admin-statistics-toolbar" in r.text
        assert "admin-statistics-toolbar__filters" in r.text
        assert "admin-statistics-toolbar__actions" in r.text
        assert "Topliste Nutzer (nach Summe)" in r.text
        assert "Topliste Nutzer (Ausstände)" in r.text
        assert "Artikel-Auswertung" in r.text
        assert "Aktiver Gruppenfilter: <strong>G1</strong>" in r.text
        assert "Cara" not in r.text
        assert "Anna" not in r.text
        assert "Ben" in r.text
        assert "Offener Ausstand" in r.text
        assert "2x Cola" in r.text
        assert "2 Buchungen" not in r.text
        assert "4,00 €" in r.text

        pdf = client.get(f"/admin/statistics/pdf?start=2026-04-12&end=2026-04-15&group_id={gid_1}")
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        disp_pdf = pdf.headers.get("content-disposition", "")
        assert "Statistik_Zeitraum" in disp_pdf

        xlsx = client.get(
            f"/admin/statistics/xlsx?start=2026-04-12&end=2026-04-15&group_id={gid_1}"
        )
        assert xlsx.status_code == 200
        assert (
            xlsx.headers["content-type"]
            == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        disp_xlsx = xlsx.headers.get("content-disposition", "")
        assert "Statistik_Zeitraum" in disp_xlsx


def test_statistics_pdf_includes_all_users_payload_for_selected_group(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_statistics_pdf_bytes(
        period_start: str | None,
        period_end: str | None,
        group_name: str | None,
        totals: dict[str, int],
        user_rows: list[dict[str, object]],
        product_rows: list[dict[str, object]],
        all_group_users: list[dict[str, object]] | None = None,
    ) -> bytes:
        captured["group_name"] = group_name
        captured["all_group_users"] = all_group_users or []
        return b"%PDF-1.4\n%fake\n"

    monkeypatch.setattr(admin_router, "build_statistics_pdf_bytes", fake_build_statistics_pdf_bytes)
    with TestClient(app) as client:
        _seed_stats_data(client)
        with db.get_connection() as conn:
            gid_1 = int(
                conn.execute("SELECT id FROM user_groups WHERE name = 'G1'").fetchone()[0]
            )
        r = client.get(f"/admin/statistics/pdf?start=2026-04-12&end=2026-04-15&group_id={gid_1}")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        rows = list(captured.get("all_group_users", []))
        names = {str(row.get("name")) for row in rows}
        assert captured.get("group_name") == "G1"
        assert names == {"Anna", "Ben"}
        row_by_name = {str(r.get("name")): r for r in rows}
        assert int(row_by_name["Ben"].get("article_count_total", 0)) == 2
        assert int(row_by_name["Anna"].get("article_count_total", 0)) == 0
        items = list(row_by_name["Ben"].get("article_items", []))
        assert items
        assert str(items[0].get("label")) == "Cola"
        assert int(items[0].get("quantity", 0)) == 2
