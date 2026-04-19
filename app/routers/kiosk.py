from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app.ledger_service import add_purchase, last_settlement, user_balance_cents
from app.templates_env import TEMPLATES

router = APIRouter(tags=["kiosk"])


@router.get("/", response_class=HTMLResponse)
def kiosk_home(request: Request) -> HTMLResponse:
    with db.get_connection() as conn:
        groups = db.fetch_all(conn, "SELECT id, name FROM user_groups ORDER BY name")
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/groups.html",
        {"groups": groups, "title": "Kiosk"},
    )


@router.get("/g/{group_id}", response_class=HTMLResponse)
def kiosk_group(request: Request, group_id: int) -> HTMLResponse:
    with db.get_connection() as conn:
        g = db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (group_id,))
        if not g:
            raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
        users = db.fetch_all(
            conn,
            "SELECT id, name FROM users WHERE group_id = ? ORDER BY name",
            (group_id,),
        )
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/members.html",
        {"group": g, "users": users, "title": g["name"]},
    )


@router.get("/u/{user_id}", response_class=HTMLResponse)
def kiosk_user(request: Request, user_id: int) -> HTMLResponse:
    with db.get_connection() as conn:
        u = db.fetch_one(
            conn,
            """
            SELECT u.id, u.name, u.group_id, g.name AS group_name
            FROM users u
            JOIN user_groups g ON g.id = u.group_id
            WHERE u.id = ?
            """,
            (user_id,),
        )
        if not u:
            raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
        balance = user_balance_cents(conn, user_id)
        last_s = last_settlement(conn, user_id)
        categories = db.fetch_all(
            conn,
            "SELECT id, name FROM product_categories ORDER BY sort_order, name",
        )
        products_by_cat: list[dict] = []
        for c in categories:
            prods = db.fetch_all(
                conn,
                """
                SELECT id, name, price_cents
                FROM products
                WHERE category_id = ? AND active = 1
                ORDER BY name
                """,
                (c["id"],),
            )
            products_by_cat.append({"category": c, "products": prods})
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/user.html",
        {
            "user": u,
            "balance_cents": balance,
            "last_settlement": last_s,
            "products_by_cat": products_by_cat,
            "title": u["name"],
        },
    )


@router.post("/u/{user_id}/add")
def kiosk_add(
    request: Request,
    user_id: int,
    product_id: int = Form(...),
) -> RedirectResponse:
    with db.get_connection() as conn:
        u = db.fetch_one(conn, "SELECT id FROM users WHERE id = ?", (user_id,))
        if not u:
            raise HTTPException(status_code=404)
        p = db.fetch_one(
            conn,
            """
            SELECT id, name, price_cents, active
            FROM products WHERE id = ? AND active = 1
            """,
            (product_id,),
        )
        if not p:
            raise HTTPException(status_code=400, detail="Artikel ungültig")
        desc = f'{p["name"]} (x1)'
        add_purchase(conn, user_id, int(p["id"]), desc, int(p["price_cents"]))
    return RedirectResponse(url=f"/u/{user_id}", status_code=303)
