"""PNG-Logos für Nutzergruppen (Kiosk-Gruppenauswahl). Ohne Pillow."""

from __future__ import annotations

import binascii
import re
import struct
import zlib
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


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(_PNG_MAGIC):
        raise ValueError("not_png")
    chunks: list[tuple[bytes, bytes]] = []
    pos = len(_PNG_MAGIC)
    while pos + 12 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        ctype = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        crc_end = end + 4
        if end > len(data) or crc_end > len(data):
            raise ValueError("chunk")
        chunks.append((ctype, data[start:end]))
        pos = crc_end
        if ctype == b"IEND":
            break
    return chunks


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanlines(raw: bytes, width: int, height: int, bpp: int) -> list[bytearray]:
    stride = width * bpp
    rows: list[bytearray] = []
    pos = 0
    prev = bytearray(stride)
    for _ in range(height):
        if pos >= len(raw):
            raise ValueError("scanline")
        ftype = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride
        if len(row) != stride:
            raise ValueError("scanline")
        for i in range(stride):
            left = row[i - bpp] if i >= bpp else 0
            up = prev[i]
            upper_left = prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                row[i] = (row[i] + left) & 0xFF
            elif ftype == 2:
                row[i] = (row[i] + up) & 0xFF
            elif ftype == 3:
                row[i] = (row[i] + ((left + up) // 2)) & 0xFF
            elif ftype == 4:
                row[i] = (row[i] + _paeth(left, up, upper_left)) & 0xFF
            elif ftype != 0:
                raise ValueError("filter")
        rows.append(row)
        prev = row
    return rows


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    crc = binascii.crc32(ctype)
    crc = binascii.crc32(payload, crc) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + ctype + payload + crc.to_bytes(4, "big")


def _encode_rgba_png(width: int, height: int, rgba_rows: list[bytes]) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + row for row in rgba_rows)
    return (
        _PNG_MAGIC
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _trim_transparent_padding(data: bytes) -> bytes:
    chunks = _png_chunks(data)
    ihdr = next((payload for ctype, payload in chunks if ctype == b"IHDR"), None)
    if ihdr is None or len(ihdr) != 13:
        raise ValueError("ihdr")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if (
        bit_depth != 8
        or compression != 0
        or filter_method != 0
        or interlace != 0
        or color_type not in (4, 6)
    ):
        return data
    bpp = 4 if color_type == 6 else 2
    idat = b"".join(payload for ctype, payload in chunks if ctype == b"IDAT")
    if not idat:
        return data
    rows = _unfilter_scanlines(zlib.decompress(idat), width, height, bpp)

    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    alpha_offset = 3 if color_type == 6 else 1
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * bpp + alpha_offset] == 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    if max_x < 0:
        return data
    if min_x == 0 and min_y == 0 and max_x == width - 1 and max_y == height - 1:
        return data

    out_rows: list[bytes] = []
    for y in range(min_y, max_y + 1):
        source = rows[y]
        out = bytearray()
        for x in range(min_x, max_x + 1):
            offset = x * bpp
            if color_type == 6:
                out.extend(source[offset : offset + 4])
            else:
                gray = source[offset]
                alpha = source[offset + 1]
                out.extend((gray, gray, gray, alpha))
        out_rows.append(bytes(out))
    return _encode_rgba_png(max_x - min_x + 1, max_y - min_y + 1, out_rows)


def normalize_logo_png(data: bytes) -> bytes:
    validate_png_bytes(data)
    try:
        normalized = _trim_transparent_padding(data)
        validate_png_bytes(normalized)
        return normalized
    except Exception:
        return data


def save_logo_png(group_id: int, data: bytes) -> None:
    normalized = normalize_logo_png(data)
    path = logo_file_path(group_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(normalized)


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
