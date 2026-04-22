from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import subprocess
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from app import admin_auth
from app import backup_service
from app import db
from app import debt_thresholds
from app import kiosk_notice
from app import ledger_service
from app import sort_order_util
from app import system_settings
from app.config import data_dir, db_path, read_master_password, year_end_exports_dir
from app.db import init_db
from app.export_service import (
    build_pdf_bytes,
    build_statistics_pdf_bytes,
    build_statistics_xlsx_bytes,
    build_xlsx_bytes,
    build_year_end_pdf_bytes,
    build_year_end_xlsx_bytes,
)
from app.templates_env import TEMPLATES

router = APIRouter(prefix="/admin", tags=["admin"])


def _backup_archive_dir() -> Path:
    return backup_service.backup_archive_dir()


def _backup_archive_list() -> list[dict]:
    return backup_service.backup_archive_list()


def _backup_archive_prune() -> None:
    backup_service.backup_archive_prune()


def _redirect_login(request: Request) -> Optional[RedirectResponse]:
    if not request.session.get("admin_user"):
        return RedirectResponse("/admin/login", status_code=303)
    return None


def _trigger_background_update() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    run_script = root / "run.sh"
    if not run_script.exists():
        raise FileNotFoundError("run.sh nicht gefunden")
    log_path = root / "update-trigger.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n=== Update ausgelöst: {datetime.now().isoformat()} ===\n")
        log_file.flush()
        subprocess.Popen(
            ["bash", str(run_script)],
            cwd=str(root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def _system_update_precheck() -> dict[str, str | bool]:
    root = Path(__file__).resolve().parent.parent.parent
    installed_version = "unbekannt"
    installed_commit = "unbekannt"
    installed_head_full = ""
    try:
        version = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        vtag = (version.stdout or "").strip()
        if vtag:
            installed_version = re.sub(r"^[vV]", "", vtag)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=1.5,
        )
        installed_head_full = (head.stdout or "").strip()
        if installed_head_full:
            installed_commit = installed_head_full[:7]
    except Exception:
        pass

    online = False
    latest_version = "unbekannt"
    latest_commit = "unbekannt"
    latest_head_full = ""
    try:
        remote_tags = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", "origin"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=2.5,
        )
        best_tag: tuple[int, int, int] | None = None
        best_version = "unbekannt"
        for raw_line in (remote_tags.stdout or "").splitlines():
            parts = raw_line.strip().split()
            if len(parts) != 2:
                continue
            ref = parts[1]
            m = re.fullmatch(r"refs/tags/v?(\d+)\.(\d+)\.(\d+)", ref)
            if not m:
                continue
            key = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if best_tag is None or key > best_tag:
                best_tag = key
                best_version = f"{key[0]}.{key[1]}.{key[2]}"
        if best_tag is not None:
            latest_version = best_version

        remote = subprocess.run(
            ["git", "ls-remote", "origin", "refs/heads/main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=2.5,
        )
        line = (remote.stdout or "").strip()
        sha = line.split()[0] if line else ""
        if remote.returncode == 0 and sha:
            online = True
            latest_head_full = sha
            latest_commit = sha[:7]
    except Exception:
        online = False
        latest_commit = "unbekannt"

    update_available = bool(
        online and installed_head_full and latest_head_full and installed_head_full != latest_head_full
    )
    return {
        "online": online,
        "online_label": "Ja" if online else "Nein",
        "online_badge": "online" if online else "offline",
        "installed_version_commit": f"{installed_version} ({installed_commit})",
        "latest_version_commit": f"{latest_version} ({latest_commit})",
        "update_available": update_available,
    }


def _read_update_log_snippet(max_lines: int = 12) -> list[str]:
    root = Path(__file__).resolve().parent.parent.parent
    log_path = root / "update-trigger.log"
    try:
        if not log_path.exists():
            return []
        lines = [line.rstrip("\r\n") for line in log_path.read_text(encoding="utf-8").splitlines()]
        if not lines:
            return []
        return lines[-max_lines:]
    except Exception:
        return []


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


def _year_end_export_stem(created_iso: str) -> str:
    s = (created_iso or "")[:19].replace(":", "-")
    s = _FN_UNSAFE.sub("_", s)
    return f"Jahresabschluss_{s}" if s else "Jahresabschluss"


def _attachment_disposition(stem: str, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    full = f"{stem}{ext}"
    ascii_fallback = full.encode("ascii", "replace").decode("ascii").replace("?", "_")[:180]
    if not ascii_fallback.strip():
        ascii_fallback = f"abrechnung{ext}"
    enc = quote(full, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{enc}'


def _parse_date_input(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Datum ungültig (YYYY-MM-DD)")
    return dt.strftime("%Y-%m-%dT00:00:00")


def _parse_date_end_input(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Datum ungültig (YYYY-MM-DD)")
    end = dt + timedelta(days=1) - timedelta(seconds=1)
    return end.strftime("%Y-%m-%dT%H:%M:%S")


@router.get("/login", response_class=HTMLResponse)
def admin_login_form(request: Request) -> Response:
    if request.session.get("admin_user"):
        return RedirectResponse("/admin", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/login.html",
        {"title": "Admin-Login"},
    )


@router.post("/login")
def admin_login_post(
    request: Request,
    password: str = Form(...),
) -> Response:
    with db.get_connection() as conn:
        ok, is_master = admin_auth.verify_admin_password(conn, password)
    if not ok:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/login.html",
            {"title": "Admin-Login", "error": "Passwort ungültig"},
            status_code=401,
        )
    request.session["admin_user"] = "master" if is_master else "admin"
    request.session["admin_master"] = bool(is_master)
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout")
def admin_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/preisliste", status_code=303)


@router.get("/password", response_class=HTMLResponse)
def admin_password_form(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    return TEMPLATES.TemplateResponse(
        request,
        "admin/password.html",
        {
            "title": "Passwort ändern",
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/password")
def admin_password_post(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    new_password2: str = Form(...),
) -> Response:
    if (r := _redirect_login(request)):
        return r
    if not new_password or len(new_password) < 4:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/password.html",
            {
                "title": "Passwort ändern",
                "error": "Neues Passwort muss mindestens 4 Zeichen haben.",
            },
            status_code=400,
        )
    if new_password != new_password2:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/password.html",
            {
                "title": "Passwort ändern",
                "error": "Neue Passwörter stimmen nicht überein.",
            },
            status_code=400,
        )
    with db.get_connection() as conn:
        ok, _is_master = admin_auth.verify_admin_password(conn, old_password)
        if not ok:
            return TEMPLATES.TemplateResponse(
                request,
                "admin/password.html",
                {
                    "title": "Passwort ändern",
                    "error": "Altes Passwort falsch.",
                },
                status_code=400,
            )
        admin_auth.set_regular_password(conn, new_password)
    return RedirectResponse("/admin/password?saved=1", status_code=303)


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        stats = {
            "groups": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM user_groups", ())["c"],
            "users": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM users", ())["c"],
            "products": db.fetch_one(conn, "SELECT COUNT(*) AS c FROM products", ())["c"],
        }
        finance = ledger_service.finance_overview(conn)
        today_row = db.fetch_one(
            conn,
            """
            SELECT
                COUNT(*) AS entries_count,
                COALESCE(SUM(amount_cents), 0) AS total_cents
            FROM ledger_entries
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
            """,
            (),
        )
        last_auto_backup_at = backup_service.get_last_existing_auto_backup_at()

    today_entries_count = int(today_row["entries_count"]) if today_row else 0
    today_total_cents = int(today_row["total_cents"]) if today_row else 0
    if last_auto_backup_at:
        next_due = last_auto_backup_at + timedelta(days=backup_service.AUTO_BACKUP_INTERVAL_DAYS)
        remaining_days = max(0, (next_due.date() - datetime.now().date()).days)
        auto_backup_label = last_auto_backup_at.strftime("%d.%m.%y")
        auto_backup_next_label = f"in {remaining_days} Tag{'en' if remaining_days != 1 else ''}"
    else:
        auto_backup_label = "noch nicht erfolgt"
        auto_backup_next_label = "sofort fällig"

    usage = shutil.disk_usage(str(data_dir()))
    free_gb = usage.free / (1024**3)
    used_gb = usage.used / (1024**3)
    disk_free_used_label = f"{free_gb:.1f} GB frei / {used_gb:.1f} GB belegt"

    return TEMPLATES.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "title": "Admin",
            "stats": stats,
            "finance": finance,
            "telemetry_extra": {
                "auto_backup_label": auto_backup_label,
                "auto_backup_next_label": auto_backup_next_label,
                "today_entries_count": today_entries_count,
                "today_total_cents": today_total_cents,
                "disk_free_used_label": disk_free_used_label,
            },
        },
    )


@router.post("/system-update")
def admin_system_update_start(request: Request, master_password: str = Form("")) -> Response:
    if (r := _redirect_login(request)):
        return r
    master_password = (master_password or "").strip()
    precheck = _system_update_precheck()
    update_log_lines = _read_update_log_snippet()
    if read_master_password() is None:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/system_update.html",
            {
                "title": "System-Update",
                "precheck": precheck,
                "update_log_lines": update_log_lines,
                "err": "nomaster",
                "started": False,
            },
            status_code=400,
        )
    if not admin_auth.is_master_password(master_password):
        return TEMPLATES.TemplateResponse(
            request,
            "admin/system_update.html",
            {
                "title": "System-Update",
                "precheck": precheck,
                "update_log_lines": update_log_lines,
                "err": "master",
                "started": False,
            },
            status_code=400,
        )
    try:
        _trigger_background_update()
        return TEMPLATES.TemplateResponse(
            request,
            "admin/system_update.html",
            {
                "title": "System-Update",
                "precheck": precheck,
                "update_log_lines": update_log_lines,
                "started": True,
                "err": None,
            },
        )
    except Exception:
        return TEMPLATES.TemplateResponse(
            request,
            "admin/system_update.html",
            {
                "title": "System-Update",
                "precheck": precheck,
                "update_log_lines": update_log_lines,
                "err": "start",
                "started": False,
            },
            status_code=500,
        )


@router.get("/system-update", response_class=HTMLResponse)
def admin_system_update_page(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    precheck = _system_update_precheck()
    master_ok = bool(read_master_password())
    update_log_lines = _read_update_log_snippet()
    return TEMPLATES.TemplateResponse(
        request,
        "admin/system_update.html",
        {
            "title": "System-Update",
            "precheck": precheck,
            "update_log_lines": update_log_lines,
            "master_configured": master_ok,
            "err": None,
            "started": False,
        },
    )


def _is_valid_sqlite_file(path: Path) -> bool:
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA schema_version").fetchone()
        return True
    except Exception:
        return False


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _replace_with_retry(src: Path, dst: Path, retries: int = 8, delay_s: float = 0.05) -> None:
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            src.replace(dst)
            return
        except PermissionError as ex:
            last_err = ex
            time.sleep(delay_s)
    if last_err:
        raise last_err


def _sqlite_copy_into(src_path: Path, dst_path: Path) -> None:
    with sqlite3.connect(str(src_path)) as src_conn:
        with sqlite3.connect(str(dst_path)) as dst_conn:
            src_conn.backup(dst_conn)


def _build_backup_manifest(db_file: Path, exports_dir: Path, created_at: str) -> dict:
    return backup_service._build_backup_manifest(
        db_file,
        exports_dir,
        created_at,
        automatic=False,
    )


def _validate_backup_manifest(raw: bytes, zip_names: set[str]) -> bool:
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    if data.get("format") != "kasse-system-backup":
        return False
    files = data.get("files")
    if not isinstance(files, dict):
        return False
    db_info = files.get("db")
    if not isinstance(db_info, dict):
        return False
    if db_info.get("path") != "kasse.db":
        return False
    return "kasse.db" in zip_names


def _parse_preview_payload(data: bytes) -> dict:
    if not data:
        raise ValueError("empty")
    if data.startswith(b"SQLite format 3\x00"):
        return {"kind": "legacy_db", "message": "Legacy-Backup (.db) erkannt."}
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = set(zf.namelist())
            if "kasse.db" not in names:
                raise ValueError("invalid")
            manifest = None
            if "manifest.json" in names:
                raw = zf.read("manifest.json")
                if not _validate_backup_manifest(raw, names):
                    raise ValueError("invalid_manifest")
                manifest = json.loads(raw.decode("utf-8"))
            year_end_files = sorted(
                name
                for name in names
                if name.startswith("jahresabschluss/") and not name.endswith("/")
            )
            return {
                "kind": "system_zip",
                "has_manifest": bool(manifest),
                "manifest_created_at": (manifest or {}).get("created_at"),
                "db_path": ((manifest or {}).get("files") or {}).get("db", {}).get("path", "kasse.db"),
                "year_end_files": year_end_files,
            }
    except zipfile.BadZipFile as ex:
        raise ValueError("invalid_zip") from ex


@router.get("/backup", response_class=HTMLResponse)
def admin_backup_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    db_file = db_path()
    mp = read_master_password()
    master_ok = bool(mp and str(mp).strip())
    archive = _backup_archive_list()
    last_auto_backup_at = backup_service.get_last_existing_auto_backup_at()
    return TEMPLATES.TemplateResponse(
        request,
        "admin/backup.html",
        {
            "title": "Sicherung",
            "db_exists": db_file.exists(),
            "saved": request.query_params.get("saved") == "1",
            "created": request.query_params.get("created") == "1",
            "error": request.query_params.get("err") == "invalid",
            "reset_ok": request.query_params.get("reset") == "1",
            "master_configured": master_ok,
            "reset_err": request.query_params.get("reset_err"),
            "archive": archive,
            "archive_deleted": request.query_params.get("deleted") == "1",
            "last_auto_backup_at": last_auto_backup_at,
        },
    )


@router.get("/backup/export")
def admin_backup_export(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    if not db_path().exists():
        raise HTTPException(status_code=404, detail="Datenbank nicht gefunden")
    backup_service.create_system_backup_archive()
    return RedirectResponse("/admin/backup?created=1", status_code=303)


@router.get("/backup/archive/{filename}")
def admin_backup_archive_download(request: Request, filename: str) -> Response:
    if (r := _redirect_login(request)):
        return r
    safe = Path(filename).name
    if not safe.endswith(".zip"):
        raise HTTPException(status_code=404)
    path = _backup_archive_dir() / safe
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path=path, media_type="application/zip", filename=safe)


@router.post("/backup/archive/{filename}/delete")
def admin_backup_archive_delete(request: Request, filename: str) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    safe = Path(filename).name
    if not safe.endswith(".zip"):
        raise HTTPException(status_code=404)
    path = _backup_archive_dir() / safe
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return RedirectResponse("/admin/backup?deleted=1", status_code=303)


@router.post("/backup/preview")
def admin_backup_preview(request: Request, backup_file: UploadFile = File(...)) -> Response:
    if (r := _redirect_login(request)):
        return r
    try:
        payload = _parse_preview_payload(backup_file.file.read())
    except ValueError:
        return Response(content='{"ok":false,"error":"invalid"}', media_type="application/json", status_code=400)
    body = json.dumps({"ok": True, "preview": payload}, ensure_ascii=True)
    return Response(content=body, media_type="application/json")


@router.post("/backup/import")
def admin_backup_import(request: Request, backup_file: UploadFile = File(...)) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    data = backup_file.file.read()
    if not data:
        return RedirectResponse("/admin/backup?err=invalid", status_code=303)

    db_file = db_path()
    exports_dir = year_end_exports_dir()
    data_root = data_dir()
    data_root.mkdir(parents=True, exist_ok=True)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = db_file.with_name(f"{db_file.name}.importing")
    old_file = db_file.with_name(f"{db_file.name}.before-import")
    backup_exports_dir = data_root / "jahresabschluss.before-import"

    db_bytes = data
    imported_exports: list[tuple[str, bytes]] = []
    if data.startswith(b"SQLite format 3\x00"):
        # Legacy fallback: allow importing plain .db backups.
        db_bytes = data
    else:
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                names = set(zf.namelist())
                if "kasse.db" not in names:
                    return RedirectResponse("/admin/backup?err=invalid", status_code=303)
                if "manifest.json" in names:
                    if not _validate_backup_manifest(zf.read("manifest.json"), names):
                        return RedirectResponse("/admin/backup?err=invalid", status_code=303)
                db_bytes = zf.read("kasse.db")
                for name in sorted(names):
                    if not name.startswith("jahresabschluss/") or name.endswith("/"):
                        continue
                    rel = name[len("jahresabschluss/") :].strip()
                    rel = Path(rel).name
                    if not rel:
                        continue
                    imported_exports.append((rel, zf.read(name)))
        except zipfile.BadZipFile:
            return RedirectResponse("/admin/backup?err=invalid", status_code=303)

    try:
        tmp_file.write_bytes(db_bytes)
        if not _is_valid_sqlite_file(tmp_file):
            _safe_unlink(tmp_file)
            return RedirectResponse("/admin/backup?err=invalid", status_code=303)
        if backup_exports_dir.exists():
            for p in backup_exports_dir.glob("*"):
                if p.is_file():
                    _safe_unlink(p)
            backup_exports_dir.rmdir()
        backup_exports_dir.mkdir(parents=True, exist_ok=True)
        if exports_dir.exists():
            for p in exports_dir.glob("*"):
                if p.is_file():
                    (backup_exports_dir / p.name).write_bytes(p.read_bytes())
        used_inplace_copy = False
        if old_file.exists():
            _safe_unlink(old_file)
        if db_file.exists():
            try:
                _replace_with_retry(db_file, old_file)
                _replace_with_retry(tmp_file, db_file)
            except PermissionError:
                used_inplace_copy = True
                if old_file.exists():
                    _safe_unlink(old_file)
                _sqlite_copy_into(tmp_file, db_file)
        else:
            _replace_with_retry(tmp_file, db_file)
        for p in exports_dir.glob("*"):
            if p.is_file():
                p.unlink(missing_ok=True)
        for fname, fbytes in imported_exports:
            (exports_dir / fname).write_bytes(fbytes)
        try:
            init_db()
        except Exception:
            if db_file.exists():
                _safe_unlink(db_file)
            if old_file.exists() and not used_inplace_copy:
                _replace_with_retry(old_file, db_file)
            for p in exports_dir.glob("*"):
                if p.is_file():
                    _safe_unlink(p)
            if backup_exports_dir.exists():
                for p in backup_exports_dir.glob("*"):
                    if p.is_file():
                        (exports_dir / p.name).write_bytes(p.read_bytes())
            raise
    finally:
        if tmp_file.exists():
            _safe_unlink(tmp_file)
        if backup_exports_dir.exists():
            for p in backup_exports_dir.glob("*"):
                if p.is_file():
                    _safe_unlink(p)
            backup_exports_dir.rmdir()
    return RedirectResponse("/admin/backup?saved=1", status_code=303)


@router.post("/backup/reset-transactional")
def admin_backup_reset_transactional(
    request: Request,
    master_password: str = Form(""),
    confirm_reset: str | None = Form(None),
) -> RedirectResponse:
    """Alle Buchungen und Abrechnungen löschen; Nutzer, Gruppen, Artikel bleiben."""
    if (r := _redirect_login(request)):
        return r
    if read_master_password() is None:
        return RedirectResponse("/admin/backup?reset_err=nomaster", status_code=303)
    if not admin_auth.is_master_password(master_password):
        return RedirectResponse("/admin/backup?reset_err=master", status_code=303)
    if confirm_reset not in ("1", "on", "yes", "true"):
        return RedirectResponse("/admin/backup?reset_err=noconfirm", status_code=303)
    with db.get_connection() as conn:
        ledger_service.purge_ledger_and_settlements(conn)
    return RedirectResponse("/admin/backup?reset=1", status_code=303)


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


@router.get("/system-settings", response_class=HTMLResponse)
def admin_system_settings_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        timeouts = system_settings.get_timeout_settings(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/system_settings.html",
        {
            "title": "Systemzeiten",
            "timeouts": timeouts,
            "saved": request.query_params.get("saved") == "1",
            "error": request.query_params.get("err") == "invalid",
        },
    )


@router.post("/system-settings")
def admin_system_settings_post(
    request: Request,
    admin_logout_seconds: str = Form(...),
    kiosk_preisliste_seconds: str = Form(...),
    kiosk_home_seconds: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    try:
        admin_seconds = int((admin_logout_seconds or "").strip())
        preisliste_seconds = int((kiosk_preisliste_seconds or "").strip())
        home_seconds = int((kiosk_home_seconds or "").strip())
    except ValueError:
        return RedirectResponse("/admin/system-settings?err=invalid", status_code=303)
    with db.get_connection() as conn:
        system_settings.save_timeout_settings(
            conn,
            admin_logout_seconds=admin_seconds,
            kiosk_preisliste_seconds=preisliste_seconds,
            kiosk_home_seconds=home_seconds,
        )
    return RedirectResponse("/admin/system-settings?saved=1", status_code=303)


@router.get("/debt-thresholds", response_class=HTMLResponse)
def admin_debt_thresholds_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        t1, t2, t3 = debt_thresholds.get_thresholds(conn)
        d1, d2, d3 = debt_thresholds.get_age_thresholds(conn)
        m1, m2, m3 = debt_thresholds.get_threshold_messages(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/debt_thresholds.html",
        {
            "title": "Ausstands-Warnstufen",
            "t1": t1,
            "t2": t2,
            "t3": t3,
            "t1_eur": _eur_field_from_cents(t1),
            "t2_eur": _eur_field_from_cents(t2),
            "t3_eur": _eur_field_from_cents(t3),
            "d1_days": d1,
            "d2_days": d2,
            "d3_days": d3,
            "m1": m1,
            "m2": m2,
            "m3": m3,
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
    age_threshold_a_days: str = Form(...),
    age_threshold_b_days: str = Form(...),
    age_threshold_c_days: str = Form(...),
    message_1: str = Form(""),
    message_2: str = Form(""),
    message_3: str = Form(""),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    try:
        ca = _parse_price_eur_to_cents(threshold_a_eur)
        cb = _parse_price_eur_to_cents(threshold_b_eur)
        cc = _parse_price_eur_to_cents(threshold_c_eur)
        da = int((age_threshold_a_days or "").strip())
        dbb = int((age_threshold_b_days or "").strip())
        dc = int((age_threshold_c_days or "").strip())
    except ValueError:
        return RedirectResponse("/admin/debt-thresholds?err=invalid", status_code=303)
    with db.get_connection() as conn:
        debt_thresholds.save_thresholds_cents(conn, ca, cb, cc)
        debt_thresholds.save_age_thresholds_days(conn, da, dbb, dc)
        current_m1, current_m2, current_m3 = debt_thresholds.get_threshold_messages(conn)
        debt_thresholds.save_threshold_messages(
            conn,
            message_1.strip() or current_m1,
            message_2.strip() or current_m2,
            message_3.strip() or current_m3,
        )
    return RedirectResponse("/admin/debt-thresholds?saved=1", status_code=303)


@router.get("/groups", response_class=HTMLResponse)
def admin_groups(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
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
        so = sort_order_util.next_sort_order(conn, "user_groups")
        conn.execute(
            "INSERT INTO user_groups (name, sort_order) VALUES (?, ?)",
            (name, so),
        )
    return RedirectResponse("/admin/groups", status_code=303)


@router.post("/groups/{group_id}/sort")
def admin_groups_sort(
    request: Request,
    group_id: int,
    direction: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    if direction not in ("up", "down"):
        return RedirectResponse("/admin/groups", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM user_groups WHERE id = ?", (group_id,))
        if not row:
            raise HTTPException(status_code=404)
        sort_order_util.swap_sort_order(conn, "user_groups", group_id, direction)  # type: ignore[arg-type]
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
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
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


@router.get("/users/over-limit", response_class=HTMLResponse)
def admin_users_over_limit(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        _t1, _t2, t3 = debt_thresholds.get_thresholds(conn)
        _d1, _d2, d3 = debt_thresholds.get_age_thresholds(conn)
        rows = ledger_service.users_over_warnstufe_3_details(conn)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/users_over_limit.html",
        {
            "title": "Nutzer über Warnstufe 3",
            "threshold_3_cents": t3,
            "threshold_3_days": d3,
            "rows": rows,
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
        so = sort_order_util.next_user_sort_order_in_group(conn, group_id)
        conn.execute(
            "INSERT INTO users (group_id, name, sort_order) VALUES (?, ?, ?)",
            (group_id, name, so),
        )
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def admin_users_edit_form(request: Request, user_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        user = db.fetch_one(
            conn,
            "SELECT id, name, group_id FROM users WHERE id = ?",
            (user_id,),
        )
        if not user:
            raise HTTPException(status_code=404)
        open_balance_cents = ledger_service.user_balance_cents(conn, user_id)
        settled_total_cents = ledger_service.total_previously_settled_cents(conn, user_id)
        settlements_count = ledger_service.settlement_count_for_user(conn, user_id)
        row_entries = db.fetch_one(
            conn,
            "SELECT COUNT(*) AS c FROM ledger_entries WHERE user_id = ?",
            (user_id,),
        )
        entries_count = int(row_entries["c"]) if row_entries else 0
        last_s = ledger_service.last_settlement(conn, user_id)
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/users_edit.html",
        {
            "title": "Nutzer bearbeiten",
            "user": user,
            "groups": groups,
            "balance_display_cents": -open_balance_cents,
            "stats": {
                "open_balance_cents": open_balance_cents,
                "settled_total_cents": settled_total_cents,
                "settlements_count": settlements_count,
                "entries_count": entries_count,
                "last_settlement": last_s,
            },
        },
    )


@router.post("/users/{user_id}/edit")
def admin_users_edit_save(
    request: Request,
    user_id: int,
    name: str = Form(...),
    group_id: int = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse(f"/admin/users/{user_id}/edit", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM users WHERE id = ?", (user_id,))
        if not row:
            raise HTTPException(status_code=404)
        conn.execute(
            "UPDATE users SET name = ?, group_id = ? WHERE id = ?",
            (name, group_id, user_id),
        )
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/sort")
def admin_users_sort(
    request: Request,
    user_id: int,
    direction: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    if direction not in ("up", "down"):
        return RedirectResponse("/admin/users", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM users WHERE id = ?", (user_id,))
        if not row:
            raise HTTPException(status_code=404)
        sort_order_util.swap_user_sort_in_group(conn, user_id, direction)  # type: ignore[arg-type]
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
def admin_users_delete(request: Request, user_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/products", response_class=HTMLResponse)
def admin_products(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        products = db.fetch_all(
            conn,
            """
            SELECT id, name, price_cents, active
            FROM products
            ORDER BY sort_order, name COLLATE NOCASE
            """,
        )
    return TEMPLATES.TemplateResponse(
        request,
        "admin/products.html",
        {"title": "Artikel", "products": products},
    )


@router.post("/products")
def admin_products_create(
    request: Request,
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
        so = sort_order_util.next_sort_order(conn, "products")
        conn.execute(
            "INSERT INTO products (name, price_cents, active, sort_order) VALUES (?, ?, 1, ?)",
            (name, cents, so),
        )
    return RedirectResponse("/admin/products", status_code=303)


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
def admin_products_edit_form(request: Request, product_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        product = db.fetch_one(
            conn,
            "SELECT id, name, price_cents, active FROM products WHERE id = ?",
            (product_id,),
        )
        if not product:
            raise HTTPException(status_code=404)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/products_edit.html",
        {
            "title": "Artikel bearbeiten",
            "product": product,
            "price_eur": _eur_field_from_cents(int(product["price_cents"])),
        },
    )


@router.post("/products/{product_id}/edit")
def admin_products_edit_save(
    request: Request,
    product_id: int,
    name: str = Form(...),
    price_eur: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    name = name.strip()
    if not name:
        return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)
    try:
        cents = _parse_price_eur_to_cents(price_eur)
    except ValueError:
        return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM products WHERE id = ?", (product_id,))
        if not row:
            raise HTTPException(status_code=404)
        conn.execute(
            "UPDATE products SET name = ?, price_cents = ? WHERE id = ?",
            (name, cents, product_id),
        )
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/sort")
def admin_products_sort(
    request: Request,
    product_id: int,
    direction: str = Form(...),
) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    if direction not in ("up", "down"):
        return RedirectResponse("/admin/products", status_code=303)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id FROM products WHERE id = ?", (product_id,))
        if not row:
            raise HTTPException(status_code=404)
        sort_order_util.swap_sort_order(conn, "products", product_id, direction)  # type: ignore[arg-type]
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/delete")
def admin_products_delete(request: Request, product_id: int) -> RedirectResponse:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return RedirectResponse("/admin/products", status_code=303)


@router.post("/products/{product_id}/toggle")
def admin_products_toggle(request: Request, product_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        row = db.fetch_one(conn, "SELECT id, active FROM products WHERE id = ?", (product_id,))
        if not row:
            raise HTTPException(status_code=404)
        conn.execute(
            "UPDATE products SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (product_id,),
        )
        updated = db.fetch_one(conn, "SELECT active FROM products WHERE id = ?", (product_id,))
    accepts_json = "application/json" in (request.headers.get("accept") or "").lower()
    fetch_toggle = (request.headers.get("x-requested-with") or "").lower() == "fetch"
    if accepts_json or fetch_toggle:
        return JSONResponse(
            {
                "ok": True,
                "product_id": int(product_id),
                "active": bool(updated and int(updated["active"]) == 1),
            }
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
            SELECT
                s.id,
                s.created_at,
                s.total_cents,
                u.name AS user_name,
                g.name AS group_name,
                'settlement' AS row_type
            FROM settlements s
            JOIN users u ON u.id = s.user_id
            JOIN user_groups g ON g.id = u.group_id
            ORDER BY datetime(s.created_at) DESC
            LIMIT 100
            """,
        )
        year_end_runs = db.fetch_all(
            conn,
            """
            SELECT
                y.id,
                y.created_at,
                y.settlements_sum_cents AS total_cents,
                'Jahresabschluss' AS user_name,
                ('System · ' || y.settlements_count || ' Abrechnungen') AS group_name,
                'year_end' AS row_type
            FROM year_end_runs y
            ORDER BY datetime(y.created_at) DESC
            LIMIT 100
            """,
        )
    rows = sorted(
        [dict(r) for r in settlements] + [dict(r) for r in year_end_runs],
        key=lambda x: str(x.get("created_at") or ""),
        reverse=True,
    )[:100]
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlements.html",
        {"title": "Abrechnungen", "settlements": rows},
    )


@router.get("/settlements/year-end", response_class=HTMLResponse)
def admin_year_end_get(request: Request) -> Response:
    if (r := _redirect_login(request)):
        return r
    mp = read_master_password()
    master_ok = bool(mp and str(mp).strip())
    return TEMPLATES.TemplateResponse(
        request,
        "admin/year_end.html",
        {
            "title": "Jahresabschluss",
            "master_configured": master_ok,
            "err": request.query_params.get("err"),
        },
    )


@router.post("/settlements/year-end")
def admin_year_end_post(
    request: Request,
    master_password: str = Form(""),
    confirm_irreversible: str | None = Form(None),
) -> Response:
    if (r := _redirect_login(request)):
        return r
    if read_master_password() is None:
        return RedirectResponse("/admin/settlements/year-end?err=nomaster", status_code=303)
    if not admin_auth.is_master_password(master_password):
        return RedirectResponse("/admin/settlements/year-end?err=master", status_code=303)
    if confirm_irreversible not in ("1", "on", "yes", "true"):
        return RedirectResponse("/admin/settlements/year-end?err=noconfirm", status_code=303)

    with db.get_connection() as conn:
        snapshot = ledger_service.year_end_snapshot(conn)
    pdf_bytes = build_year_end_pdf_bytes(snapshot)
    xlsx_bytes = build_year_end_xlsx_bytes(snapshot)
    stem = _year_end_export_stem(str(snapshot["created_at_iso"]))
    out_dir = year_end_exports_dir()
    # Keep system storage bounded: remove older year-end archives before writing new ones.
    for old in out_dir.glob("*"):
        if old.is_file():
            old.unlink(missing_ok=True)
    (out_dir / f"{stem}.pdf").write_bytes(pdf_bytes)
    (out_dir / f"{stem}.xlsx").write_bytes(xlsx_bytes)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{stem}.pdf", pdf_bytes)
        zf.writestr(f"{stem}.xlsx", xlsx_bytes)
    zip_bytes = buf.getvalue()
    (out_dir / f"{stem}.zip").write_bytes(zip_bytes)

    with db.get_connection() as conn:
        # Keep only the latest year-end run in history view.
        conn.execute("DELETE FROM year_end_runs")
        conn.execute(
            """
            INSERT INTO year_end_runs (
                created_at, settlements_count, settlements_sum_cents,
                zip_filename, pdf_filename, xlsx_filename
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(snapshot["created_at_iso"]),
                int(snapshot["totals"]["settlements_count"]),
                int(snapshot["totals"]["settlements_sum_cents"]),
                f"{stem}.zip",
                f"{stem}.pdf",
                f"{stem}.xlsx",
            ),
        )
        ledger_service.purge_settled_ledger_and_settlements(conn)

    return RedirectResponse("/admin?year_end=1", status_code=303)


def _year_end_file_response(request: Request, run_id: int, ext: str) -> Response:
    if (r := _redirect_login(request)):
        return r
    col = {"zip": "zip_filename", "pdf": "pdf_filename", "xlsx": "xlsx_filename"}.get(ext)
    if not col:
        raise HTTPException(status_code=404)
    with db.get_connection() as conn:
        row = db.fetch_one(conn, f"SELECT {col} AS filename FROM year_end_runs WHERE id = ?", (run_id,))
    if not row:
        raise HTTPException(status_code=404)
    filename = str(row["filename"] or "").strip()
    if not filename:
        raise HTTPException(status_code=404)
    path = year_end_exports_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archivdatei nicht gefunden")
    media = {
        "zip": "application/zip",
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[ext]
    return FileResponse(path=path, media_type=media, filename=filename)


@router.get("/settlements/year-end/{run_id}/zip")
def admin_year_end_zip(request: Request, run_id: int) -> Response:
    return _year_end_file_response(request, run_id, "zip")


@router.get("/settlements/year-end/{run_id}/pdf")
def admin_year_end_pdf(request: Request, run_id: int) -> Response:
    return _year_end_file_response(request, run_id, "pdf")


@router.get("/settlements/year-end/{run_id}/xlsx")
def admin_year_end_xlsx(request: Request, run_id: int) -> Response:
    return _year_end_file_response(request, run_id, "xlsx")


@router.get("/settlements/start", response_class=HTMLResponse)
def admin_settlement_start_get(
    request: Request,
    group_id: str = "",
    user_id: str = "",
) -> Response:
    if (r := _redirect_login(request)):
        return r
    gid = int(group_id) if group_id.strip().isdigit() else None
    uid = int(user_id) if user_id.strip().isdigit() else None
    with db.get_connection() as conn:
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
        if gid is None and groups:
            gid = int(groups[0]["id"])
        if gid is not None:
            grow = db.fetch_one(conn, "SELECT id FROM user_groups WHERE id = ?", (gid,))
            if not grow:
                raise HTTPException(status_code=404, detail="Nutzergruppe nicht gefunden")
        users = db.fetch_all(
            conn,
            """
            SELECT u.id, u.name, g.name AS group_name
            FROM users u
            JOIN user_groups g ON g.id = u.group_id
            WHERE (? IS NULL OR u.group_id = ?)
            ORDER BY u.sort_order, u.name COLLATE NOCASE
            """,
            (gid, gid),
        )
        if uid is None and users:
            uid = int(users[0]["id"])
        selected_user = None
        selected_balance_cents = 0
        selected_settled_total_cents = 0
        selected_last_settlement = None
        if uid is not None:
            selected_user = db.fetch_one(
                conn,
                """
                SELECT u.id, u.name, g.name AS group_name
                FROM users u
                JOIN user_groups g ON g.id = u.group_id
                WHERE u.id = ? AND (? IS NULL OR u.group_id = ?)
                """,
                (uid, gid, gid),
            )
            if selected_user:
                selected_balance_cents = ledger_service.user_balance_cents(conn, uid)
                selected_settled_total_cents = ledger_service.total_previously_settled_cents(conn, uid)
                selected_last_settlement = ledger_service.last_settlement(conn, uid)
            else:
                uid = None
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlement_start.html",
        {
            "title": "Abrechnung starten",
            "users": users,
            "groups": groups,
            "selected_group_id": gid,
            "selected_user_id": uid,
            "selected_user": selected_user,
            "selected_balance_cents": selected_balance_cents,
            "selected_settled_total_cents": selected_settled_total_cents,
            "selected_last_settlement": selected_last_settlement,
        },
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
        raw_lines = ledger_service.open_ledger_for_user(conn, user_id)
        open_agg = ledger_service.aggregate_ledger_lines(raw_lines)
    if open_cents == 0 or not raw_lines:
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
            "open_agg": open_agg,
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
    return RedirectResponse("/admin?settlement_done=1", status_code=303)


@router.get("/settlements/{settlement_id}/xlsx")
def admin_settlement_xlsx(request: Request, settlement_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    with db.get_connection() as conn:
        header = ledger_service.settlement_header(conn, settlement_id)
        if not header:
            raise HTTPException(status_code=404)
        lines = ledger_service.settlement_lines(conn, settlement_id)
        agg = ledger_service.aggregate_ledger_lines(lines)
    stem = _settlement_filename_stem(header)
    data = build_xlsx_bytes(header, agg)
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
        agg = ledger_service.aggregate_ledger_lines(lines)
    stem = _settlement_filename_stem(header)
    data = build_pdf_bytes(header, agg)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": _attachment_disposition(stem, ".pdf")},
    )


@router.get("/settlements/{settlement_id}/done", response_class=HTMLResponse)
def admin_settlement_done(request: Request, settlement_id: int) -> Response:
    if (r := _redirect_login(request)):
        return r
    return TEMPLATES.TemplateResponse(
        request,
        "admin/settlement_done.html",
        {"title": "Abrechnung erstellt", "settlement_id": settlement_id},
    )


@router.get("/statistics", response_class=HTMLResponse)
def admin_statistics(
    request: Request,
    start: str = "",
    end: str = "",
    group_id: str = "",
) -> Response:
    if (r := _redirect_login(request)):
        return r
    period_start = _parse_date_input(start) if start else None
    period_end = _parse_date_end_input(end) if end else None
    gid = int(group_id) if group_id.strip().isdigit() else None
    with db.get_connection() as conn:
        groups = db.fetch_all(
            conn,
            "SELECT id, name FROM user_groups ORDER BY sort_order, name COLLATE NOCASE",
        )
        group_row = (
            db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (gid,))
            if gid is not None
            else None
        )
        if gid is not None and not group_row:
            raise HTTPException(status_code=404, detail="Nutzergruppe nicht gefunden")
        selected_group_name = str(group_row["name"]) if group_row else None
        totals = ledger_service.period_totals(conn, period_start, period_end, gid)
        user_rows = ledger_service.period_user_toplist(conn, period_start, period_end, gid)
        open_balance_rows = ledger_service.open_balance_toplist(conn, period_start, period_end, gid)
        product_rows = ledger_service.period_product_stats(conn, period_start, period_end, gid)
    return TEMPLATES.TemplateResponse(
        request,
        "admin/statistics.html",
        {
            "title": "Statistik",
            "start": start,
            "end": end,
            "group_id": group_id,
            "selected_group_id": gid,
            "groups": groups,
            "selected_group_name": selected_group_name,
            "totals": totals,
            "user_rows": user_rows,
            "open_balance_rows": open_balance_rows,
            "product_rows": product_rows,
        },
    )


@router.get("/statistics/pdf")
def admin_statistics_pdf(
    request: Request,
    start: str = "",
    end: str = "",
    group_id: str = "",
) -> Response:
    if (r := _redirect_login(request)):
        return r
    period_start = _parse_date_input(start) if start else None
    period_end = _parse_date_end_input(end) if end else None
    gid = int(group_id) if group_id.strip().isdigit() else None
    with db.get_connection() as conn:
        group_row = (
            db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (gid,))
            if gid is not None
            else None
        )
        if gid is not None and not group_row:
            raise HTTPException(status_code=404, detail="Nutzergruppe nicht gefunden")
        selected_group_name = str(group_row["name"]) if group_row else None
        totals = ledger_service.period_totals(conn, period_start, period_end, gid)
        user_rows = [
            dict(r)
            for r in ledger_service.period_user_toplist(conn, period_start, period_end, gid)
        ]
        product_rows = ledger_service.period_product_stats(conn, period_start, period_end, gid)
    data = build_statistics_pdf_bytes(
        period_start, period_end, selected_group_name, totals, user_rows, product_rows
    )
    stem = "Statistik_Zeitraum"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": _attachment_disposition(stem, ".pdf")},
    )


@router.get("/statistics/xlsx")
def admin_statistics_xlsx(
    request: Request,
    start: str = "",
    end: str = "",
    group_id: str = "",
) -> Response:
    if (r := _redirect_login(request)):
        return r
    period_start = _parse_date_input(start) if start else None
    period_end = _parse_date_end_input(end) if end else None
    gid = int(group_id) if group_id.strip().isdigit() else None
    with db.get_connection() as conn:
        group_row = (
            db.fetch_one(conn, "SELECT id, name FROM user_groups WHERE id = ?", (gid,))
            if gid is not None
            else None
        )
        if gid is not None and not group_row:
            raise HTTPException(status_code=404, detail="Nutzergruppe nicht gefunden")
        selected_group_name = str(group_row["name"]) if group_row else None
        totals = ledger_service.period_totals(conn, period_start, period_end, gid)
        user_rows = [
            dict(r)
            for r in ledger_service.period_user_toplist(conn, period_start, period_end, gid)
        ]
        product_rows = ledger_service.period_product_stats(conn, period_start, period_end, gid)
    data = build_statistics_xlsx_bytes(
        period_start, period_end, selected_group_name, totals, user_rows, product_rows
    )
    stem = "Statistik_Zeitraum"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _attachment_disposition(stem, ".xlsx")},
    )
