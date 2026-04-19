from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db
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
    return TEMPLATES.TemplateResponse(
        request,
        "admin/dashboard.html",
        {"title": "Admin", "stats": stats},
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
        users = db.fetch_all(
            conn,
            """
            SELECT u.id, u.name, g.id AS group_id, g.name AS group_name
            FROM users u
            JOIN user_groups g ON g.id = u.group_id
            ORDER BY g.name, u.name
            """,
        )
        groups = db.fetch_all(conn, "SELECT id, name FROM user_groups ORDER BY name")
    return TEMPLATES.TemplateResponse(
        request,
        "admin/users.html",
        {"title": "Nutzer", "users": users, "groups": groups},
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
        "admin/settlements.html",
        {"title": "Abrechnungen", "settlements": settlements, "users": users},
    )


@router.post("/settlements")
def admin_settlements_create(
    request: Request,
    user_id: int = Form(...),
    note: str = Form(""),
    period_start: str = Form(""),
    period_end: str = Form(""),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    ps = period_start.strip() or None
    pe = period_end.strip() or None
    note = note.strip() or None
    with db.get_connection() as conn:
        sid = ledger_service.create_settlement_for_user(conn, user_id, note, ps, pe)
    if sid is None:
        return RedirectResponse("/admin/settlements?err=no_open", status_code=303)
    return RedirectResponse(f"/admin/settlements", status_code=303)


@router.get("/settlements/{settlement_id}/xlsx")
def admin_settlement_xlsx(request: Request, settlement_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        header = ledger_service.settlement_header(conn, settlement_id)
        if not header:
            raise HTTPException(status_code=404)
        lines = ledger_service.settlement_lines(conn, settlement_id)
    data = build_xlsx_bytes(header, lines)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="abrechnung_{settlement_id}.xlsx"'},
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
    data = build_pdf_bytes(header, lines)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="abrechnung_{settlement_id}.pdf"'},
    )
