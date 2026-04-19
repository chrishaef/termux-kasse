from __future__ import annotations

import io
from typing import TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    import sqlite3


def build_xlsx_bytes(header: sqlite3.Row, lines: list[sqlite3.Row]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Abrechnung"
    bold = Font(bold=True)
    ws.append(["Abrechnung", "", "", ""])
    ws["A1"].font = bold
    ws.append(["Nutzer", header["user_name"]])
    ws.append(["Gruppe", header["group_name"]])
    ws.append(["Erstellt", header["created_at"]])
    ws.append(["Summe (EUR)", round(int(header["total_cents"]) / 100, 2)])
    if header["note"]:
        ws.append(["Notiz", header["note"]])
    ws.append([])
    ws.append(["Datum", "Beschreibung", "Artikel", "Betrag EUR"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r in lines:
        ws.append(
            [
                r["created_at"],
                r["description"],
                r["product_name"] or "",
                round(int(r["amount_cents"]) / 100, 2),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf_bytes(header: sqlite3.Row, lines: list[sqlite3.Row]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    story: list = []
    styles = getSampleStyleSheet()
    story.append(Paragraph("Abrechnung Vertrauenskasse", styles["Title"]))
    story.append(Spacer(1, 0.4 * cm))
    meta = [
        ["Nutzer", str(header["user_name"])],
        ["Gruppe", str(header["group_name"])],
        ["Erstellt", str(header["created_at"])],
        ["Summe EUR", f'{int(header["total_cents"]) / 100:.2f}'],
    ]
    if header["note"]:
        meta.append(["Notiz", str(header["note"])])
    t = Table(meta, colWidths=[4 * cm, 12 * cm])
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.6 * cm))
    data = [["Datum", "Beschreibung", "Artikel", "EUR"]]
    for r in lines:
        data.append(
            [
                str(r["created_at"]),
                str(r["description"]),
                str(r["product_name"] or ""),
                f'{int(r["amount_cents"]) / 100:.2f}',
            ]
        )
    lt = Table(data, repeatRows=1, colWidths=[3.2 * cm, 5 * cm, 4 * cm, 2.5 * cm])
    lt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(lt)
    doc.build(story)
    return buf.getvalue()
