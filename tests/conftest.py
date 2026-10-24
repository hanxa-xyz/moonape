import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fixture_mode(tmp_path, monkeypatch):
    """Every test runs on recorded fixtures and writes to a throwaway data dir."""
    monkeypatch.setenv("MOONAPE_FIXTURE", "1")
    monkeypatch.setenv("MOONAPE_DATA", str(tmp_path / "data"))
    from moonape import config
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "SITE_DATA", tmp_path / "site_data")
    yield


@pytest.fixture
def http():
    from moonape.http import Http
    return Http(fixture=True)


os.environ.setdefault("SEC_USER_AGENT", "moonape tests@example.com")
