import pytest


@pytest.fixture(autouse=True)
def no_rate_limit_wait(monkeypatch):
    # Rate-limit retries wait in real use; tests must stay instant.
    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_WAIT", "0")
