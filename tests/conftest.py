import pytest


@pytest.fixture(autouse=True)
def no_tracing(monkeypatch):
    """Tests never send an investigation's trace anywhere, whatever is installed and whatever is in .env."""
    monkeypatch.setenv("WHODUNIT_TRACE", "off")
