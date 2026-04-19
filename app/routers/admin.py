from __future__ import annotations

import re
import sqlite3
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db
from app import debt_thresholds
from app import kiosk_notice
from app import ledger_service
from app.auth import hash_password, verify_password
from app.export_service import build_pdf_bytes, build_xlsx_bytes
from app.templates_env import TEMPLATES

router = APIRouter(prefix="/admin", tags=["admin"])


def _redirect_login(request: Request) -> Optional[RedirectResponse]:
    if not request.session.get("admin_user"):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _parse_price_eur_to_cents(raw: str) -> int:
    s = raw.strip().replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        raise ValueError("Preis ungültig")
    return int(round(float(s) * 100))


_FN_UNSAFE = re.compile(r'[\s<>:"/\\|?*\x00-\x1f]+')


def _settlement_filename_stem(header: sqlite3.Row) -> str:
    name = str(header["user_name"] or "Nutzer").strip() or "Nutzer"
    name = _FN_UNSAFE.sub("_", name)
    name = re.sub(r"_+", "_", name).strip("_") or "Nutzer"
    name = name[:45]
    created = str(header["created_at"] or "")
    if len(created) >= 10 and created[4] == "-" and created[7] == "-":
        day = created[:10]
    else:
        day = "unbekannt"
    return f"Abrechnung_{name}_{day}"


def _attachment_disposition(stem: str, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    full = f"{stem}{ext}"
    ascii_fallback = full.encode("ascii", "replace").decode("ascii").replace("?", "_")[:180]
    if not ascii_fallback.strip():
        ascii_fallback = f"abrechnung{ext}"
    enc = quote(full, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{enc}'


@router.get("/login", response_class=HTMLResponse)
def admin_login_form(request: Request) -> Response:
    if request.session.get("admin_user"):
        return RedirectResponse("/admin", status_code=303)
    with db.get_connection() as conn:
        setup_needed = not ledger_service.admin_exists(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/login.html",
        {"title": "Admin-Login", "setup_needed": setup_needed},
    )


@router.post("/login")
def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Response:
    with db.get_connection() as conn:
        if not ledger_service.admin_exists(conn):
            return RedirectResponse("/admin/setup", status_code=303)
        row = db.fetch_one(
            conn,
            "SELECT username, password_hash FROM admin_users WHERE username = ?",
            (username.strip(),),
        )
        if not row or not verify_password(password, row["password_hash"]):
            setup_needed = not ledger_service.admin_exists(conn)
            return TEMPLATES.TemplateResponse(
                request,
                "admin/login.html",
                {
                    "title": "Admin-Login",
                    "error": "Zugangsdaten ungültig",
                    "setup_needed": setup_needed,
                },
                status_code=401,
            )
    request.session["admin_user"] = row["username"]
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout")
def admin_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/setup", response_class=HTMLResponse)
def admin_setup_form(request: Request) -> HTMLResponse:
    with db.get_connection() as conn:
        if ledger_service.admin_exists(conn):
            return RedirectResponse("/admin/login", status_code=303)  # type: ignore[return-value]
    return TEMPLATES.TemplateResponse(request, "admin/setup.html", {"title": "Admin einrichten"})


@router.post("/setup")
def admin_setup_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
) -> Response:
    if password != password2:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/setup.html",
            {"title": "Admin einrichten", "error": "Passwörter stimmen nicht überein"},
            status_code=400,
        )
    with db.get_connection() as conn:
        if ledger_service.admin_exists(conn):
            return RedirectResponse("/admin/login", status_code=303)
        conn.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            (username.strip(), hash_password(password)),
        )
    request.session["admin_user"] = username.strip()
    return RedirectResponse("/admin", status_code=303)


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        if not ledger_service.admin_exists(conn):
            return RedirectResponse("/admin/setup", status_code=303)
        stats = {
            "groups": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM user_groups", ())["c"],
            "users": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM users", ())["c"],
            "products": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM products", ())["c"],
            "categories": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM product_categories", ())["c"],
        }
        finance = ledger_service.finance_overview(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/dashboard.html",
        {"title": "Admin", "stats": stats, "finance": finance},
    )


