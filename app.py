"""Start with: streamlit run app.py."""
import sqlite3
from dotenv import load_dotenv
import streamlit as st
from src.database.store import save_run
from src.ui.access import load_cloud_secrets, password_ok, shared_deployment
from src.ui.layout import CSS, STEPS
from src.ui.results import results_screen, evaluation_screen
from src.ui.workflow import setup_screen, processing_screen, verification_screen

st.set_page_config(page_title="FinSight | Financial research", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
load_cloud_secrets()
load_dotenv()
if not password_ok():
    st.stop()
st.markdown(CSS, unsafe_allow_html=True)
st.markdown('<div class="fs-brand"><b>◈ FinSight</b><span>Evidence-led financial research</span></div>', unsafe_allow_html=True)
if shared_deployment():
    st.info("Shared test version: upload public annual reports only. Saved runs are visible to every tester and are "
            "deleted when the app restarts, so download your report before leaving.", icon="ℹ️")

if "_goto" in st.session_state:  # a screen asked to move on after an action
    st.session_state.step = st.session_state.pop("_goto")
step = st.radio("Step", STEPS, horizontal=True, key="step", label_visibility="collapsed")
run = st.session_state.get("run")
if run:
    status = "✓ verified" if run.verified_at and not run.review_draft else "verification pending"
    info, save = st.columns([4, 1], vertical_alignment="center")
    info.caption(f"**{run.company.name}** · FY {run.company.financial_year} · {run.company.statement_basis} · {status}")
    if save.button("💾 Save run", width="stretch", help="Shared with all testers and cleared on restart." if shared_deployment()
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
    st.info("Start on **1 · Upload**: load the synthetic demo or upload an annual report.")
elif step == STEPS[1]:
    processing_screen(run)
elif step == STEPS[2]:
    verification_screen(run)
elif step == STEPS[4]:
    evaluation_screen(run)
else:
    results_screen(run)
st.divider()
st.caption("Decision-support prototype. Outputs require human review and do not replace professional judgment.")
