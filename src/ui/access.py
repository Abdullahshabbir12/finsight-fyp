"""Settings and access control for a shared test deployment (Streamlit Community Cloud).

Locally nothing changes: settings come from .env and there is no password screen.
"""
import hmac
import os
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


def load_cloud_secrets() -> None:
    """Streamlit Cloud stores settings in st.secrets; the rest of FinSight reads environment variables."""
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
    st.title("FinSight")
    st.caption("Test deployment for a final-year project. Enter the password you were given.")
    with st.form("password"):
        entered = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Enter", type="primary")
    if submitted:
        if hmac.compare_digest(entered.encode(), expected.encode()):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def shared_deployment() -> bool:
    return os.getenv("FINSIGHT_SHARED_DEPLOYMENT", "").strip().lower() in {"1", "true", "yes"}
