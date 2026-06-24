from __future__ import annotations

import io
import json
import sqlite3
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from app import db
from app import group_logo_util
from app.config import db_path, year_end_exports_dir

BACKUP_ARCHIVE_KEEP = 25
AUTO_BACKUP_INTERVAL_DAYS = 7
AUTO_BACKUP_RETENTION_DAYS = 28
AUTO_BACKUP_MISSING_GRACE_MINUTES = 5
KEY_LAST_AUTO_BACKUP_AT = "last_auto_backup_at"

_AUTO_BACKUP_LOCK = threading.Lock()


def backup_archive_dir() -> Path:
    path = db_path().parent / "system_backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_archive_list() -> list[dict]:
    items: list[dict] = []
    for path in backup_archive_dir().glob("*.zip"):
        if not path.is_file():
            continue
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "bytes": int(stat.st_size),
                "mtime": float(stat.st_mtime),
            }
        )
    items.sort(key=lambda item: float(item.get("mtime") or 0.0), reverse=True)
    return items


def backup_archive_prune() -> None:
    items = backup_archive_list()
    for item in items[BACKUP_ARCHIVE_KEEP:]:
        try:
            (backup_archive_dir() / str(item["name"])).unlink(missing_ok=True)
        except Exception:
            pass


def _read_backup_manifest(path: Path) -> dict | None:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "manifest.json" not in set(zf.namelist()):
                return None
            raw = zf.read("manifest.json")
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _is_expired_auto_backup(path: Path, now: datetime) -> bool:
    manifest = _read_backup_manifest(path)
    if not manifest or not bool(manifest.get("automatic")):
        return False
    created_raw = str(manifest.get("created_at") or "").strip()
    if not created_raw:
        return False
    try:
        created_at = datetime.fromisoformat(created_raw)
    except ValueError:
        return False
    return now - created_at > timedelta(days=AUTO_BACKUP_RETENTION_DAYS)


def prune_expired_auto_backups(now: datetime | None = None) -> None:
    current = now or datetime.now()
    for item in backup_archive_list():
        path = backup_archive_dir() / str(item["name"])
        if not path.is_file():
            continue
        if not _is_expired_auto_backup(path, current):
            continue
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _latest_auto_backup_at_from_archive() -> datetime | None:
    latest: datetime | None = None
    for item in backup_archive_list():
        path = backup_archive_dir() / str(item["name"])
        if not path.is_file():
            continue
        manifest = _read_backup_manifest(path)
        if not manifest or not bool(manifest.get("automatic")):
            continue
        created_raw = str(manifest.get("created_at") or "").strip()
        if not created_raw:
            continue
        try:
            created_at = datetime.fromisoformat(created_raw)
        except ValueError:
            continue
        if latest is None or created_at > latest:
            latest = created_at
    return latest


def _build_backup_manifest(
    db_file: Path,
    exports_dir: Path,
    created_at: str,
    *,
    automatic: bool,
    purpose: str = "manual",
    source_commit: str | None = None,
) -> dict:
    export_files = [path.name for path in sorted(exports_dir.glob("*")) if path.is_file()]
    logo_dir = group_logo_util.group_logos_dir()
    group_logos: list[dict[str, str | int]] = []
    if logo_dir.is_dir():
        for path in sorted(logo_dir.glob("*.png")):
            if path.is_file():
                group_logos.append(
                    {"path": f"group_logos/{path.name}", "bytes": int(path.stat().st_size)}
                )
    return {
        "format": "kasse-system-backup",
        "version": 1,
        "created_at": created_at,
        "automatic": bool(automatic),
        "purpose": purpose,
        "source_commit": source_commit or "",
        "files": {
            "db": {"path": "kasse.db", "bytes": int(db_file.stat().st_size)},
            "year_end_exports": [
                {"path": f"jahresabschluss/{name}", "bytes": int((exports_dir / name).stat().st_size)}
                for name in export_files
            ],
        },
        "group_logos": group_logos,
    }


def _next_backup_path(stamp: str) -> Path:
    archive_dir = backup_archive_dir()
    first = archive_dir / f"kasse-system-backup-{stamp}.zip"
    if not first.exists():
        return first
    suffix = 2
    while True:
        candidate = archive_dir / f"kasse-system-backup-{stamp}-{suffix}.zip"
        if not candidate.exists():
            return candidate
        suffix += 1


def create_system_backup_archive(
    created_at: datetime | None = None,
    *,
    automatic: bool = False,
    purpose: str | None = None,
    source_commit: str | None = None,
) -> Path | None:
    db_file = db_path()
    if not db_file.exists():
        return None
    created = created_at or datetime.now()
    created_iso = created.isoformat(timespec="seconds")
    stamp = created.strftime("%Y%m%d_%H%M%S")
    exports_dir = year_end_exports_dir()
    manifest = _build_backup_manifest(
        db_file,
        exports_dir,
        created_iso,
        automatic=automatic,
        purpose=purpose or ("automatic" if automatic else "manual"),
        source_commit=source_commit,
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=True, indent=2))
        zf.writestr("kasse.db", db_file.read_bytes())
        for path in sorted(exports_dir.glob("*")):
            if path.is_file():
                zf.write(path, arcname=f"jahresabschluss/{path.name}")
        logo_dir = group_logo_util.group_logos_dir()
        if logo_dir.is_dir():
            for path in sorted(logo_dir.glob("*.png")):
                if path.is_file():
                    zf.write(path, arcname=f"group_logos/{path.name}")
    out = _next_backup_path(stamp)
    out.write_bytes(buf.getvalue())
    if automatic:
        prune_expired_auto_backups(created)
    backup_archive_prune()
    return out


def get_last_existing_auto_backup_at() -> datetime | None:
    return _latest_auto_backup_at_from_archive()


def get_last_auto_backup_at(conn: sqlite3.Connection) -> datetime | None:
    row = db.fetch_one(conn, "SELECT value FROM app_settings WHERE key = ?", (KEY_LAST_AUTO_BACKUP_AT,))
    if not row or row["value"] is None:
        return None
    raw = str(row["value"]).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def set_last_auto_backup_at(conn: sqlite3.Connection, at: datetime) -> None:
    conn.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (KEY_LAST_AUTO_BACKUP_AT, at.isoformat(timespec="seconds")),
    )


def maybe_create_weekly_backup(now: datetime | None = None) -> Path | None:
    current = now or datetime.now()
    if not db_path().exists():
        return None
    with _AUTO_BACKUP_LOCK:
        prune_expired_auto_backups(current)
        latest_existing_auto = get_last_existing_auto_backup_at()
        with db.get_connection() as conn:
            last = get_last_auto_backup_at(conn)
            if latest_existing_auto is None:
                # If auto backups were deleted manually, wait a short grace period
                # before creating a replacement backup, then recreate immediately.
                if last and current - last < timedelta(minutes=AUTO_BACKUP_MISSING_GRACE_MINUTES):
                    return None
            else:
                if last and current - last < timedelta(days=AUTO_BACKUP_INTERVAL_DAYS):
                    return None
        created = create_system_backup_archive(current, automatic=True)
        if created is None:
            return None
        with db.get_connection() as conn:
            set_last_auto_backup_at(conn, current)
        return created
