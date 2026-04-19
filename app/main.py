from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_secret_key
from app import db
from app import debt_thresholds
from app import kiosk_notice
from app import ledger_service
from app.db import init_db
from app.routers import admin, kiosk


def _last_sync_label() -> str:
    git_dir = Path(__file__).resolve().parent.parent / ".git"
    fetch_head = git_dir / "FETCH_HEAD"
    try:
        if fetch_head.exists():
            ts = datetime.fromtimestamp(fetch_head.stat().st_mtime)
            return ts.strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    return "unbekannt"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Termux-Shopkasse", lifespan=lifespan)


@app.middleware("http")
async def attach_kiosk_notice(request: Request, call_next):
    try:
        request.state.kiosk_notice = kiosk_notice.get_display_text()
    except Exception:
        request.state.kiosk_notice = kiosk_notice.DEFAULT_KIOSK_NOTICE
    request.state.last_sync_label = _last_sync_label()
    return await call_next(request)


@app.middleware("http")
async def attach_admin_debt_alerts(request: Request, call_next):
    request.state.admin_debt_alert_count = 0
    path = request.url.path
    if path.startswith("/admin") and path not in ("/admin/login", "/admin/setup"):
        try:
            if request.session.get("admin_user"):
                try:
                    with db.get_connection() as conn:
                        _t1, _t2, t3 = debt_thresholds.get_thresholds(conn)
                        request.state.admin_debt_alert_count = (
                            ledger_service.count_users_open_balance_gte(conn, t3)
                        )
                except Exception:
                    request.state.admin_debt_alert_count = 0
        except Exception:
            request.state.admin_debt_alert_count = 0
    return await call_next(request)


# Zuletzt registriert = äußerste Schicht: Session steht beim Aufruf der inneren HTTP-Middleware bereit.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_secret_key(),
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
)


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(kiosk.router)
app.include_router(admin.router)
