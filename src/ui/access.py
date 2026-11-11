"""Settings and access control for a shared test deployment (Streamlit Community Cloud).

Locally nothing changes: settings come from .env and there is no password screen.
"""
import hmac
import os
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from src.ui.brand import login_panel


def load_cloud_secrets() -> None:
    """Streamlit Cloud stores settings in st.secrets; the rest of BrokerLens reads environment variables."""
    try:
        secrets = dict(st.secrets)
    except (StreamlitSecretNotFoundError, FileNotFoundError):
        return
    for key, value in secrets.items():
        if isinstance(value, (str, int, float, bool)) and key not in os.environ:
            os.environ[key] = str(value)


def password_ok() -> bool:
    """Show a password screen when APP_PASSWORD is set, so a shared link cannot spend the API quota freely."""
    expected = os.getenv("APP_PASSWORD", "")
    if not expected or st.session_state.get("authenticated"):
        return True
    panel, form = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    panel.markdown(login_panel(), unsafe_allow_html=True)
    with form:
        st.markdown('<div class="bl-welcome">Welcome back</div>', unsafe_allow_html=True)
        st.caption("Sign in to BrokerLens with the password you were given. Test deployment for a final-year project.")
        with st.form("password", border=False):
            entered = st.text_input("Password", type="password", placeholder="Enter your password", icon=":material/lock:")
            submitted = st.form_submit_button("Continue →", type="primary", width="stretch")
        st.caption(":material/shield: Password-protected test deployment. Upload public annual reports only.")
    if submitted:
        if hmac.compare_digest(entered.encode(), expected.encode()):
            st.session_state.authenticated = True
            st.rerun()
        form.error("Incorrect password.")
    return False


def shared_deployment() -> bool:
    return os.getenv("FINSIGHT_SHARED_DEPLOYMENT", "").strip().lower() in {"1", "true", "yes"}
