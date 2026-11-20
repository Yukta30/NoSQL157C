"""The current user. The backend is stateless, so "who am I" lives here in
st.session_state and gets passed to every backend call that needs it."""

import streamlit as st

# Quick picks on the login screen. Only the ones present in the loaded data are
# shown: the first group is real Meta Kaggle users, the second the seed graph.
DEMO_USERS = [
    ("k54836", "grandmaster with a big network"),        # titericz (Giba)
    ("k2909983", "master, a few teams and follows"),     # frlemarchand
    ("k1723677", "grandmaster, most-followed"),          # cdeotte
    ("k1001", "lots of data to explore"),                # seed: Alice
    ("u5eed0000000000000000000000000002", "brand-new, empty account"),  # seed: Lee
]


def get_me():
    return st.session_state.get("me")


def set_me(user_id):
    st.session_state["me"] = user_id


def log_out():
    st.session_state.pop("me", None)
    st.session_state.pop("team_request", None)


def require_me(action):
    """Return the current user id, or stop the page asking to log in."""
    me = get_me()
    if not me:
        st.info(f"Log in to {action}.", icon=":material/person:")
        st.stop()
    return me


def display_name(user):
    return user.get("displayName") or user.get("username") or user.get("userId")
