import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEY_FILE = ROOT / ".secret_key"
MASTER_PASSWORD_FILE = ROOT / ".admin_master_password"


def data_dir() -> Path:
    return Path(os.environ.get("KASSE_DATA_DIR", str(ROOT / "data")))


def db_path() -> Path:
    return data_dir() / "kasse.db"


def get_secret_key() -> str:
    data_dir().mkdir(parents=True, exist_ok=True)
    if "KASSE_SECRET_KEY" in os.environ:
        return os.environ["KASSE_SECRET_KEY"]
    if SECRET_KEY_FILE.is_file():
        return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
    key = os.urandom(32).hex()
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key


def master_password_file() -> Path:
    """Fester Pfad der Master-Passwort-Datei. Der Inhalt ist das Passwort im Klartext."""
    override = os.environ.get("KASSE_MASTER_PASSWORD_FILE")
    if override:
        return Path(override)
    return MASTER_PASSWORD_FILE


def read_master_password() -> str | None:
    """Inhalt der Master-Passwort-Datei (getrimmt). None, wenn Datei fehlt oder leer ist."""
    path = master_password_file()
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None
