from __future__ import annotations

import time

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app import debt_thresholds
from app import ledger_service
from app.ledger_service import add_purchase, last_settlement, oldest_open_age_days, user_balance_cents
from app.templates_env import TEMPLATES

router = APIRouter(tags=["kiosk"])

UNDO_WINDOW_MS = 3000


def _clear_undo_session(request: Request) -> None:
    try:
        request.session.pop("kiosk_undo", None)
    except Exception:
        pass


def _get_active_undo(request: Request, user_id: int) -> dict | None:
    try:
        data = request.session.get("kiosk_undo")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("user_id") or 0) != int(user_id):
        return None
    entry_id = int(data.get("entry_id") or 0)
    expires_ms = int(data.get("expires_ms") or 0)
    now_ms = int(time.time() * 1000)
    if entry_id <= 0 or expires_ms <= now_ms:
        _clear_undo_session(request)
        return None
    return {"entry_id": entry_id, "expires_ms": expires_ms, "remaining_ms": max(0, expires_ms - now_ms)}


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
    undo_active = _get_active_undo(request, user_id) if request.query_params.get("undo") == "1" else None
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
        d1, d2, d3 = debt_thresholds.get_age_thresholds(conn)
        m1, m2, m3 = debt_thresholds.get_threshold_messages(conn)
        age_days = oldest_open_age_days(conn, user_id)
        debt_reminder_level = debt_thresholds.reminder_level(balance, t1, t2, t3, age_days, d1, d2, d3)
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
            "undo_active": undo_active,
            "undone": request.query_params.get("undone") == "1",
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
        entry_id = add_purchase(conn, user_id, int(p["id"]), desc, int(p["price_cents"]))

    try:
        now_ms = int(time.time() * 1000)
        request.session["kiosk_undo"] = {
            "user_id": int(user_id),
            "entry_id": int(entry_id),
            "expires_ms": now_ms + UNDO_WINDOW_MS,
        }
    except Exception:
        pass
    return RedirectResponse(url=f"/u/{user_id}?undo=1", status_code=303)


@router.post("/u/{user_id}/undo")
def kiosk_undo(request: Request, user_id: int, entry_id: int = Form(...)) -> RedirectResponse:
    active = _get_active_undo(request, user_id)
    if not active or int(active["entry_id"]) != int(entry_id):
        _clear_undo_session(request)
        return RedirectResponse(url=f"/u/{user_id}", status_code=303)

    with db.get_connection() as conn:
        row = db.fetch_one(
            conn,
            """
            SELECT id FROM ledger_entries
            WHERE id = ? AND user_id = ? AND settlement_id IS NULL
            """,
            (int(entry_id), int(user_id)),
        )
        if row:
            conn.execute("DELETE FROM ledger_entries WHERE id = ?", (int(entry_id),))
    _clear_undo_session(request)
    return RedirectResponse(url=f"/u/{user_id}?undone=1", status_code=303)


@router.get("/egg/flappy", response_class=HTMLResponse)
def kiosk_flappy_easter_egg(request: Request) -> HTMLResponse:
        return TEMPLATES.TemplateResponse(
        request,
        "kiosk/flappy.html",
        {"title": "Flappy"},
    )
