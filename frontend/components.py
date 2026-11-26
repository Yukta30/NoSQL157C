"""Small UI pieces shared by several pages (iOS-style cards, rows, avatars)."""

import base64
import hashlib
from html import escape

import streamlit as st

from frontend import data
from frontend.session import display_name

# Page paths are relative to frontend/app.py (the entry point).
HOME = "app_pages/discover.py"
DISCOVER = HOME
PROFILE = "app_pages/profile.py"
NETWORK = "app_pages/network.py"
RECOMMENDATIONS = "app_pages/recommendations.py"
PROJECTS = "app_pages/projects.py"
PEOPLE = "app_pages/people.py"
CONNECTIONS = "app_pages/connections.py"
INBOX = "app_pages/inbox.py"
TEAM_BUILDER = "app_pages/team_builder.py"

TIER_COLORS = {
    "novice": "green",
    "contributor": "blue",
    "expert": "violet",
    "master": "orange",
    "grandmaster": "red",
    "staff": "gray",
}
MEDAL_ICONS = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}
MEDALS_LABEL = "Medals " + "".join(MEDAL_ICONS.values())

# Warm, muted avatar backgrounds that match the burgundy/beige theme.
AVATAR_COLORS = ["#800020", "#A0522D", "#6D1A36", "#8B6B3D", "#5E7D4E", "#3E5C76", "#9E3B4E", "#7A4E7E"]


# st.html content is isolated from page CSS, so these styles are inline.
_AVATAR_STYLE = ("display:flex;align-items:center;justify-content:center;border-radius:50%;"
                 "color:#FFFFFF;font-weight:700;letter-spacing:0.02em;font-family:inherit;")
_SECTION_STYLE = ("margin:0.9rem 0 -0.25rem 0.25rem;font-size:0.75rem;font-weight:700;"
                  "letter-spacing:0.08em;text-transform:uppercase;color:#9A8574;")


# ---------- building blocks ----------

def card(key):
    """A white, rounded inset card (styled in frontend/style.css)."""
    return st.container(border=True, key=f"card_{key}")


def eyebrow(label):
    """Small burgundy uppercase label above a page title."""
    st.html(f"<div class='page-eyebrow'>{escape(label)}</div>")


def page_header(label, title, subtitle=None, art=None):
    """Pill label, burgundy serif title and a subtitle: the same on every page.
    `art` (an image path or SVG string) shows an illustration on the right."""
    def text():
        eyebrow(label)
        st.title(title, anchor=False)
        if subtitle:
            st.markdown(subtitle)

    if art is None:
        with st.container(gap="small"):
            text()
        return
    with st.container(horizontal=True, vertical_alignment="center", gap="large", key="page_hero"):
        with st.container(gap="small"):
            text()
        st.image(str(art), width=300, alt="")


_SPARKLE_SVG_SRC = (
    "<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'>"
    "<path d='M22 2 L25.5 14.5 L38 18 L25.5 21.5 L22 34 L18.5 21.5 L6 18 L18.5 14.5 Z' fill='#800020'/>"
    "<path d='M8 26 L9.6 31.4 L15 33 L9.6 34.6 L8 40 L6.4 34.6 L1 33 L6.4 31.4 Z' fill='#800020'/>"
    "<path d='M33 1 L34 4 L37 5 L34 6 L33 9 L32 6 L29 5 L32 4 Z' fill='#B5652B'/></svg>")
# st.html strips inline <svg>, so the icon goes in as an <img> data URI.
_SPARKLE_SVG = ("<img alt='' width='40' height='40' src='data:image/svg+xml;base64,"
                + base64.b64encode(_SPARKLE_SVG_SRC.encode()).decode() + "'/>")


def form_title(title, subtitle=None):
    """Sparkle icon + bold burgundy heading inside a card (styled in style.css)."""
    sub = f"<div class='form-subtitle'>{escape(subtitle)}</div>" if subtitle else ""
    st.html(f"<div class='form-head'>{_SPARKLE_SVG}<div><div class='form-title'>{escape(title)}</div>"
            f"{sub}</div></div>")


