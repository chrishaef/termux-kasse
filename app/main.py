from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import io
from pathlib import Path
import re
import subprocess
import time

import qrcode
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from qrcode.image.svg import SvgPathImage
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_secret_key
from app import backup_service
from app import db
from app import debt_thresholds
from app import kiosk_notice
from app import ledger_service
from app import system_settings
from app.db import init_db
from app.routers import admin, kiosk

REPO_URL = "https://github.com/chrishaef/termux-kasse"
APP_STARTED_AT = datetime.now()
_FRESHNESS_CACHE_TTL_SECONDS = 60.0
_freshness_cache_checked_at = 0.0
_freshness_cache_label = "unknown"
_freshness_cache_online = False


def _git_version_label(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "tag", "--sort=-v:refname"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        tags = [line.strip() for line in (out.stdout or "").splitlines() if line.strip()]
        version_tag = None
        for tag in tags:
            if re.fullmatch(r"[vV]?\d+\.\d+\.\d+", tag):
                version_tag = tag
                break
        if not version_tag:
            return "unbekannt"
        return re.sub(r"^[vV]", "", version_tag)
    except Exception:
        return "unbekannt"


def _git_commit_short(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        sha = (out.stdout or "").strip()
        return sha if sha else "unbekannt"
    except Exception:
        return "unbekannt"


def _commit_freshness_label(root: Path) -> str:
    global _freshness_cache_checked_at
    global _freshness_cache_label
    global _freshness_cache_online
    now = time.monotonic()
    if (now - _freshness_cache_checked_at) < _FRESHNESS_CACHE_TTL_SECONDS:
        return _freshness_cache_label
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        origin_main = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        head_sha = (head.stdout or "").strip()
        remote_line = (origin_main.stdout or "").strip()
        remote_sha = remote_line.split()[0] if remote_line else ""
        if head.returncode != 0 or origin_main.returncode != 0 or not head_sha or not remote_sha:
            _freshness_cache_label = "unknown"
            _freshness_cache_online = False
        else:
            _freshness_cache_label = "latest" if head_sha == remote_sha else "outdated"
            _freshness_cache_online = True
    except Exception:
        _freshness_cache_label = "unknown"
        _freshness_cache_online = False
    _freshness_cache_checked_at = now
    return _freshness_cache_label


def _last_sync_at(root: Path) -> datetime | None:
    sync_file = root / ".last_sync"
    git_dir = root / ".git"
    try:
        if sync_file.exists():
            txt = sync_file.read_text(encoding="utf-8").strip()
            if txt:
                try:
                    return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
        candidates = [
            git_dir / "FETCH_HEAD",
            git_dir / "refs" / "remotes" / "origin" / "HEAD",
            git_dir / "refs" / "remotes" / "origin" / "main",
            git_dir / "logs" / "refs" / "remotes" / "origin" / "HEAD",
            git_dir / "logs" / "refs" / "remotes" / "origin" / "main",
        ]
        existing = [p for p in candidates if p.exists()]
        if existing:
            newest = max(existing, key=lambda p: p.stat().st_mtime)
            return datetime.fromtimestamp(newest.stat().st_mtime)
    except Exception:
        return None
    return None


def _sync_labels() -> tuple[str, str, str]:
    root = Path(__file__).resolve().parent.parent
    version = _git_version_label(root)
    ts = _last_sync_at(root)
    if ts is None:
        return version, f"{version} - unbekannt", "unbekannt"
    return version, f"{version} - {ts.strftime('%d%m%y')}", ts.strftime("%d.%m.%y")


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
    root = Path(__file__).resolve().parent.parent
    version_label, last_sync_label, last_sync_at_label = _sync_labels()
    request.state.version_label = version_label
    request.state.version_commit_label = f"{version_label} ({_git_commit_short(root)})"
    request.state.version_status_label = _commit_freshness_label(root)
    request.state.remote_online = _freshness_cache_online
    request.state.last_sync_label = last_sync_label
    request.state.last_sync_at_label = last_sync_at_label
    request.state.system_started_label = APP_STARTED_AT.strftime("%d.%m.%y %H.%M")
    request.state.repo_url = REPO_URL
    return await call_next(request)


@app.middleware("http")
async def attach_system_timeouts(request: Request, call_next):
    try:
        with db.get_connection() as conn:
            request.state.system_timeouts = system_settings.get_timeout_settings(conn)
    except Exception:
        request.state.system_timeouts = system_settings.default_timeout_settings()
    return await call_next(request)


@app.middleware("http")
async def ensure_weekly_backup(request: Request, call_next):
    try:
        if not request.url.path.startswith("/static/"):
            backup_service.maybe_create_weekly_backup()
    except Exception:
        pass
    return await call_next(request)


@app.middleware("http")
async def auto_logout_admin_outside_panel(request: Request, call_next):
    path = request.url.path
    try:
        is_admin_logged_in = bool(request.session.get("admin_user"))
    except Exception:
        is_admin_logged_in = False
    if is_admin_logged_in:
        accept = (request.headers.get("accept") or "").lower()
        is_html_navigation = request.method == "GET" and "text/html" in accept
        if is_html_navigation and not path.startswith("/admin"):
            request.session.clear()
    return await call_next(request)


@app.middleware("http")
async def attach_admin_debt_alerts(request: Request, call_next):
    request.state.admin_debt_alert_count = 0
    path = request.url.path
    if path.startswith("/admin") and path != "/admin/login":
        try:
            if request.session.get("admin_user"):
                try:
                    with db.get_connection() as conn:
                        request.state.admin_debt_alert_count = ledger_service.count_users_over_warnstufe_3(conn)
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


@app.get("/repo/qr.svg")
def repo_qr_svg() -> Response:
    buf = io.BytesIO()
    img = qrcode.make(REPO_URL, image_factory=SvgPathImage, box_size=8, border=2)
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")

app.include_router(kiosk.router)
app.include_router(admin.router)
