from fastapi.testclient import TestClient

from app import db
from app.ledger_service import add_purchase
from app.main import app


def test_kiosk_add_purchase_redirects_back_to_user_page() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        c.post("/admin/users", data={"name": "U1", "group_id": str(gid)})
        c.post("/admin/products", data={"name": "P1", "price_eur": "2.00"})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users LIMIT 1").fetchone()[0])
            pid = int(conn.execute("SELECT id FROM products LIMIT 1").fetchone()[0])

        r = c.post(f"/u/{uid}/add", data={"product_id": str(pid)}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"].endswith(f"/u/{uid}")

        with db.get_connection() as conn:
            n = int(conn.execute("SELECT COUNT(*) FROM ledger_entries WHERE user_id = ?", (uid,)).fetchone()[0])
            assert n == 1


def test_kiosk_home() -> None:
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "k-tiles" in r.text or "k-empty" in r.text
        assert "kasse.css" in r.text
        assert "Top 10" in r.text or "Top Ten" in r.text
        assert "Preisliste" in r.text
        assert 'id="site-repo-link"' in r.text
        assert "Version:" in r.text
        assert 'src="/repo/qr.svg"' in r.text
        assert "v1.4.2" in r.text


def test_kiosk_top_ten_shows_active_users() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
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
        assert 'id="site-repo-link"' not in r.text
        # Ben hat mehr Buchungen und sollte vor Anna erscheinen.
        assert r.text.find("Ben") < r.text.find("Anna")


def test_kiosk_top_ten_can_rank_by_payments() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        c.post("/admin/users", data={"name": "Anna", "group_id": str(gid)})
        c.post("/admin/users", data={"name": "Ben", "group_id": str(gid)})
        c.post("/admin/products", data={"name": "Groß", "price_eur": "3.00"})
        c.post("/admin/products", data={"name": "Klein", "price_eur": "1.00"})
        with db.get_connection() as conn:
            users = conn.execute("SELECT id FROM users ORDER BY name").fetchall()
            uid_anna = int(users[0][0])
            uid_ben = int(users[1][0])
            pid_gross = int(conn.execute("SELECT id FROM products WHERE name='Groß'").fetchone()[0])
            pid_klein = int(conn.execute("SELECT id FROM products WHERE name='Klein'").fetchone()[0])
            add_purchase(conn, uid_anna, pid_gross, "Groß (x1)", 300)
            add_purchase(conn, uid_ben, pid_klein, "Klein (x1)", 100)
            add_purchase(conn, uid_ben, pid_klein, "Klein (x1)", 100)
        by_entries = c.get("/top-ten?ranking=entries")
        assert by_entries.status_code == 200
        assert ">Buchungen<" not in by_entries.text
        assert ">Zahlungen<" not in by_entries.text
        assert "k-top-ten-switch__btn--active" in by_entries.text
        assert by_entries.text.find("Ben") < by_entries.text.find("Anna")
        by_payments = c.get("/top-ten?ranking=payments")
        assert by_payments.status_code == 200
        assert ">Buchungen<" not in by_payments.text
        assert ">Zahlungen<" not in by_payments.text
        assert by_payments.text.find("Anna") < by_payments.text.find("Ben")


def test_kiosk_preisliste_shows_products() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/products", data={"name": "Wasser", "price_eur": "1.20"})
        r = c.get("/preisliste")
        assert r.status_code == 200
        assert "Preisliste" in r.text
        assert "Wasser" in r.text
        assert 'id="site-repo-link"' in r.text
        assert 'src="/repo/qr.svg"' in r.text
        assert "v1.4.2" in r.text


def test_kiosk_preisliste_hides_products_with_pricelist_flag_off() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/products", data={"name": "NurKiosk", "price_eur": "1.30"})
        with db.get_connection() as conn:
            pid = int(conn.execute("SELECT id FROM products WHERE name='NurKiosk'").fetchone()[0])
        c.post(
            f"/admin/products/{pid}/edit",
            data={
                "name": "NurKiosk",
                "price_eur": "1.30",
            },
            follow_redirects=False,
        )
        r = c.get("/preisliste")
        assert r.status_code == 200
        assert "NurKiosk" not in r.text


def test_kiosk_user_shows_credit_with_plus_and_green_class() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        with db.get_connection() as conn:
            gid = int(conn.execute("SELECT id FROM user_groups LIMIT 1").fetchone()[0])
        c.post("/admin/users", data={"name": "Lea", "group_id": str(gid)})
        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='Lea'").fetchone()[0])
            conn.execute(
                """
                INSERT INTO ledger_entries (user_id, product_id, description, amount_cents, created_at)
                VALUES (?, NULL, ?, ?, ?)
                """,
                (uid, "Admin-Guthaben", -500, "2026-01-01T10:00:00"),
            )
        r = c.get(f"/u/{uid}")
        assert r.status_code == 200
        assert "+5,00 €" in r.text
        assert "k-user-head__balance-value--credit" in r.text
        assert 'href="/g/' in r.text
        assert "k-user-head__inline-back" in r.text
        assert ">← G1</a>" in r.text
        assert 'id="site-repo-link"' not in r.text


def test_kiosk_flappy_easter_egg_route() -> None:
    with TestClient(app) as c:
        r = c.get("/egg/flappy")
        assert r.status_code == 200
        assert "flappy-canvas" in r.text


def test_kiosk_user_shows_only_products_visible_for_users_group() -> None:
    with TestClient(app) as c:
        c.post("/admin/login", data={"password": "admin"}, follow_redirects=False)
        c.post("/admin/groups", data={"name": "G1"})
        c.post("/admin/groups", data={"name": "G2"})
        with db.get_connection() as conn:
            groups = conn.execute("SELECT id, name FROM user_groups ORDER BY name").fetchall()
            gid1 = int(groups[0][0])
            gid2 = int(groups[1][0])
        c.post("/admin/users", data={"name": "U1", "group_id": str(gid1)})
        c.post("/admin/products", data={"name": "Standard", "price_eur": "1.00"})
        c.post("/admin/products", data={"name": "Spezial", "price_eur": "2.00"})

        with db.get_connection() as conn:
            uid = int(conn.execute("SELECT id FROM users WHERE name='U1'").fetchone()[0])
            pid_special = int(conn.execute("SELECT id FROM products WHERE name='Spezial'").fetchone()[0])
            conn.execute(
                "INSERT INTO product_group_hidden (product_id, group_id) VALUES (?, ?)",
                (pid_special, gid1),
            )

        r = c.get(f"/u/{uid}")
        assert r.status_code == 200
        assert "Standard" in r.text
        assert "Spezial" not in r.text

        add_hidden = c.post(f"/u/{uid}/add", data={"product_id": str(pid_special)}, follow_redirects=False)
        assert add_hidden.status_code == 400

        with db.get_connection() as conn:
            conn.execute("DELETE FROM product_group_hidden WHERE product_id = ? AND group_id = ?", (pid_special, gid1))
            conn.execute(
                "INSERT INTO product_group_hidden (product_id, group_id) VALUES (?, ?)",
                (pid_special, gid2),
            )

        add_visible = c.post(f"/u/{uid}/add", data={"product_id": str(pid_special)}, follow_redirects=False)
        assert add_visible.status_code == 303
        assert add_visible.headers["location"].endswith(f"/u/{uid}")


def test_repo_qr_svg_route() -> None:
    with TestClient(app) as c:
        r = c.get("/repo/qr.svg")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in r.text
