"""Start with: streamlit run app.py."""
import sqlite3
from dotenv import load_dotenv
import streamlit as st
from src.database.store import list_runs, load_run, save_run
from src.ui.access import load_cloud_secrets, password_ok, shared_deployment
from src.ui.results import results_screen, evaluation_screen
from src.ui.workflow import setup_screen, processing_screen, verification_screen, set_run

st.set_page_config(page_title="FinSight | Financial research", page_icon="◈", layout="wide")
load_cloud_secrets()
load_dotenv()
if not password_ok():
    st.stop()
st.markdown("""<style>
.block-container {max-width: 1500px; padding-top: 2rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {background: white; border: 1px solid #dce5ed; border-radius: 10px; padding: 16px;}
[data-testid="stMetricValue"] {font-size: 1.55rem;}
h1 {letter-spacing: -0.04em;}
[data-testid="stSidebar"] {border-right: 1px solid #dce5ed;}
</style>""", unsafe_allow_html=True)
st.title("FinSight")
st.caption("EVIDENCE-LED FINANCIAL RESEARCH · ACCOUNTING & FINANCE")
if shared_deployment():
    st.info("Shared test version. Upload public annual reports only: page text is sent to the AI provider. Saved runs are "
            "visible to every tester and are deleted whenever the app restarts, so download your report before leaving.")
st.sidebar.title("◈ FinSight")
st.sidebar.caption("Financial research workspace")
step = st.sidebar.radio("Workflow", ["Company & report", "Document processing", "Human verification", "Results & analysis", "Evaluation"])
run = st.session_state.get("run")
if run:
    st.sidebar.divider()
    st.sidebar.write(run.company.name)
    st.sidebar.caption(f"FY {run.company.financial_year} · {run.company.statement_basis.title()}")
    st.sidebar.caption("● Verification saved" if run.verified_at else "○ Verification pending")
    if run.is_demo:
        st.warning("DEMO / SYNTHETIC DATA — fictional company and sample analysis")
    if st.sidebar.button("Save run locally"):
        try:
            save_run(run)
            st.sidebar.success("Saved on this computer.")
        except (OSError, sqlite3.Error):
            st.sidebar.error("Cannot write the local database. Check folder permissions. Your current session is still available.")
with st.sidebar.expander("Open a saved run"):
    try:
        saved = list_runs()
        if saved:
            selected = st.selectbox("Saved analyses", [r[0] for r in saved], format_func=lambda rid: next(f"{'DEMO · ' if r[3] else ''}{r[1]} · {r[2][:16]}" for r in saved if r[0] == rid))
            if st.button("Open selected run"):
                set_run(load_run(selected))
                st.rerun()
        else:
            st.caption("No saved runs yet.")
    except (OSError, sqlite3.Error, ValueError):
        st.warning("Saved runs are unavailable. Check the database path and file permissions.")
st.sidebar.caption("Saved runs on this shared version are visible to all testers and are cleared on restart." if shared_deployment()
                   else "Saving stores extracted page text and review history locally. The original PDF stays in the current session only.")
if step == "Company & report":
    setup_screen()
elif not run:
    st.info("Upload an annual report or load the synthetic demo first.")
elif step == "Document processing":
    processing_screen(run)
elif step == "Human verification":
    verification_screen(run)
elif step == "Evaluation":
    evaluation_screen(run)
else:
    results_screen(run)
st.divider()
st.caption("Decision-support prototype. Outputs require human review and do not replace professional judgment.")
