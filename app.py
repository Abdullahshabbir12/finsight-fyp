"""Start with: streamlit run app.py."""
import os
import sqlite3
from html import escape
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
from src.database.store import save_run
from src.ui.access import load_cloud_secrets, password_ok, shared_deployment
from src.ui.brand import side_brand
from src.ui.layout import CSS, NAV, STEPS
from src.ui.results import results_screen, evaluation_screen
from src.ui.workflow import setup_screen, processing_screen, verification_screen

st.set_page_config(page_title="BrokerLens | Financial research", page_icon=str(Path(__file__).parent / "src/ui/favicon.png"),
                   layout="wide", initial_sidebar_state="auto")
load_cloud_secrets()
load_dotenv()
st.markdown(CSS, unsafe_allow_html=True)
if not password_ok():
    st.stop()

if "_goto" in st.session_state:  # a screen asked to move on after an action
    st.session_state.step = st.session_state.pop("_goto")
with st.sidebar:
    st.markdown(side_brand(), unsafe_allow_html=True)
    step = st.radio("Step", STEPS, key="step", format_func=NAV.get, label_visibility="collapsed")
    if os.getenv("APP_PASSWORD") and st.button(":material/logout: Log out", width="stretch"):
        st.session_state.clear()
        st.rerun()
    if shared_deployment():
        st.markdown('<div class="bl-side-note">Shared test version: upload public annual reports only. Saved runs are visible to '
                    'every tester and are deleted when the app restarts, so download your report before leaving.</div>',
                    unsafe_allow_html=True)

run = st.session_state.get("run")
if run:
    status = "✓ verified" if run.verified_at and not run.review_draft else "verification pending"
    with st.container(border=True):
        info, save = st.columns([3, 1], vertical_alignment="center")
        info.markdown(f'<div class="bl-context"><b>{escape(run.company.name)}</b> · FY {run.company.financial_year} · '
                      f'{run.company.statement_basis} · {status}</div>', unsafe_allow_html=True)
        if save.button(":material/save: Save", width="stretch",
                       help="Shared with all testers and cleared on restart." if shared_deployment()
                       else "Stores page text and review history on this computer; the PDF itself is not saved."):
            try:
                save_run(run)
                st.toast("Run saved.")
            except (OSError, sqlite3.Error):
                st.error("Cannot write the database. Your current session is still available.")
    if run.is_demo:
        st.warning("DEMO / SYNTHETIC DATA: fictional company and sample analysis.")

if step == STEPS[0]:
    setup_screen()
elif not run:
    st.info("Start on **Home**: load the synthetic demo or upload an annual report.")
elif step == STEPS[1]:
    processing_screen(run)
elif step == STEPS[2]:
    verification_screen(run)
elif step == STEPS[4]:
    evaluation_screen(run)
else:
    results_screen(run)
st.divider()
st.caption("Decision-support prototype. Outputs require human review and do not replace professional judgment. "
           "[Source code](https://github.com/Abdullahshabbir12/finsight-fyp) (AGPL-3.0). Commodity prices: World Bank (CC BY 4.0).")
