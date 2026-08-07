from pathlib import Path
from typing import Any
import inspect

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.requests import Request

from app.dates import format_date_de

# FastAPI 0.99 / Starlette 0.27 (Termux): TemplateResponse(name, context)
# Newer Starlette: TemplateResponse(request, name, context)
_SUPER_TEMPLATE_PARAMS = tuple(
    name
    for name in inspect.signature(Jinja2Templates.TemplateResponse).parameters
    if name != "self"
)
_SUPER_USES_REQUEST_FIRST = bool(_SUPER_TEMPLATE_PARAMS) and _SUPER_TEMPLATE_PARAMS[0] == "request"


class KasseTemplates(Jinja2Templates):
    """Call sites use TemplateResponse(request, name, context) on both Starlette APIs."""

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
        if _SUPER_USES_REQUEST_FIRST:
            return super().TemplateResponse(
                request,
                name,
                context,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
                background=background,
            )
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
