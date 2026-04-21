from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app import debt_thresholds
from app import ledger_service
from app.ledger_service import add_purchase, last_settlement, user_balance_cents
from app.templates_env import TEMPLATES

router = APIRouter(tags=["kiosk"])


@router.get("/", response_class=HTMLResponse)
def kiosk_home(request: Request) -> HTMLResponse:
    with db.get_connection() as conn:
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/groups.html",
        {"groups": groups, "title": "Kiosk"},
    )


@router.get("/top-ten", response_class=HTMLResponse)
def kiosk_top_ten(request: Request) -> HTMLResponse:
    with db.get_connection() as conn:
        rows = ledger_service.top_ten_active_users(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/top_ten.html",
        {"title": "Top Ten", "rows": rows},
    )


@router.get("/preisliste", response_class=HTMLResponse)
def kiosk_preisliste(request: Request) -> HTMLResponse:
    with db.get_connection() as conn:
        products = db.fetch_all(
            conn,
            """
            SELECT name, price_cents
            FROM products
            WHERE active = 1
            ORDER BY sort_order, name COLLATE NOCASE
            """,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/preisliste.html",
        {"title": "Preisliste", "products": products},
    )


@router.get("/g/{group_id}", response_class=HTMLResponse)
def kiosk_group(request: Request, group_id: int) -> HTMLResponse:
    with db.get_connection() as conn:
        g = db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (group_id,))
        if not g:
            raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")
        users = db.fetch_all(
            conn,
            """
            SELECT id, name FROM users
            WHERE group_id = ?
            ORDER BY sort_order, name COLLATE NOCASE
            """,
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
        t1, t2, t3 = debt_thresholds.get_thresholds(conn)
        m1, m2, m3 = debt_thresholds.get_threshold_messages(conn)
        debt_reminder_level = debt_thresholds.reminder_level(balance, t1, t2, t3)
        debt_message = ""
        if debt_reminder_level == 1:
            debt_message = m1
        elif debt_reminder_level == 2:
            debt_message = m2
        elif debt_reminder_level == 3:
            debt_message = m3
        last_s = last_settlement(conn, user_id)
        products = db.fetch_all(
            conn,
            """
            SELECT id, name, price_cents
            FROM products
            WHERE active = 1
            ORDER BY sort_order, name COLLATE NOCASE
            """,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "kiosk/user.html",
        {
            "user": u,
            "balance_cents": balance,
            "display_balance_cents": -balance,
            "debt_reminder_level": debt_reminder_level,
            "debt_message": debt_message,
            "debt_threshold_1": t1,
            "debt_threshold_2": t2,
            "debt_threshold_3": t3,
            "last_settlement": last_s,
            "products": products,
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


@router.get("/egg/flappy", response_class=HTMLResponse)
def kiosk_flappy_easter_egg(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
        request,
        "kiosk/flappy.html",
        {"title": "Flappy"},
    )
