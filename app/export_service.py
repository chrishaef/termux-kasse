from __future__ import annotations

import io
from typing import TYPE_CHECKING

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font

if TYPE_CHECKING:
    import sqlite3

from app.dates import format_date_de


def _received_quittance_label(header: sqlite3.Row) -> str | None:
    try:
        v = header["received_confirmed"]
    except (KeyError, IndexError):
        return None
    return "Ja" if int(v) == 1 else "Nein"


def _pdf_cell_text(s: str, max_len: int) -> str:
    """PyFPDF 1.x nutzt Latin-1-Kernschriften — Umlaute ok, Rest ersetzt."""
    t = str(s).replace("\r", " ").replace("\n", " ")
    if len(t) > max_len:
        t = t[: max_len - 3] + "..."
    return t.encode("latin-1", errors="replace").decode("latin-1")


def build_xlsx_bytes(header: sqlite3.Row, lines: list[sqlite3.Row]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Abrechnung"
    bold = Font(bold=True)
    ws.append(["Abrechnung", "", "", ""])
    ws["A1"].font = bold
    ws.append(["Nutzer", header["user_name"]])
    ws.append(["Gruppe", header["group_name"]])
    ws.append(["Erstellt", format_date_de(header["created_at"])])
    ws.append(["Summe (EUR)", round(int(header["total_cents"]) / 100, 2)])
    if header["note"]:
        ws.append(["Notiz", header["note"]])
    rq = _received_quittance_label(header)
    if rq is not None:
        ws.append(["Zahlungseingang bestätigt", rq])
    ws.append([])
    ws.append(["Datum", "Beschreibung", "Artikel", "Betrag EUR"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r in lines:
        ws.append(
            [
                format_date_de(r["created_at"]),
                r["description"],
                r["product_name"] or "",
                round(int(r["amount_cents"]) / 100, 2),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf_bytes(header: sqlite3.Row, lines: list[sqlite3.Row]) -> bytes:
    """PDF ohne Pillow — PyFPDF 1.x-Paket ``fpdf`` (nicht fpdf2), keine Bild-Abhängigkeiten."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, _pdf_cell_text("Abrechnung Shopkasse", 80), 0, 1)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 9)

    meta: list[tuple[str, str]] = [
        ("Nutzer", str(header["user_name"])),
        ("Gruppe", str(header["group_name"])),
        ("Erstellt", format_date_de(header["created_at"])),
        ("Summe EUR", f'{int(header["total_cents"]) / 100:.2f}'),
    ]
    if header["note"]:
        meta.append(("Notiz", str(header["note"])))
    rq = _received_quittance_label(header)
    if rq is not None:
        meta.append(("Zahlungseingang bestätigt", rq))

    label_w, val_w = 48, 122
    for label, val in meta:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(label_w, 6, _pdf_cell_text(label, 40), 1, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(val_w, 6, _pdf_cell_text(val, 120), 1, 1)

    pdf.ln(4)
    wcols = (26, 74, 40, 30)
    pdf.set_font("Helvetica", "B", 8)
    for i, (txt, w) in enumerate(zip(["Datum", "Beschreibung", "Artikel", "EUR"], wcols)):
        pdf.cell(w, 6, _pdf_cell_text(txt, 24), 1, 1 if i == len(wcols) - 1 else 0)
    pdf.set_font("Helvetica", "", 8)
    for r in lines:
        cells = [
            format_date_de(r["created_at"]),
            str(r["description"]),
            str(r["product_name"] or ""),
            f'{int(r["amount_cents"]) / 100:.2f}',
        ]
        maxl = (22, 48, 24, 12)
        for i, (c, w, m) in enumerate(zip(cells, wcols, maxl)):
            pdf.cell(w, 5.5, _pdf_cell_text(c, m), 1, 1 if i == len(wcols) - 1 else 0)

    out = pdf.output(dest="S")
    return out.encode("latin-1", errors="replace")