# Small burgundy line icons (24x24) for stat circles and card titles.
_ICONS = {
    "target": "<circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='5'/><circle cx='12' cy='12' r='1.5' "
              "fill='#800020'/><path d='M12 12 L19 5 M16 5 h3 v3'/>",
    "people": "<circle cx='9' cy='8' r='3.2'/><path d='M3 19 a6 5.5 0 0 1 12 0'/><circle cx='17' cy='9' r='2.6'/>"
              "<path d='M15.5 14.2 a5 4.6 0 0 1 6 4.8'/>",
    "layers": "<path d='M12 3 L21 8 L12 13 L3 8 Z'/><path d='M3 12.5 L12 17.5 L21 12.5'/>"
              "<path d='M3 16.5 L12 21.5 L21 16.5'/>",
    "ties": "<circle cx='5' cy='6' r='2.5'/><circle cx='19' cy='6' r='2.5'/><circle cx='12' cy='18' r='2.5'/>"
            "<path d='M7.3 7.2 L10.8 16 M16.7 7.2 L13.2 16 M7.5 6 h9'/>",
}


def icon_html(name, size=22):
    """An <img> of one of _ICONS (st.html strips inline <svg>, data URIs are fine)."""
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='{size}' height='{size}' "
           f"fill='none' stroke='#800020' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
           f"{_ICONS[name]}</svg>")
    return (f"<img alt='' width='{size}' height='{size}' "
            f"src='data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}'/>")


def icon_circle(name):
    """Round blush badge with a burgundy icon, e.g. next to a metric."""
    st.html(f"<div class='icon-circle'>{icon_html(name)}</div>", width="content")


def card_title(icon, text):
    st.html(f"<div class='card-title'>{icon_html(icon, 20)}<span>{escape(text)}</span></div>")


def soft_divider():
    st.html("<div class='soft-divider'></div>")


def vertical_divider():
    st.html("<div class='v-divider'></div>", width="content")


def section(label):
    """Small gray uppercase label above a group of cards, like iOS Settings."""
    st.html(f"<div style='{_SECTION_STYLE}'>{escape(label)}</div>")


def avatar(user, size=44):
    """Colored circle with the user's initials."""
    name = display_name(user)
    initials = "".join(w[0] for w in name.replace(",", " ").split()[:2]).upper() or "?"
    digest = hashlib.md5(str(user.get("userId", name)).encode()).digest()
    color = AVATAR_COLORS[int.from_bytes(digest[:4], "big") % len(AVATAR_COLORS)]
    st.html(
        f"<div style='{_AVATAR_STYLE}width:{size}px;height:{size}px;background:{color};"
        f"font-size:{size * 0.38:.0f}px'>{escape(initials)}</div>",
        width="content",
    )


def user_link(user, label=None, help=None):
    """Link to a user's profile page. Default label: bold name and @username."""
    st.page_link(PROFILE, label=label or f"**{display_name(user)}** · @{user['username']}",
                 query_params={"user": user["userId"]}, help=help)


def user_badges(user):
    """Tier and 'new member' badges in one row."""
    with st.container(horizontal=True, gap="small"):
        tier = user.get("tier")
        if tier:
            st.badge(tier.title(), color=TIER_COLORS.get(tier, "gray"))
        if user.get("source") == "app":
            st.badge("New member", icon=":material/fiber_new:", color="green")


def person_card(user, key, me=None, label=None, lines=(), follow=True, extra=None):
    """One person as an inset card: avatar, name, badges, detail lines, and a
    Follow button on the right. `extra` is called inside the text column to
    add anything page-specific (badges, captions)."""
    with card(key):
        pic, body, action = st.columns([0.9, 5, 2], vertical_alignment="center")
        with pic:
            avatar(user)
        with body:
            user_link(user, label=label)
            user_badges(user)
            bullets(lines)
            if extra:
                extra()
        with action:
            if follow:
                follow_button(me, user, key=f"follow_{key}")


SKILL_CATEGORY_ORDER = ["data type", "task", "technique", "analysis", "packages"]


CATEGORY_ICONS = {
    "data type": ":material/dataset:",
    "task": ":material/task_alt:",
    "technique": ":material/psychology:",
    "analysis": ":material/analytics:",
    "packages": ":material/inventory_2:",
}
CATEGORY_PLACEHOLDERS = {
    "data type": "Choose data types…",
    "task": "Choose tasks…",
    "technique": "Choose techniques…",
    "analysis": "Choose analysis skills…",
    "packages": "Choose packages…",
}


