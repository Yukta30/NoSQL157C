"""Small UI pieces shared by several pages."""

import streamlit as st

from frontend import data
from frontend.session import display_name

# Page paths are relative to frontend/app.py (the entry point).
DISCOVER = "pages/discover.py"
PROFILE = "pages/profile.py"
NETWORK = "pages/network.py"

TIER_COLORS = {
    "novice": "green",
    "contributor": "blue",
    "expert": "violet",
    "master": "orange",
    "grandmaster": "red",
    "staff": "gray",
}
MEDAL_ICONS = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}


def user_link(user, help=None):
    """Link to a user's profile page."""
    st.page_link(PROFILE, label=f"{display_name(user)} · @{user['username']}",
                 query_params={"user": user["userId"]}, help=help)


def user_badges(user):
    """Tier and 'new member' badges in one row."""
    with st.container(horizontal=True, gap="small"):
        tier = user.get("tier")
        if tier:
            st.badge(tier.title(), color=TIER_COLORS.get(tier, "gray"))
        if user.get("source") == "app":
            st.badge("New member", icon=":material/fiber_new:", color="green")


def medals_text(user):
    parts = [f"{MEDAL_ICONS[m]} {user.get(m + 's', 0)}" for m in ("gold", "silver", "bronze")]
    return "  ".join(parts)


def _set_flash(kind, message):
    st.session_state["flash"] = (kind, message)


def show_flash():
    """Show (once) a message left by a button callback."""
    flash = st.session_state.pop("flash", None)
    if flash:
        kind, message = flash
        if kind == "error":
            st.error(message)
        else:
            st.toast(message, icon=":material/check:")


def _toggle_follow(me, other, name, currently_following):
    try:
        if currently_following:
            data.unfollow(me, other)
            _set_flash("ok", f"Unfollowed {name}")
        else:
            data.follow(me, other)
            _set_flash("ok", f"Following {name}")
    except ValueError as e:
        _set_flash("error", str(e))


def follow_button(me, other_user, key):
    """Follow / Unfollow toggle. Renders nothing on your own profile or when
    nobody is logged in."""
    other = other_user["userId"]
    if not me or me == other:
        return
    status = data.connection_status(me, other)
    if status is None:
        return
    following = status["following"]
    st.button(
        "Following" if following else ("Follow back" if status["followedBy"] else "Follow"),
        key=key,
        icon=":material/check:" if following else ":material/person_add:",
        type="secondary" if following else "primary",
        help="Click to unfollow" if following else None,
        on_click=_toggle_follow,
        args=(me, other, display_name(other_user), following),
    )


def bullets(lines):
    """A compact bullet list (one element, so no gaps between items)."""
    if lines:
        st.markdown("\n".join(f"- {line}" for line in lines))


def empty_state(message, icon=":material/info:"):
    st.info(message, icon=icon)
