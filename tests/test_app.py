from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    # Never read or write the user's real saved runs during tests.
    monkeypatch.setenv("FINSIGHT_DB_PATH", str(tmp_path / "runs.sqlite3"))


def test_app_starts_and_demo_loads():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    assert not app.exception
    click(app, "Load synthetic demo")
    assert not app.exception
    assert app.session_state.run.is_demo
    assert len(app.session_state.run.fields) == 27  # 21 current-year + 6 prior-year


def click(app, label):
    return next(b for b in app.button if b.label == label).click().run()


def test_verification_gate_and_demo_ratios():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    click(app, "Load synthetic demo")
    assert app.session_state.step == "3 · Verify"  # the demo skips straight to checking values
    app.radio(key="step").set_value("4 · Results").run()
    assert not app.exception
    assert len(app.metric) == 0
    app.radio(key="step").set_value("3 · Verify").run()
    click(app, "Finish verification")
    assert app.error and "rows need attention" in app.error[0].value  # every problem listed at once
    assert not app.session_state.run.verified_at
    click(app, "✓ Accept all ready")
    click(app, "Finish verification")
    assert not app.exception
    assert app.session_state.run.verified_at
    app.radio(key="step").set_value("4 · Results").run()
    assert not app.exception
    assert len(app.metric) >= 6
    assert str(app.session_state.run.metrics[0].value) == "0.35"


def test_save_progress_keeps_partial_decisions():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    click(app, "Load synthetic demo")
    click(app, "Mark remaining unavailable")
    run = app.session_state.run
    assert run.review_draft and not run.verified_at
    assert {d["Decision"] for d in run.review_draft} == {"unavailable"}


def test_complete_demo_workflow_and_export():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=30).run()
    click(app, "Load synthetic demo")
    click(app, "✓ Accept all ready")
    click(app, "Finish verification")
    app.radio(key="step").set_value("4 · Results").run()
    click(app, "Generate demo council & synthesis")
    assert not app.exception
    assert len(app.session_state.run.analysts) == 4
    assert len(app.session_state.run.synthesis.sections) == 11
    labels = {b.label for b in app.get("download_button")}
    assert {"Download Markdown", "Download PDF", "Download full audit JSON", "Download per-field CSV"} <= labels
    app.radio(key="step").set_value("5 · Evaluate").run()
    assert not app.exception


def test_password_screen_blocks_until_correct(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "fyp-test")
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    assert not app.exception and not any(b.label == "Load synthetic demo" for b in app.button)
    app.text_input[0].input("wrong").run()
    app.button[0].click().run()
    assert app.error and not any(b.label == "Load synthetic demo" for b in app.button)
    app.text_input[0].input("fyp-test").run()
    app.button[0].click().run()
    assert any(b.label == "Load synthetic demo" for b in app.button)


def test_no_password_configured_means_no_screen(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    assert any(b.label == "Load synthetic demo" for b in app.button)


def test_cloud_secrets_become_settings_without_overriding(monkeypatch):
    import os
    monkeypatch.setenv("GEMINI_MODEL", "local-choice")
    monkeypatch.delenv("FINSIGHT_SHARED_DEPLOYMENT", raising=False)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20)
    app.secrets["FINSIGHT_SHARED_DEPLOYMENT"] = "true"
    app.secrets["GEMINI_MODEL"] = "cloud-choice"
    try:
        app.run()
        assert os.environ["GEMINI_MODEL"] == "local-choice"
        assert any("Shared test version" in i.value for i in app.info)
    finally:
        os.environ.pop("FINSIGHT_SHARED_DEPLOYMENT", None)


def test_theme_and_upload_settings_exist():
    import tomllib
    config = tomllib.loads(Path(".streamlit/config.toml").read_text())
    assert config["theme"]["base"] == "light" and config["theme"]["primaryColor"] == "#087f8c"
    assert config["server"]["maxUploadSize"] == 100
    assert config["browser"]["gatherUsageStats"] is False


def report_pdf() -> bytes:
    import pymupdf
    doc = pymupdf.open()
    rows = "\n".join(f"Line item {i}    {i},234,567    {i},111,222" for i in range(1, 21))
    doc.new_page().insert_text((40, 40), "STATEMENT OF FINANCIAL POSITION\nAS AT DECEMBER 31, 2024\n" + rows, fontsize=7)
    return doc.tobytes()


def test_fetch_from_psx_opens_extract_with_details_filled(monkeypatch):
    import streamlit as st
    from src.sources import psx
    st.cache_data.clear()
    report = psx.Report("EFERT", "Annual", "2024", "2025-03-03", "249069")
    monkeypatch.setattr(psx, "list_companies", lambda: {"EFERT": "Engro Fertilizers Limited"})
    monkeypatch.setattr(psx, "annual_reports", lambda ticker: {2024: report})
    monkeypatch.setattr(psx, "download", lambda r: report_pdf())
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    app.selectbox[0].set_value("EFERT").run()
    click(app, "Fetch annual report")
    assert not app.exception
    run = app.session_state.run
    assert (run.company.name, run.company.ticker, run.company.financial_year) == ("Engro Fertilizers Limited", "EFERT", 2024)
    assert run.company.statement_basis == "standalone"  # chosen from the report, which has only standalone statements
    assert "249069" in run.source and app.session_state.step == "2 · Extract"
    st.cache_data.clear()


def test_psx_unavailable_points_to_upload(monkeypatch):
    import streamlit as st
    from src.sources import psx
    st.cache_data.clear()
    def down():
        raise psx.PSXError("The PSX financial reports library is not reachable right now.")
    monkeypatch.setattr(psx, "list_companies", down)
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    assert not app.exception and any("Upload a PDF" in w.value for w in app.warning)
    st.cache_data.clear()
