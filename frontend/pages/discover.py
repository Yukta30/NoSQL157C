import streamlit as st

from frontend import components, data
from frontend.session import get_me

st.title("Discover people")

term = st.text_input("Search by name or username", key="discover_q",
                     placeholder="e.g. alice", icon=":material/search:")

if not term.strip():
    st.caption("Type a name or username. Partial words work, so “ali ch” finds Alice Chen.")
    st.stop()

results = data.search_users(term, limit=30)
if not results:
    components.empty_state(f"No users match “{term.strip()}”.", icon=":material/search_off:")
    st.stop()

st.caption(f"{len(results)} result{'s' if len(results) != 1 else ''}")
me = get_me()
for user in results:
    with st.container(border=True):
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            components.user_link(user)
            components.user_badges(user)
        with right:
            components.follow_button(me, user, key=f"follow_{user['userId']}")
