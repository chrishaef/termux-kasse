import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KASSE_SECRET_KEY", "unit-test-secret-key-32bytes!!")
    monkeypatch.setenv("KASSE_DATA_DIR", str(tmp_path / "data"))
