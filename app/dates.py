"""Anzeige von Zeitstempeln aus der DB nur als Datum (deutsch TT.MM.JJJJ)."""

from __future__ import annotations

from datetime import datetime, timezone


def format_date_de(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except ValueError:
                return s[:10]
        else:
            return s[:10] if len(s) >= 10 else s
    return f"{dt.day:02d}.{dt.month:02d}.{dt.year}"
