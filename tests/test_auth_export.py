from app.auth import hash_password, verify_password
from app.export_service import build_pdf_bytes


def test_password_pbkdf2_roundtrip() -> None:
    h = hash_password("secret-kasse")
    assert h.startswith("$pbkdf2")
    assert verify_password("secret-kasse", h)
    assert not verify_password("wrong", h)


def test_build_pdf_starts_with_pdf_magic() -> None:
    header = {
        "user_name": "Anna",
        "group_name": "G1",
        "created_at": "2024-06-01T12:00:00+00:00",
        "total_cents": 250,
        "note": "Bar",
        "received_confirmed": 1,
    }
    lines = [
        {
            "created_at": "2024-06-01T11:00:00+00:00",
            "description": "Test",
            "product_name": "Cola",
            "amount_cents": 250,
        }
    ]
    data = build_pdf_bytes(header, lines)  # type: ignore[arg-type]
    assert data[:4] == b"%PDF"
