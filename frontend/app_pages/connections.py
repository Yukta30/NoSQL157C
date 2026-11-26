"""Connections: graph traversal tools.

  UC-13  Degrees of separation  shortest directed FOLLOWS path, up to 4 hops
  UC-8   Mutual connections     users followed by both of two users
"""

import streamlit as st

from frontend import components, data
from frontend.session import display_name, require_me

VIEWS = {
    "degrees": ":material/route: Degrees of separation",
    "mutual": ":material/join_inner: Mutual connections",
}

me = require_me("explore connections")
user = data.get_user(me)

components.page_header("Connections", "How are people connected?",
                       "Follow the graph: find the shortest follow path between two people, or who they both follow.")
st.caption("Tip: usernames are listed on the People page (All users).")


def _clean(username):
    return (username or "").strip().lstrip("@").lower()


def two_usernames(prefix, first_label, second_label, default_first, default_second, button):
    with st.form(f"{prefix}_form", border=False), components.card(f"{prefix}_form"):
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            first = st.text_input(first_label, value=default_first, key=f"{prefix}_from",
                                  icon=":material/alternate_email:")
            st.html("<div style='padding-bottom:0.55rem;font-size:1.3rem;color:#800020'>→</div>",
                    width="content")
            second = st.text_input(second_label, value=default_second, key=f"{prefix}_to",
                                   icon=":material/alternate_email:")
            submitted = st.form_submit_button(button, key=f"{prefix}_submit", type="primary",
                                              icon=":material/search:")
    return _clean(first), _clean(second), submitted


def path_chain(path):
    """The path as avatars joined by arrows."""
    with components.card("degrees_path"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small", wrap=True):
            for i, u in enumerate(path):
                if i:
                    st.html("<div style='font-size:1.4rem;color:#800020;padding:0 0.2rem'>→</div>",
                            width="content")
                with st.container(gap="xsmall", horizontal_alignment="center", width=120):
                    components.avatar(u, size=46)
                    components.user_link(u, label=f"**{display_name(u)}**")
                    st.caption(f"@{u['username']}")


# ---------- UC-13 ----------

def degrees_view():
    st.markdown("**Shortest follow path** from the first person to the second (up to 4 hops). "
                "Follows are one-way, so A → B can exist even when B → A doesn't.")
    first, second, submitted = two_usernames("degrees", "From username", "To username",
                                             user["username"], "", "Find path")
    if submitted:
        st.session_state["degrees_query"] = (first, second)
    query = st.session_state.get("degrees_query")
    if not query:
        return
    first, second = query
    if not first or not second:
        st.error("Enter both usernames.", icon=":material/error:")
        return
    try:
        result = data.degrees_of_separation(first, second, max_hops=4)
    except ValueError as e:
        st.error(str(e), icon=":material/error:")
        return

    if not result["found"]:
        components.empty_state(f"No connection found from @{first} to @{second} within "
                               f"{result['maxHops']} hops.", icon=":material/link_off:")
        return
    d = result["degrees"]
    with components.card("degrees_result"):
        left, right = st.columns([1, 3], vertical_alignment="center")
        left.metric("Degrees of separation", d)
        right.markdown(f"**@{first}** reaches **@{second}** in **{d} hop{'s' if d != 1 else ''}**"
                       + (" (same person)." if d == 0 else ":")
                       + ("" if d == 0 else "  \n" + " → ".join(f"@{u['username']}" for u in result["path"])))
    path_chain(result["path"])


# ---------- UC-8 ----------

def mutual_view():
    st.markdown("**People both users follow:** everyone A follows who B also follows.")
    first, second, submitted = two_usernames("mutual", "First username", "Second username",
                                             user["username"], "", "Find mutual connections")
    if submitted:
        st.session_state["mutual_query"] = (first, second)
    query = st.session_state.get("mutual_query")
    if not query:
        return
    first, second = query
    users_found = {u: data.get_user_by_username(u) for u in (first, second) if u}
    missing = [u for u in (first, second) if not u or users_found.get(u) is None]
    if missing:
        st.error("No user with username " + " or ".join(f"@{u}" for u in missing if u) + "."
                 if any(missing) else "Enter both usernames.", icon=":material/error:")
        return
    a, b = users_found[first], users_found[second]
    rows = data.mutual_following(a["userId"], b["userId"])
    st.markdown(f"**{len(rows)}** user{'s' if len(rows) != 1 else ''} followed by both "
                f"**{display_name(a)}** (@{first}) and **{display_name(b)}** (@{second}).")
    if not rows:
        components.empty_state("They don't follow anyone in common.", icon=":material/join_inner:")
        return
    following = data.following_ids(me)
    with components.card("mutual_list"):
        for i, row in enumerate(rows):
            if i:
                components.soft_divider()
            u = row["user"]
            pic, body, action = st.columns([0.7, 6, 1.7], vertical_alignment="center")
            with pic:
                components.avatar(u, size=40)
            with body:
                components.user_link(u)
                st.caption(f"{row['followers']:,} followers")
            with action:
                components.follow_toggle(me, u, u["userId"] in following, key=f"mutual_follow_{u['userId']}")


view = st.segmented_control("View", list(VIEWS), format_func=VIEWS.get, default="degrees",
                            key="connections_view", required=True, label_visibility="collapsed")
if view == "mutual":
    mutual_view()
else:
    degrees_view()
