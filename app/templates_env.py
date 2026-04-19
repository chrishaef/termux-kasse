from pathlib import Path

from fastapi.templating import Jinja2Templates


def _eur(cents: int | str | None) -> str:
    if cents is None:
        return "0,00 €"
    v = int(cents) / 100
    return f"{v:.2f} €".replace(".", ",")


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["eur"] = _eur
