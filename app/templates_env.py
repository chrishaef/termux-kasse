from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.requests import Request

from app.dates import format_date_de


class KasseTemplates(Jinja2Templates):
    """Starlette 0.27: TemplateResponse(name, context) mit Pflicht-Key request — gleiche Signatur wie früheres FastAPI (request zuerst)."""

    def TemplateResponse(  # type: ignore[override]
        self,
        request: Request,
        name: str,
        context: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
        background: Any = None,
    ) -> Any:
        merged = {"request": request, **context}
        return super().TemplateResponse(
            name,
            merged,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )


def _eur(cents: int | str | None) -> str:
    if cents is None:
        return "0,00 €"
    v = int(cents) / 100
    return f"{v:.2f} €".replace(".", ",")


def _nl2br(value: str | None) -> Markup:
    if value is None:
        return Markup("")
    return Markup("<br>\n").join(escape(line) for line in str(value).split("\n"))


TEMPLATES = KasseTemplates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["eur"] = _eur
TEMPLATES.env.filters["nl2br"] = _nl2br
TEMPLATES.env.filters["date_de"] = format_date_de
