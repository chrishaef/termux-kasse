#!/usr/bin/env python3
"""
Demo-Datenbank anlegen, Uvicorn starten und PNG-Screenshots für die README erzeugen.

Voraussetzungen (nur auf dem Rechner, der die Bilder bauen soll):
  pip install -r requirements.txt -r scripts/requirements-screenshots.txt
  python -m playwright install chromium

Aufruf vom Projektroot:
  python scripts/capture_readme_screenshots.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / "docs" / "readme-screenshots"
PORT = 9876
BASE = f"http://127.0.0.1:{PORT}"


def _wait_http_ready(timeout_s: float = 30.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{BASE}/", follow_redirects=True, timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as e:  # noqa: BLE001 — robustes Warten auf Serverstart
            last_err = e
            time.sleep(0.25)
    msg = f"Server unter {BASE} wurde nicht bereit."
    if last_err:
        msg += f" Letzter Fehler: {last_err!r}"
    raise RuntimeError(msg)


def _seed_demo() -> tuple[int, int]:
    """Legt Stammdaten und ein paar Buchungen an. Gibt (group_id, user_id_max) zurück."""
    from app import db
    from app import debt_thresholds
    from app.db import init_db
    from app.ledger_service import add_purchase

    init_db()
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO user_groups (name, sort_order) VALUES (?, ?)",
            ("Vereinskasse", 0),
        )
        gid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO users (group_id, name, sort_order) VALUES (?, ?, ?)",
            (gid, "Max Mustermann", 0),
        )
        uid_max = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        conn.execute(
            "INSERT INTO users (group_id, name, sort_order) VALUES (?, ?, ?)",
            (gid, "Erika Beispiel", 1),
        )
        conn.execute(
            """
            INSERT INTO products (name, price_cents, active, sort_order)
            VALUES ('Cola', 200, 1, 0), ('Kaffee', 150, 1, 1)
            """
        )
        row_p = conn.execute("SELECT id FROM products WHERE name = 'Cola' LIMIT 1").fetchone()
        pid_cola = int(row_p[0])
        add_purchase(conn, uid_max, pid_cola, "Cola (x1)", 200)
        add_purchase(conn, uid_max, pid_cola, "Cola (x1)", 200)
        debt_thresholds.save_thresholds_cents(conn, 100, 250, 500)
        debt_thresholds.save_threshold_messages(
            conn,
            "Demo: erste Warnstufe (über 1 € offen).",
            "Demo: zweite Warnstufe.",
            "Demo: dritte Warnstufe — bitte begleichen.",
        )
    return gid, uid_max


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright fehlt. Installieren mit:\n"
            "  pip install -r scripts/requirements-screenshots.txt\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 1

    data_root = ROOT / ".tmp_readme_screenshot_data"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True)
    (data_root / "jahresabschluss").mkdir(exist_ok=True)
    master_file = data_root / "master_pw.txt"
    master_file.write_text("master", encoding="utf-8")

    env = os.environ.copy()
    env["KASSE_DATA_DIR"] = str(data_root)
    env["KASSE_SECRET_KEY"] = "readme-screenshot-secret-32bytes!!"
    env["KASSE_MASTER_PASSWORD_FILE"] = str(master_file)

    for k, v in (
        ("KASSE_DATA_DIR", env["KASSE_DATA_DIR"]),
        ("KASSE_SECRET_KEY", env["KASSE_SECRET_KEY"]),
        ("KASSE_MASTER_PASSWORD_FILE", env["KASSE_MASTER_PASSWORD_FILE"]),
    ):
        os.environ[k] = v

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    gid, uid_max = _seed_demo()

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_http_ready()
        shots: list[tuple[str, str]] = [
            ("kiosk-start.png", f"{BASE}/"),
            ("kiosk-gruppe.png", f"{BASE}/g/{gid}"),
            ("kiosk-nutzer.png", f"{BASE}/u/{uid_max}"),
            ("kiosk-preisliste.png", f"{BASE}/preisliste"),
            ("kiosk-top-ten.png", f"{BASE}/top-ten"),
        ]
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="de-DE",
            )
            page = context.new_page()
            for filename, url in shots:
                page.goto(url, wait_until="networkidle", timeout=60_000)
                page.screenshot(path=str(OUT_DIR / filename), full_page=True)
            page.goto(f"{BASE}/admin/login", wait_until="networkidle", timeout=60_000)
            page.fill('input[name="password"]', "admin")
            page.click('button[type="submit"]')
            page.wait_for_url("**/admin", timeout=60_000)
            page.goto(f"{BASE}/admin", wait_until="networkidle", timeout=60_000)
            page.screenshot(path=str(OUT_DIR / "admin-start.png"), full_page=True)
            page.goto(f"{BASE}/admin/statistics", wait_until="networkidle", timeout=60_000)
            page.screenshot(path=str(OUT_DIR / "admin-statistik.png"), full_page=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    print(f"Screenshots geschrieben nach: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
