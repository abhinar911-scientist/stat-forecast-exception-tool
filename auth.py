"""Password-gate for the Streamlit app.

Users live in .streamlit/secrets.toml (locally) or in the app's Secrets box
(Streamlit Community Cloud):

    [auth]
    cookie_name = "stf_exception_tool"

    [auth.users.abhi]
    name = "Abhi"
    password_hash = "$2b$12$..."

Hashes are generated with scripts/hash_password.py.
"""
from __future__ import annotations

import hmac
import bcrypt
import streamlit as st

MAX_ATTEMPTS = 8


def _users() -> dict:
    try:
        auth = st.secrets["auth"]
    except Exception:  # noqa: BLE001 - secrets missing entirely
        return {}
    users = auth.get("users", {}) if hasattr(auth, "get") else {}
    return {str(k): dict(v) for k, v in dict(users).items()}


def _verify(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"),
                              stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _check(username: str, password: str) -> tuple[bool, str]:
    users = _users()
    if not users:
        return False, "No users are configured. Add them under [auth.users] in secrets."
    record = None
    for key, value in users.items():
        if hmac.compare_digest(key.lower(), username.strip().lower()):
            record = value
            break
    if record is None:
        # Run a dummy hash check so a wrong username costs the same as a wrong password.
        bcrypt.checkpw(b"x", bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=4)))
        return False, "Incorrect username or password."
    if _verify(password, str(record.get("password_hash", ""))):
        st.session_state["auth_user"] = username.strip()
        st.session_state["auth_name"] = record.get("name", username.strip())
        return True, ""
    return False, "Incorrect username or password."


def login_gate() -> bool:
    """Return True when the visitor is signed in, otherwise render the form."""
    if st.session_state.get("authenticated"):
        return True

    st.session_state.setdefault("login_attempts", 0)

    left, mid, right = st.columns([1, 1.4, 1])
    with mid:
        st.markdown("### Statistical Forecast Exception List")
        st.caption("Sign in to continue")

        if st.session_state["login_attempts"] >= MAX_ATTEMPTS:
            st.error("Too many failed attempts. Reload the page to try again.")
            return False

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)

        if submitted:
            ok, message = _check(username, password)
            if ok:
                st.session_state["authenticated"] = True
                st.session_state["login_attempts"] = 0
                st.rerun()
            else:
                st.session_state["login_attempts"] += 1
                st.error(message)
    return False


def logout_button(container=None) -> None:
    target = container or st.sidebar
    name = st.session_state.get("auth_name", "")
    target.caption(f"Signed in as **{name}**")
    if target.button("Sign out", use_container_width=True):
        for key in ("authenticated", "auth_user", "auth_name"):
            st.session_state.pop(key, None)
        st.rerun()