def tag_picker(tags, key_prefix, default=(), persist=False, style="chips", columns=2):
    """Pick skills or interests, grouped by category. Returns the selected names.
    Works inside st.form.

    style="chips"     tappable chips, one row per category
    style="dropdown"  one searchable dropdown per category, in a grid
    """
    by_category = {}
    for tag in tags:
        by_category.setdefault(tag["category"], []).append(tag["name"])
    order = lambda c: (SKILL_CATEGORY_ORDER.index(c) if c in SKILL_CATEGORY_ORDER else 99, c)
    categories = sorted(by_category, key=order)
    persist_state = "session" if persist else None
    picked = []

    if style == "dropdown":
        grid = st.columns(columns, gap="medium")
        for i, category in enumerate(categories):
            options = sorted(by_category[category])
            label = category.capitalize() if len(by_category) > 1 else "Topics"
            icon = CATEGORY_ICONS.get(category, ":material/label:")
            with grid[i % columns]:
                chosen = st.multiselect(
                    f"{icon} {label}", options, key=f"{key_prefix}_{category}",
                    default=[t for t in default if t in options] or None,
                    placeholder=CATEGORY_PLACEHOLDERS.get(category, f"Choose {label.lower()}…"),
                    help=f"{len(options)} {label.lower()} skills", persist_state=persist_state,
                    select_all=False,
                )
            picked += chosen or []
        return picked

    for category in categories:
        options = sorted(by_category[category])
        chosen = st.pills(category.capitalize() if len(by_category) > 1 else "Topics", options,
                          selection_mode="multi", key=f"{key_prefix}_{category}",
                          default=[t for t in default if t in options] or None,
                          persist_state=persist_state)
        picked += chosen or []
    return picked


def medals_text(user):
    """'gold · silver · bronze' counts, short enough for a metric column."""
    return " · ".join(str(user.get(m + "s", 0)) for m in ("gold", "silver", "bronze"))


def follow_toggle(me, user, following, key):
    """Follow / Following button for lists, when the caller already knows the status.
    Always clickable (even on your own row), so the backend's error messages show:
    "You can't follow yourself." / "You already follow X." (UC-5)."""
    st.button(
        "Following" if following else "Follow",
        key=key,
        icon=":material/check:" if following else ":material/person_add:",
        type="secondary" if following else "primary",
        help="Click to unfollow" if following else None,
        on_click=_toggle_follow,
        args=(me, user["userId"], display_name(user), following),
        width="stretch",
    )


def bullets(lines):
    """A compact bullet list (one element, so no gaps between items)."""
    if lines:
        st.markdown("\n".join(f"- {line}" for line in lines))


def empty_state(message, icon=":material/info:"):
    st.info(message, icon=icon)


# ---------- follow button + flash messages ----------

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


def run_action(fn, success, *args, **kwargs):
    """Button callback: call a backend write, then leave a toast (or the error)
    for the next run. Use as on_click=run_action, args=(fn, "Done!", ...)."""
    try:
        fn(*args, **kwargs)
        _set_flash("ok", success)
    except ValueError as e:
        _set_flash("error", str(e))


STATUS_BADGES = {
    "open": ("Open", "green", ":material/lock_open:"),
    "full": ("Team complete", "primary", ":material/groups:"),
    "closed": ("Closed", "gray", ":material/lock:"),
    "pending": ("Pending", "orange", ":material/schedule:"),
    "accepted": ("Accepted", "green", ":material/check:"),
    "declined": ("Declined", "gray", ":material/close:"),
}


def status_badge(status):
    label, color, icon = STATUS_BADGES.get(status, (status.title(), "gray", None))
    st.badge(label, color=color, icon=icon)


def skill_badges(skills, color="gray"):
    """Needed skills as a row of small badges."""
    if skills:
        st.markdown(" ".join(f":{color}-badge[{s}]" for s in skills))


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


def follow_button(me, other_user, key, outline=False):
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
        type="secondary" if (following or outline) else "primary",
        help="Click to unfollow" if following else None,
        on_click=_toggle_follow,
        args=(me, other, display_name(other_user), following),
        width="stretch",
    )
