import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_KEY_FILE = ROOT / ".secret_key"


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
