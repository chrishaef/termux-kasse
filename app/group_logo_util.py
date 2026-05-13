"""PNG-Logos für Nutzergruppen (Kiosk-Gruppenauswahl). Ohne Pillow — nur Signatur/IHDR prüfen."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import data_dir

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# Große PNGs sind ok — in der Kachel wird nur klein dargestellt (CSS).
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_DIMENSION = 8192
_FILENAME_RE = re.compile(r"^(\d+)\.png$")


def group_logos_dir() -> Path:
    p = data_dir() / "group_logos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logo_file_path(group_id: int) -> Path:
    return group_logos_dir() / f"{int(group_id)}.png"


def parse_png_ihdr_dimensions(data: bytes) -> tuple[int, int]:
    """Liest Breite/Höhe aus dem IHDR-Chunk (erster Chunk nach PNG-Signatur)."""
    if len(data) < 24 or not data.startswith(_PNG_MAGIC):
        raise ValueError("not_png")
    if data[12:16] != b"IHDR":
        raise ValueError("ihdr")
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    if w < 1 or h < 1 or w > _MAX_DIMENSION or h > _MAX_DIMENSION:
        raise ValueError("dimensions")
    return w, h


def validate_png_bytes(data: bytes) -> None:
    if len(data) < 24:
        raise ValueError("too_small")
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError("too_big")
    parse_png_ihdr_dimensions(data)


def save_logo_png(group_id: int, data: bytes) -> None:
    validate_png_bytes(data)
    path = logo_file_path(group_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_logo_file(group_id: int) -> None:
    logo_file_path(group_id).unlink(missing_ok=True)


def unlink_all_logo_files() -> None:
    d = group_logos_dir()
    if not d.is_dir():
        return
    for p in d.glob("*.png"):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def safe_group_logo_arcname(name: str) -> str | None:
    """Nur ``group_logos/<id>.png`` mit numerischer id."""
    if not name.startswith("group_logos/") or name.endswith("/"):
        return None
    base = Path(name).name
    m = _FILENAME_RE.match(base)
    if not m:
        return None
    return f"group_logos/{m.group(1)}.png"
