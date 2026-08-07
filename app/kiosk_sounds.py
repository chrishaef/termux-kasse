"""Instanz-Kiosk-Sounds (Warnungen + Buchungsklick) mit Fallback auf Static-Defaults."""

from __future__ import annotations

from pathlib import Path

from app.config import data_dir

SOUND_KEYS = ("warn1", "warn2", "warn3", "click")
_STATIC_FILENAMES = {
    "warn1": "warn1.mp3",
    "warn2": "warn2.mp3",
    "warn3": "warn3.mp3",
    "click": "click.mp3",
}
_MAX_BYTES = 2 * 1024 * 1024


def sounds_dir() -> Path:
    path = data_dir() / "kiosk_sounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_key(key: str) -> str:
    normalized = (key or "").strip().lower()
    if normalized not in SOUND_KEYS:
        raise ValueError(f"Ungültiger Sound-Key: {key}")
    return normalized


def custom_sound_path(key: str) -> Path:
    return sounds_dir() / f"{_normalize_key(key)}.mp3"


def default_static_sound_path(key: str) -> Path:
    filename = _STATIC_FILENAMES[_normalize_key(key)]
    return Path(__file__).resolve().parent / "static" / filename


def has_custom_sound(key: str) -> bool:
    return custom_sound_path(key).is_file()


def resolve_sound_file_path(key: str) -> Path:
    custom = custom_sound_path(key)
    if custom.is_file():
        return custom
    return default_static_sound_path(key)


def default_sound_url(key: str) -> str:
    return f"/static/{_STATIC_FILENAMES[_normalize_key(key)]}"


def sound_url(key: str) -> str:
    custom = custom_sound_path(key)
    if custom.is_file():
        try:
            version = int(custom.stat().st_mtime)
        except OSError:
            version = 0
        return f"/kiosk-sound/{_normalize_key(key)}?v={version}"
    return default_sound_url(key)


def validate_mp3_bytes(data: bytes) -> None:
    if not data:
        raise ValueError("Leere Audiodatei")
    if len(data) > _MAX_BYTES:
        raise ValueError("Audiodatei zu groß (max. 2 MB)")
    if data.startswith(b"ID3"):
        return
    # MPEG frame sync (common MP3 without ID3 tag)
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return
    raise ValueError("Keine gültige MP3-Datei")


def save_sound_mp3(key: str, data: bytes) -> Path:
    validate_mp3_bytes(data)
    path = custom_sound_path(key)
    path.write_bytes(data)
    return path


def delete_custom_sound(key: str) -> None:
    path = custom_sound_path(key)
    if path.is_file():
        path.unlink()


def get_sound_urls() -> dict[str, str]:
    return {key: sound_url(key) for key in SOUND_KEYS}


def get_sounds_admin_state() -> dict[str, dict[str, str | bool]]:
    state: dict[str, dict[str, str | bool]] = {}
    for key in SOUND_KEYS:
        state[key] = {
            "url": sound_url(key),
            "has_custom": has_custom_sound(key),
        }
    return state
