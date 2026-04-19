import bcrypt

# bcrypt begrenzt Passwörter auf 72 Byte (UTF-8); für typische Admin-Passwörter ausreichend.
_MAX = 72


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > _MAX:
        raw = raw[:_MAX]
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        raw = password.encode("utf-8")
        if len(raw) > _MAX:
            raw = raw[:_MAX]
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
