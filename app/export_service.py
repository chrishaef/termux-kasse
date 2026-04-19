from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

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


def build_xlsx_bytes(
    header: sqlite3.Row,
    aggregated_lines: list[dict[str, Any]],
) -> bytes:
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
    ws.append(["Anzahl", "Bezeichnung", "Einzel (EUR)", "Summe (EUR)"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r in aggregated_lines:
        ws.append(
            [
                int(r["quantity"]),
                r["label"],
                round(int(r["unit_cents"]) / 100, 2),
                round(int(r["total_cents"]) / 100, 2),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf_bytes(
    header: sqlite3.Row,
    aggregated_lines: list[dict[str, Any]],
) -> bytes:
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
    wcols = (16, 94, 30, 30)
    pdf.set_font("Helvetica", "B", 8)
    headers = ("Anz.", "Bezeichnung", "Einzel", "Summe")
    for i, (txt, w) in enumerate(zip(headers, wcols)):
        pdf.cell(w, 6, _pdf_cell_text(txt, 20), 1, 1 if i == len(wcols) - 1 else 0)
    pdf.set_font("Helvetica", "", 8)
    for r in aggregated_lines:
        cells = [
            str(int(r["quantity"])),
            str(r["label"]),
            f'{int(r["unit_cents"]) / 100:.2f}',
            f'{int(r["total_cents"]) / 100:.2f}',
        ]
        maxl = (10, 60, 12, 12)
        for i, (c, w, m) in enumerate(zip(cells, wcols, maxl)):
            pdf.cell(w, 5.5, _pdf_cell_text(c, m), 1, 1 if i == len(wcols) - 1 else 0)

    out = pdf.output(dest="S")
    return out.encode("latin-1", errors="replace")


def build_statistics_pdf_bytes(
    period_start: str | None,
    period_end: str | None,
    group_name: str | None,
    totals: dict[str, int],
    user_rows: list[dict[str, Any]],
    product_rows: list[dict[str, Any]],
) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _pdf_cell_text("Statistik (Zeitraum)", 80), 0, 1)
    pdf.set_font("Helvetica", "", 9)
    p_from = format_date_de(period_start) if period_start else "-"
    p_to = format_date_de(period_end) if period_end else "-"
    pdf.cell(0, 6, _pdf_cell_text(f"Von: {p_from}   Bis: {p_to}", 110), 0, 1)
    if group_name:
        pdf.cell(0, 6, _pdf_cell_text(f"Nutzergruppe: {group_name}", 90), 0, 1)
    pdf.ln(1)

    meta = [
        ("Buchungen", str(int(totals["entries_count"]))),
        ("Nutzer mit Buchungen", str(int(totals["users_count"]))),
        ("Gesamtumsatz EUR", f'{int(totals["total_cents"]) / 100:.2f}'),
    ]
    for label, val in meta:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(52, 6, _pdf_cell_text(label, 36), 1, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(110, 6, _pdf_cell_text(val, 50), 1, 1)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _pdf_cell_text("Nutzer-Topliste (inkl. Artikelmix)", 48), 0, 1)
    w_users = (10, 26, 28, 76, 14, 28)
    headers_u = ("#", "Gruppe", "Nutzer", "Artikel", "Anz.", "EUR")
    pdf.set_font("Helvetica", "B", 8)
    for i, (txt, w) in enumerate(zip(headers_u, w_users)):
        pdf.cell(w, 6, _pdf_cell_text(txt, 20), 1, 1 if i == len(w_users) - 1 else 0)
    pdf.set_font("Helvetica", "", 8)
    if not user_rows:
        pdf.cell(sum(w_users), 6, _pdf_cell_text("Keine Daten im Zeitraum", 40), 1, 1)
    for idx, r in enumerate(user_rows, start=1):
        cells = [
            str(idx),
            str(r["group_name"]),
            str(r["user_name"]),
            str(r.get("purchases_summary", "")),
            str(int(r["entries_count"])),
            f'{int(r["total_cents"]) / 100:.2f}',
        ]
        maxl = (3, 13, 14, 42, 5, 12)
        for i, (c, w, m) in enumerate(zip(cells, w_users, maxl)):
            pdf.cell(w, 5.5, _pdf_cell_text(c, m), 1, 1 if i == len(w_users) - 1 else 0)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _pdf_cell_text("Artikel (zusammengefasst)", 42), 0, 1)
    w_prod = (16, 90, 28, 28)
    headers_p = ("Anz.", "Bezeichnung", "Einzel", "Summe")
    pdf.set_font("Helvetica", "B", 8)
    for i, (txt, w) in enumerate(zip(headers_p, w_prod)):
        pdf.cell(w, 6, _pdf_cell_text(txt, 20), 1, 1 if i == len(w_prod) - 1 else 0)
    pdf.set_font("Helvetica", "", 8)
    if not product_rows:
        pdf.cell(sum(w_prod), 6, _pdf_cell_text("Keine Daten im Zeitraum", 40), 1, 1)
    for r in product_rows:
        cells = [
            str(int(r["quantity"])),
            str(r["label"]),
            f'{int(r["unit_cents"]) / 100:.2f}',
            f'{int(r["total_cents"]) / 100:.2f}',
        ]
        for i, (c, w) in enumerate(zip(cells, w_prod)):
            pdf.cell(w, 5.5, _pdf_cell_text(c, 42), 1, 1 if i == len(w_prod) - 1 else 0)

    out = pdf.output(dest="S")
    return out.encode("latin-1", errors="replace")


def build_statistics_xlsx_bytes(
    period_start: str | None,
    period_end: str | None,
    group_name: str | None,
    totals: dict[str, int],
    user_rows: list[dict[str, Any]],
    product_rows: list[dict[str, Any]],
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statistik"
    bold = Font(bold=True)

    ws.append(["Statistik (Zeitraum)"])
    ws["A1"].font = bold
    ws.append(["Von", format_date_de(period_start) if period_start else "-"])
    ws.append(["Bis", format_date_de(period_end) if period_end else "-"])
    ws.append(["Nutzergruppe", group_name or "Alle"])
    ws.append([])
    ws.append(["Kennzahl", "Wert"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    ws.append(["Buchungen", int(totals["entries_count"])])
    ws.append(["Nutzer mit Buchungen", int(totals["users_count"])])
    ws.append(["Gesamtumsatz (EUR)", round(int(totals["total_cents"]) / 100, 2)])

    ws.append([])
    ws.append(["Nutzer-Topliste"])
    ws[f"A{ws.max_row}"].font = bold
    ws.append(["Rang", "Gruppe", "Nutzer", "Artikelmix", "Buchungen", "Summe (EUR)"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for idx, r in enumerate(user_rows, start=1):
        ws.append(
            [
                idx,
                r["group_name"],
                r["user_name"],
                r.get("purchases_summary", ""),
                int(r["entries_count"]),
                round(int(r["total_cents"]) / 100, 2),
            ]
        )

    ws.append([])
    ws.append(["Artikel-Auswertung (zusammengefasst)"])
    ws[f"A{ws.max_row}"].font = bold
    ws.append(["Anzahl", "Bezeichnung", "Einzel (EUR)", "Summe (EUR)"])
    for cell in ws[ws.max_row]:
        cell.font = bold
    for r in product_rows:
        ws.append(
            [
                int(r["quantity"]),
                r["label"],
                round(int(r["unit_cents"]) / 100, 2),
                round(int(r["total_cents"]) / 100, 2),
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
