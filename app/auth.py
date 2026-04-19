import re

from passlib.hash import pbkdf2_sha256

# bcrypt begrenzt Passwörter auf 72 Byte (UTF-8); für typische Admin-Passwörter ausreichend.
_MAX = 72

_BCRYPT_RE = re.compile(r"^\$2[aby]\$")


def hash_password(password: str) -> str:
    """Neue Hashes: PBKDF2-SHA256 (reines Python, kein Rust) — pip ohne bcrypt möglich."""
    return pbkdf2_sha256.using(rounds=310_000).hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    h = (password_hash or "").strip()
    if not h:
        return False
    # Alte Installationen (Desktop): bcrypt-Hashes weiter prüfen, falls Paket vorhanden.
    if _BCRYPT_RE.match(h):
        try:
            import bcrypt
        except ImportError:
            return False
        try:
            raw = password.encode("utf-8")
            if len(raw) > _MAX:
                raw = raw[:_MAX]
            return bcrypt.checkpw(raw, h.encode("ascii"))
        except (ValueError, TypeError):
            return False
    try:
        return pbkdf2_sha256.verify(password, h)
    except (ValueError, TypeError):
        return False
