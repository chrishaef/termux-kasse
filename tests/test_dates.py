from app.dates import format_date_de


def test_format_date_de_iso_datetime_utc() -> None:
    assert format_date_de("2026-04-19T14:30:00+00:00") == "19.04.2026"


def test_format_date_de_date_only() -> None:
    assert format_date_de("2026-01-05") == "05.01.2026"


def test_format_date_de_z_suffix() -> None:
    assert format_date_de("2026-12-01T00:00:00Z") == "01.12.2026"
