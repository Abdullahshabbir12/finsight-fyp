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
    next(b for b in app.button if b.label == "Load synthetic demo").click().run()
    assert not app.exception
    assert app.session_state.run.is_demo
    assert len(app.session_state.run.fields) == 27  # 21 current-year + 6 prior-year


def test_verification_gate_and_demo_ratios():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    next(b for b in app.button if b.label == "Load synthetic demo").click().run()
    app.sidebar.radio[0].set_value("Results & analysis").run()
    assert not app.exception
    assert len(app.metric) == 0
    app.sidebar.radio[0].set_value("Human verification").run()
    assert not app.exception
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "Save verification").click().run()
    assert not app.exception
    assert app.session_state.run.verified_at
    app.sidebar.radio[0].set_value("Results & analysis").run()
    assert not app.exception
    assert len(app.metric) >= 6
    assert app.session_state.run.metrics[0].value == .35 or str(app.session_state.run.metrics[0].value) == "0.35"


def test_complete_demo_workflow_and_export():
    app = AppTest.from_file(Path("app.py").resolve(), default_timeout=30).run()
    next(b for b in app.button if b.label == "Load synthetic demo").click().run()
    app.sidebar.radio[0].set_value("Human verification").run()
    app.checkbox[0].check()
    next(b for b in app.button if b.label == "Save verification").click().run()
    app.sidebar.radio[0].set_value("Results & analysis").run()
    next(b for b in app.button if b.label == "Generate demo council & synthesis").click().run()
    assert not app.exception
    assert len(app.session_state.run.analysts) == 4
    assert len(app.session_state.run.synthesis.sections) == 11
    labels = {b.label for b in app.get("download_button")}
    assert {"Download Markdown", "Download PDF", "Download full audit JSON", "Download per-field CSV"} <= labels
    app.sidebar.radio[0].set_value("Evaluation").run()
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
