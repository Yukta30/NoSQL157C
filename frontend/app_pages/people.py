"""People: browse and follow users.

  UC-10  All users            every user, including you and people you follow (paged)
  UC-12  Popular              most-followed users first
  UC-9   People you may know  exactly two FOLLOWS hops away (me -> A -> B)
  UC-5   Follow by username   follow anyone by @username (shows the error messages)
"""

import streamlit as st

from frontend import components, data
from frontend.session import display_name, require_me

PAGE_SIZE = 25
VIEWS = {
    "all": ":material/groups: All users",
    "popular": ":material/local_fire_department: Popular",
    "may_know": ":material/diversity_3: People you may know",
}

me = require_me("browse people")
user = data.get_user(me)
following = data.following_ids(me)

components.page_header("People", "Find people to follow",
                       "Browse everyone, see who's most followed, or meet people your connections follow.")


# ---------- UC-5: follow by username ----------

def follow_by_username():
    with st.form("follow_form", border=False), components.card("follow_form"):
        st.markdown("**Follow someone by username**")
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            username = st.text_input("Username", key="follow_username", placeholder="e.g. cdeotte",
                                     icon=":material/alternate_email:", label_visibility="collapsed")
            submitted = st.form_submit_button("Follow", key="follow_submit", type="primary",
                                              icon=":material/person_add:")
    if submitted:
        target = data.get_user_by_username(username.strip().lstrip("@").lower()) if username.strip() else None
        if target is None:
            st.error(f"No user with username @{username.strip().lstrip('@')}." if username.strip()
                     else "Enter a username.", icon=":material/error:")
            return
        try:
            data.follow(me, target["userId"])
        except ValueError as e:  # "You can't follow yourself." / "You already follow X."
            st.error(str(e), icon=":material/error:")
            return
        st.session_state["flash"] = ("ok", f"Following {display_name(target)}")
        st.rerun()


# ---------- shared row ----------

def person_row(u, key, detail=None):
    is_you = u["userId"] == me
    pic, body, action = st.columns([0.7, 6, 1.7], vertical_alignment="center")
    with pic:
        components.avatar(u, size=40)
    with body:
        label = f"**{display_name(u)}**" + (" (you)" if is_you else "") + f" · @{u['username']}"
        components.user_link(u, label=label)
        if detail:
            st.caption(detail)
    with action:
        components.follow_toggle(me, u, u["userId"] in following, key=key)


def people_list(rows, key_prefix, detail_fn):
    with components.card(f"{key_prefix}_list"):
        for i, row in enumerate(rows):
            if i:
                components.soft_divider()
            u = row.get("user", row)
            person_row(u, key=f"{key_prefix}_{u['userId']}", detail=detail_fn(row))


# ---------- UC-10: all users ----------

def all_users_view():
    total = data.count_users()
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    st.session_state.setdefault("people_page", 1)

    def jump_to_me():
        st.session_state["people_page"] = data.user_page_of(user["username"], PAGE_SIZE) + 1

    st.markdown(f"**{total:,} users**, sorted by username. Includes you and people you already follow.")
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.markdown("Page", width="content")
        page = st.number_input("Page", min_value=1, max_value=pages, key="people_page", width=140,
                               label_visibility="collapsed")
        st.markdown(f":gray[of {pages:,}]", width="content")
        st.space("stretch")
        st.button("Find me", key="people_find_me", icon=":material/my_location:", on_click=jump_to_me)
    rows = data.all_users((page - 1) * PAGE_SIZE, PAGE_SIZE)
    people_list(rows, "all", lambda r: f"{r['followers']:,} follower{'s' if r['followers'] != 1 else ''}"
                + (" · you follow them" if r["userId"] in following else ""))
    st.caption(f"Page {page:,} of {pages:,}")


# ---------- UC-12: popular ----------

def popular_view():
    rows = data.popular_users(limit=25)
    st.markdown("**The most-followed users**, ranked by number of followers.")
    with components.card("popular_list"):
        for i, row in enumerate(rows, start=1):
            if i > 1:
                components.soft_divider()
            rank, rest = st.columns([0.5, 9], vertical_alignment="center")
            with rank:
                st.markdown(f"### {i}")
            with rest:
                person_row(row["user"], key=f"popular_{row['user']['userId']}",
                           detail=f"{row['followers']:,} followers")


# ---------- UC-9: two-hop recommendations ----------

def may_know_view():
    st.markdown("**People followed by people you follow** (you → someone → them). "
                "You and people you already follow are left out; everyone appears once.")
    rows = data.two_hop_recommendations(me, limit=25)
    if not rows:
        components.empty_state("No suggestions yet. Follow a few people and their follows will show up here.",
                               icon=":material/diversity_3:")
        return

    def via(r):
        names = ", ".join(r["viaNames"])
        more = r["viaCount"] - len(r["viaNames"])
        return f"Followed by {names}" + (f" and {more} more you follow" if more > 0 else "") \
            + f" · {r['followers']:,} followers"

    people_list(rows, "mayknow", via)


follow_by_username()
view = st.segmented_control("View", list(VIEWS), format_func=VIEWS.get, default="all", key="people_view",
                            required=True, label_visibility="collapsed")
if view == "popular":
    popular_view()
elif view == "may_know":
    may_know_view()
else:
    all_users_view()
