from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape


def _eur(cents: int | str | None) -> str:
    if cents is None:
        return "0,00 €"
    v = int(cents) / 100
    return f"{v:.2f} €".replace(".", ",")


def _nl2br(value: str | None) -> Markup:
    if value is None:
        return Markup("")
    return Markup("<br>\n").join(escape(line) for line in str(value).split("\n"))


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["eur"] = _eur
TEMPLATES.env.filters["nl2br"] = _nl2br
