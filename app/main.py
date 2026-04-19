from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_secret_key
from app.db import init_db
from app import kiosk_notice
from app.routers import admin, kiosk


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Termux-Vertrauenskasse", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=get_secret_key(),
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
)


@app.middleware("http")
async def attach_kiosk_notice(request: Request, call_next):
    request.state.kiosk_notice = kiosk_notice.get_display_text()
    return await call_next(request)


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(kiosk.router)
app.include_router(admin.router)
