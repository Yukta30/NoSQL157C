"""The current user. The backend is stateless, so "who am I" lives here in
st.session_state and gets passed to every backend call that needs it."""

import streamlit as st

from frontend import data

# Quick picks for the demo seed data.
DEMO_USERS = [
    ("k1001", "Alice", "lots of data"),
    ("u5eed0000000000000000000000000002", "Lee", "new, empty account"),
]


def get_me():
    return st.session_state.get("me")


def set_me(user_id):
    st.session_state["me"] = user_id


def log_out():
    st.session_state.pop("me", None)


def require_me(action):
    """Return the current user id, or stop the page asking to pick one."""
    me = get_me()
    if not me:
        st.info(f"Pick a user in the sidebar to {action}.", icon=":material/person:")
        st.stop()
    return me


def display_name(user):
    return user.get("displayName") or user.get("username") or user.get("userId")


def render_sidebar():
    with st.sidebar:
        me = get_me()
        user = data.get_user(me) if me else None
        if me and user is None:  # e.g. database was reloaded
            log_out()
            me = None

        if me:
            st.caption("Logged in as")
            st.markdown(f"**{display_name(user)}**  \n@{user['username']}")
            st.button("Switch user", on_click=log_out, icon=":material/logout:",
                      width="stretch")
            return

        st.subheader("Log in as…")
        st.caption("No passwords; this demo just picks whose view to show.")
        for user_id, name, hint in DEMO_USERS:
            st.button(f"{name} ({hint})", key=f"login_{user_id}", on_click=set_me,
                      args=(user_id,), width="stretch")

        term = st.text_input("Or find someone", key="login_search", placeholder="name or username")
        if term.strip():
            results = data.search_users(term, limit=8)
            if not results:
                st.caption("No matching users.")
            for r in results:
                st.button(f"{display_name(r)} · @{r['username']}", key=f"login_search_{r['userId']}",
                          on_click=set_me, args=(r["userId"],), width="stretch")