@router.get("/news", response_class=HTMLResponse)
def admin_news_form(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    stored = kiosk_notice.get_stored_custom()
    return TEMPLATES.TemplateResponse(
        request,
        "admin/news.html",
        {
            "title": "Kiosk-Nachricht",
            "stored_notice": stored,
            "default_notice": kiosk_notice.DEFAULT_KIOSK_NOTICE,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/news")
def admin_news_save(request: Request, message: str = Form("")) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    kiosk_notice.set_custom_message(message)
    return RedirectResponse("/admin/news?saved=1", status_code=303)


def _eur_field_from_cents(cents: int) -> str:
    return f"{int(cents) / 100:.2f}"


@router.get("/debt-thresholds", response_class=HTMLResponse)
def admin_debt_thresholds_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        t1, t2, t3 = debt_thresholds.get_thresholds(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/debt_thresholds.html",
        {
            "title": "Ausstands-Schwellen",
            "t1": t1,
            "t2": t2,
            "t3": t3,
            "t1_eur": _eur_field_from_cents(t1),
            "t2_eur": _eur_field_from_cents(t2),
            "t3_eur": _eur_field_from_cents(t3),
            "saved": request.query_params.get("saved") == "1",
            "error": request.query_params.get("err") == "invalid",
        },
    )


@router.post("/debt-thresholds")
def admin_debt_thresholds_post(
    request: Request,
    threshold_a_eur: str = Form(...),
    threshold_b_eur: str = Form(...),
    threshold_c_eur: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    try:
        ca = _parse_price_eur_to_cents(threshold_a_eur)
        cb = _parse_price_eur_to_cents(threshold_b_eur)
        cc = _parse_price_eur_to_cents(threshold_c_eur)
    except ValueError:
        return RedirectResponse("/admin/debt-thresholds?err=invalid", status_code=303)
    with db.get_connection() as conn:
        debt_thresholds.save_thresholds_cents(conn, ca, cb, cc)
    return RedirectResponse("/admin/debt-thresholds?saved=1", status_code=303)


@router.get("/groups", response_class=HTMLResponse)
def admin_groups(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        groups = db.fetch_all(conn, "SELECT id, name FROM user_groups ORDER BY name")
    return TEMPLATES.TemplateResponse(
        request,
        "admin/groups.html",
        {"title": "Nutzergruppen", "groups": groups},
    )


@router.post("/groups")
def admin_groups_create(request: Request, name: str = Form(...)) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/groups", status_code=303)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO user_groups (name) VALUES (?)", (name,))
    return RedirectResponse("/admin/groups", status_code=303)


@router.get("/groups/{group_id}/edit", response_class=HTMLResponse)
def admin_groups_edit_form(request: Request, group_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        group = db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (group_id,))
        if not group:
            raise HTTPException(status_code=404)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/groups_edit.html",
        {"title": "Gruppe bearbeiten", "group": group},
    )


@router.post("/groups/{group_id}/edit")
def admin_groups_edit_save(
    request: Request,
    group_id: int,
    name: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse(f"/admin/groups/{group_id}/edit", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM user_groups WHERE id = ?", (group_id,))
        if not row:
            raise HTTPException(status_code=404)
        conn.execute("UPDATE user_groups SET name = ? WHERE id = ?", (name, group_id))
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/groups/{group_id}/delete")
def admin_groups_delete(request: Request, group_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM user_groups WHERE id = ?", (group_id,))
    return RedirectResponse("/admin/groups", status_code=303)


@router.get("/users", response_class=HTMLResponse)
def admin_users(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        users = ledger_service.users_admin_overview(conn)
        groups = db.fetch_all(conn, "SELECT id, name FROM user_groups ORDER BY name")
        overview_totals = {
            "open_balance_cents": sum(int(u["open_balance_cents"]) for u in users),
            "open_entries_count": sum(int(u["open_entries_count"]) for u in users),
            "settled_total_cents": sum(int(u["settled_total_cents"]) for u in users),
            "settlements_count": sum(int(u["settlements_count"]) for u in users),
        }
    return TEMPLATES.TemplateResponse(
        request,
        "admin/users.html",
        {
            "title": "Nutzer",
            "users": users,
            "groups": groups,
            "overview_totals": overview_totals,
        },
    )


@router.post("/users")
def admin_users_create(
    request: Request,
    name: str = Form(...),
    group_id: int = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/users", status_code=303)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO users (group_id, name) VALUES (?, ?)", (group_id, name))
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
def admin_users_delete(request: Request, user_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/categories", response_class=HTMLResponse)
def admin_categories(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        cats = db.fetch_all(
            conn,
            "SELECT id, name, sort_order FROM product_categories ORDER BY sort_order, name",
        )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/categories.html",
        {"title": "Warengruppen", "categories": cats},
    )


@router.post("/categories")
def admin_categories_create(
    request: Request,
    name: str = Form(...),
    sort_order: int = Form(0),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/categories", status_code=303)
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO product_categories (name, sort_order) VALUES (?, ?)",
            (name, sort_order),
        )
    return RedirectResponse("/admin/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
def admin_categories_delete(request: Request, cat_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM product_categories WHERE id = ?", (cat_id,))
    return RedirectResponse("/admin/categories", status_code=303)


@router.get("/products", response_class=HTMLResponse)
def admin_products(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        products = db.fetch_all(
            conn,
            """
            SELECT p.id, p.name, p.price_cents, p.active, c.name AS category_name, c.id AS category_id
            FROM products p
            JOIN product_categories c ON c.id = p.category_id
            ORDER BY c.sort_order, c.name, p.name
            """,
        )
        cats = db.fetch_all(conn, "SELECT id, name FROM product_categories ORDER BY sort_order, name")
    return TEMPLATES.TemplateResponse(
        request,
        "admin/products.html",
        {"title": "Artikel", "products": products, "categories": cats},
    )


@router.post("/products")
def admin_products_create(
    request: Request,
    category_id: int = Form(...),
    name: str = Form(...),
    price_eur: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/products", status_code=303)
    try:
        cents = _parse_price_eur_to_cents(price_eur)
    except ValueError:
        return RedirectResponse("/admin/products", status_code=303)
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO products (category_id, name, price_cents, active)
            VALUES (?, ?, ?, 1)
            """,
            (category_id, name, cents),
        )
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
def admin_products_delete(request: Request, product_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/toggle")
def admin_products_toggle(request: Request, product_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE products SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (product_id,),
        )
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/settlements", response_class=HTMLResponse)
def admin_settlements_list(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        settlements = db.fetch_all(
            conn,
            """
            SELECT s.id, s.created_at, s.total_cents, u.name AS user_name, g.name AS group_name
            FROM settlements s
            JOIN users u ON u.id = s.user_id
            JOIN user_groups g ON g.id = u.group_id
            ORDER BY datetime(s.created_at) DESC
            LIMIT 100
            """,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlements.html",
        {"title": "Abrechnungen", "settlements": settlements},
    )


@router.get("/settlements/start", response_class=HTMLResponse)
def admin_settlement_start_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        users = db.fetch_all(
            conn,
            """
            SELECT u.id, u.name, g.name AS group_name
            FROM users u
            JOIN user_groups g ON g.id = u.group_id
            ORDER BY g.name, u.name
            """,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlement_start.html",
        {"title": "Abrechnung starten", "users": users},
    )


@router.post("/settlements/start")
def admin_settlement_start_post(request: Request, user_id: int = Form(...)) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    return RedirectResponse(f"/admin/settlements/confirm?user_id={user_id}", status_code=303)


@router.get("/settlements/confirm", response_class=HTMLResponse)
def admin_settlement_confirm_get(request: Request, user_id: int = Query(...)) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        user = db.fetch_one(
            conn,
            """
            SELECT u.id, u.name, g.name AS group_name
            FROM users u
            JOIN user_groups g ON g.id = u.group_id
            WHERE u.id = ?
            """,
            (user_id,),
        )
        if not user:
            raise HTTPException(status_code=404)
        open_cents = ledger_service.user_balance_cents(conn, user_id)
        previously_settled_cents = ledger_service.total_previously_settled_cents(conn, user_id)
        settlement_count = ledger_service.settlement_count_for_user(conn, user_id)
        open_lines = ledger_service.open_ledger_for_user(conn, user_id)
    if open_cents == 0 or not open_lines:
        return RedirectResponse("/admin/settlements/start?err=no_open", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlement_confirm.html",
        {
            "title": "Abrechnung bestätigen",
            "user": user,
            "open_cents": open_cents,
            "previously_settled_cents": previously_settled_cents,
            "settlement_count": settlement_count,
            "open_lines": open_lines,
        },
    )


@router.post("/settlements/confirm")
def admin_settlement_confirm_post(
    request: Request,
    user_id: int = Form(...),
    note: str = Form(""),
    received_confirmed: str | None = Form(None),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    if received_confirmed not in ("1", "on", "yes", "true"):
        return RedirectResponse(
            f"/admin/settlements/confirm?user_id={user_id}&err=noconfirm",
            status_code=303,
        )
    note = note.strip() or None
    with db.get_connection() as conn:
        sid = ledger_service.create_settlement_for_user(
            conn, user_id, note, None, None, received_confirmed=1
        )
    if sid is None:
        return RedirectResponse("/admin/settlements/start?err=no_open", status_code=303)
    return RedirectResponse(f"/admin/settlements/{sid}/pdf", status_code=303)


@router.get("/settlements/{settlement_id}/xlsx")
def admin_settlement_xlsx(request: Request, settlement_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        header = ledger_service.settlement_header(conn, settlement_id)
        if not header:
            raise HTTPException(status_code=404)
        lines = ledger_service.settlement_lines(conn, settlement_id)
    stem = _settlement_filename_stem(header)
    data = build_xlsx_bytes(header, lines)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _attachment_disposition(stem, ".xlsx")},
    )


@router.get("/settlements/{settlement_id}/pdf")
def admin_settlement_pdf(request: Request, settlement_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        header = ledger_service.settlement_header(conn, settlement_id)
        if not header:
            raise HTTPException(status_code=404)
        lines = ledger_service.settlement_lines(conn, settlement_id)
    stem = _settlement_filename_stem(header)
    data = build_pdf_bytes(header, lines)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": _attachment_disposition(stem, ".pdf")},
    )
