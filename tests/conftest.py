import httpx
import pytest


@pytest.fixture(autouse=True)
def no_rate_limit_wait(monkeypatch):
    # Rate-limit retries wait in real use; tests must stay instant.
    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_WAIT", "0")


@pytest.fixture(autouse=True)
def no_psx_network(monkeypatch, tmp_path):
    # The Upload screen asks PSX for its company list; tests must never reach the real site.
    import streamlit as st
    from src.sources import psx

    def offline(request):
        raise httpx.ConnectError("network disabled in tests")
    monkeypatch.setattr(psx, "_client", lambda: httpx.Client(transport=httpx.MockTransport(offline)))
    monkeypatch.setattr(psx, "_pause", lambda: None)
    monkeypatch.setenv("FINSIGHT_CACHE_DIR", str(tmp_path / "psx-cache"))
    st.cache_data.clear()
    yield
    st.cache_data.clear()
