"""Shared page furniture: navigation, page guidance, messages and the BrokerLens styling."""
import streamlit as st
from src.ui.brand import SERIF

STEPS = ["1 · Upload", "2 · Extract", "3 · Verify", "4 · Results", "5 · Evaluate"]
# Sidebar labels; the step values stay the same so saved state and links keep working.
NAV = {"1 · Upload": ":material/home: Home", "2 · Extract": ":material/document_scanner: Extract",
       "3 · Verify": ":material/fact_check: Verify", "4 · Results": ":material/monitoring: Research",
       "5 · Evaluate": ":material/analytics: Evaluate"}

CSS = """<style>
:root {--bl-green:#1d4a3b; --bl-deep:#12332a; --bl-cream:#e9e3d4; --bl-ivory:#f3eee2; --bl-card:#fffdf8;
       --bl-line:#e3dccd; --bl-muted:#6f7c75; --bl-mint:#e4efe8;}
.block-container {max-width: 1240px; padding: 2.4rem 2rem 3rem;}
h1, h2, h3 {letter-spacing: -0.01em;}

/* Sidebar: brand and menu */
[data-testid="stSidebar"] {min-width: 236px !important; max-width: 262px !important;}
.bl-side-brand {display: flex; align-items: center; gap: .55rem; padding: .1rem 0 1.1rem; margin-bottom: .9rem;
  border-bottom: 1px solid rgba(233,227,212,.16);}
.bl-word {font-family: SERIF; font-size: 1.42rem; color: var(--bl-ivory); line-height: 1.1;}
.bl-tag {font-size: .6rem; letter-spacing: .14em; text-transform: uppercase; color: rgba(233,227,212,.62); margin-top: .2rem;}
.bl-side-note {font-size: .78rem; color: rgba(233,227,212,.68); line-height: 1.45; margin-top: 1rem;}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> div[data-testid="stRadio"]),
[data-testid="stSidebar"] div[data-testid="stRadio"], [data-testid="stSidebar"] div[data-testid="stRadio"] > div {width: 100% !important;}
[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] {flex-direction: column; align-items: stretch; gap: .2rem; width: 100%;}
[data-testid="stSidebar"] label[data-testid="stRadioOption"] {display: flex; width: 100%; box-sizing: border-box; background: transparent;
  border: 0; border-radius: 10px; padding: .62rem .8rem; color: var(--bl-cream); font-weight: 500; font-size: .95rem;}
[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover {background: rgba(233,227,212,.08);}
[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {background: var(--bl-green); color: #fff;
  box-shadow: inset 3px 0 0 #9cc5b0;}
[data-testid="stSidebar"] [data-testid="stButton"] button {background: transparent; color: var(--bl-cream);
  border: 1px solid rgba(233,227,212,.25);}

/* Radios in the page (e.g. finding status) drawn as pills */
div[data-testid="stRadio"] [role="radiogroup"] {gap: .4rem; flex-wrap: wrap;}
label[data-testid="stRadioOption"] {background: var(--bl-card); border: 1px solid var(--bl-line); border-radius: 999px;
  padding: .3rem .85rem; margin: 0; font-weight: 500;}
label[data-testid="stRadioOption"][data-selected="true"] {border-color: var(--bl-green); background: var(--bl-mint); color: var(--bl-green);}
label[data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) {display: none;}  /* hide the radio circle */
label[data-testid="stRadioOption"] p {margin: 0;}

/* Cards */
[data-testid="stMetric"], .bl-stat {background: var(--bl-card); border: 1px solid var(--bl-line); border-radius: 14px;
  padding: 14px 16px; box-shadow: 0 1px 2px rgba(18,51,42,.05);}
[data-testid="stMetricValue"] {font-family: SERIF; font-size: 1.55rem;}
[data-testid="stMetricLabel"] p {color: var(--bl-muted);}
[data-testid="stExpander"] details {background: var(--bl-card); border-radius: 12px;}
div[data-testid="stVerticalBlock"]:has(> div > [data-testid="stVerticalBlockBorderWrapper"]) {gap: 1rem;}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {background: var(--bl-card);}
.stTabs [data-baseweb="tab-list"] {gap: 1.1rem; border-bottom: 1px solid var(--bl-line);}
.stTabs [data-baseweb="tab"] {font-weight: 500; padding-left: 0; padding-right: 0;}
.bl-context {display: flex; align-items: center; gap: .5rem; color: var(--bl-muted); font-size: .92rem;}
.bl-context b {color: #1c2a24;}

/* Home hero and statistics */
.bl-hero {position: relative; overflow: hidden; border-radius: 18px; padding: 2.1rem 2.2rem; min-height: 168px; margin-bottom: 1.1rem;
  background: linear-gradient(118deg, #12332a 0%, #1d4a3b 58%, #2b5d4b 100%);}
.bl-hero-text {position: relative; z-index: 1; max-width: 36rem;}
.bl-hero-text h1 {font-family: SERIF; font-weight: 400; color: var(--bl-ivory); font-size: 2.35rem; margin: 0 0 .45rem; padding: 0;}
.bl-hero-text p {color: rgba(243,238,226,.82); margin: 0; font-size: 1rem;}
.bl-skyline {position: absolute; right: 0; bottom: 0; width: 62%; height: 100%; pointer-events: none;}
.bl-stats {display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .9rem; margin-bottom: 1.3rem;}
.bl-stat .material-symbols-rounded {font-family: 'Material Symbols Rounded'; font-size: 21px; line-height: 1; color: var(--bl-green);
  background: var(--bl-mint); border-radius: 8px; padding: 5px; display: inline-block; font-feature-settings: 'liga';}
.bl-stat-value {font-family: SERIF; font-size: 1.75rem; color: #1c2a24; margin-top: .55rem; line-height: 1.15;}
.bl-stat-label {color: var(--bl-muted); font-size: .85rem;}

/* Sign-in */
.bl-login-panel {position: relative; overflow: hidden; border-radius: 20px; min-height: 540px; display: flex; align-items: center;
  justify-content: center; text-align: center; background: linear-gradient(160deg, #12332a 0%, #1d4a3b 100%);}
.bl-login-panel .bl-skyline {width: 100%; height: 34%; opacity: .8;}
.bl-login-inner {position: relative; z-index: 1; padding: 2rem;}
.bl-login-word {font-family: SERIF; font-size: 2.7rem; color: var(--bl-ivory); margin-top: .3rem;}
.bl-login-tag {letter-spacing: .2em; font-size: .68rem; text-transform: uppercase; color: rgba(243,238,226,.75);}
.bl-rule {width: 56px; height: 1px; background: rgba(243,238,226,.4); margin: 1.4rem auto;}
.bl-login-quote {font-family: SERIF; font-style: italic; color: var(--bl-ivory); font-size: 1.3rem; line-height: 1.5;}
.bl-welcome {font-family: SERIF; font-size: 2.3rem; color: #1c2a24; margin: 0 0 .2rem;}

@media (max-width: 640px) {
  .block-container {padding: 3.2rem .8rem 2rem;}
  label[data-testid="stRadioOption"] {padding: .25rem .6rem; font-size: .85rem;}
  [data-testid="stMetricValue"] {font-size: 1.15rem;}
  h2, h3 {font-size: 1.3rem;}
  .bl-hero {padding: 1.4rem 1.2rem; min-height: 0;}
  .bl-hero-text h1 {font-size: 1.7rem;}
  .bl-stats {grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem;}
  .bl-stat-value {font-size: 1.35rem;}
  .bl-login-panel {min-height: 300px;}
  .bl-login-word {font-size: 2rem;}
  /* Keep metric cards two per row instead of one long column */
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {flex-direction: row !important; flex-wrap: wrap !important; gap: .5rem !important;}
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - .25rem) !important; min-width: calc(50% - .25rem) !important; width: calc(50% - .25rem) !important;}
}
</style>""".replace("SERIF", SERIF)


def go_to(step: str) -> None:
    """Button callback: callbacks run before widgets are drawn, so the navigation can change."""
    st.session_state.step = step


def request_step(step: str) -> None:
    """From inside a screen (after the navigation is drawn): switch step on the next rerun."""
    st.session_state["_goto"] = step


def next_button(label: str, step: str, key: str) -> None:
    st.button(label, type="primary", on_click=go_to, args=(step,), key=key)


def page_header(title: str, guidance: list[str]) -> None:
    st.header(title, anchor=False)
    with st.container(border=True):
        st.markdown("**What to do here**\n" + "\n".join(f"- {line}" for line in guidance))


def flash(kind: str, text: str) -> None:
    """Show a message after the next rerun (st.rerun clears messages drawn before it)."""
    st.session_state.setdefault("_flash", []).append((kind, text))


def show_flash() -> None:
    for kind, text in st.session_state.pop("_flash", []):
        getattr(st, kind)(text)
