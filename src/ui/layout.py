"""Shared page furniture: step navigation, page guidance, messages and responsive styling."""
import streamlit as st

STEPS = ["1 · Upload", "2 · Extract", "3 · Verify", "4 · Results", "5 · Evaluate"]

CSS = """<style>
.block-container {max-width: 1200px; padding: 3.75rem 1.5rem 3rem;}
.fs-brand {display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; margin-bottom: .5rem;}
.fs-brand b {font-size: 1.7rem; letter-spacing: -0.03em; color: #087f8c;}
.fs-brand span {color: #64748b; font-size: .9rem;}
/* Step bar: radio options drawn as pills */
div[data-testid="stRadio"] [role="radiogroup"] {gap: .4rem; flex-wrap: wrap;}
label[data-testid="stRadioOption"] {background: #ffffff; border: 1px solid #dce5ed; border-radius: 999px;
  padding: .3rem .85rem; margin: 0; font-weight: 500;}
label[data-testid="stRadioOption"][data-selected="true"] {border-color: #087f8c; background: #e3f1f3; color: #05616b;}
label[data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {display: none;}  /* hide the radio circle */
label[data-testid="stRadioOption"] p {margin: 0;}
[data-testid="stMetric"] {background: #ffffff; border: 1px solid #dce5ed; border-radius: 12px; padding: 12px 14px;}
[data-testid="stMetricValue"] {font-size: 1.4rem;}
[data-testid="stSidebar"] {border-right: 1px solid #dce5ed;}
@media (max-width: 640px) {
  .block-container {padding: 3.5rem .75rem 2rem;}
  .fs-brand b {font-size: 1.35rem;}
  label[data-testid="stRadioOption"] {padding: .25rem .6rem; font-size: .85rem;}
  [data-testid="stMetricValue"] {font-size: 1.1rem;}
  h2, h3 {font-size: 1.2rem;}
  /* Keep metric cards two per row instead of one long column */
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {flex-direction: row !important; flex-wrap: wrap !important; gap: .5rem !important;}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - .25rem) !important; min-width: calc(50% - .25rem) !important; width: calc(50% - .25rem) !important;}
}
</style>"""


def go_to(step: str) -> None:
    """Button callback: callbacks run before widgets are drawn, so the step bar can change."""
    st.session_state.step = step


def request_step(step: str) -> None:
    """From inside a screen (after the step bar is drawn): switch step on the next rerun."""
    st.session_state["_goto"] = step


def next_button(label: str, step: str, key: str) -> None:
    st.button(label, type="primary", on_click=go_to, args=(step,), key=key)


def page_header(title: str, guidance: list[str]) -> None:
    st.subheader(title)
    with st.container(border=True):
        st.markdown("**What to do here**\n" + "\n".join(f"- {line}" for line in guidance))


def flash(kind: str, text: str) -> None:
    """Show a message after the next rerun (st.rerun clears messages drawn before it)."""
    st.session_state.setdefault("_flash", []).append((kind, text))


def show_flash() -> None:
    for kind, text in st.session_state.pop("_flash", []):
        getattr(st, kind)(text)
