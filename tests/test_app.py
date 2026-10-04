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
