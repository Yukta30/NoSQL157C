"""CS 157C Project frontend. Run from the project root:

    streamlit run frontend/app.py

Logged out, every URL shows the login screen (and keeps its address, so a
shared profile link opens after logging in). After picking a user, the
feature pages appear in a top navigation bar with an account menu.
"""

import sys
from pathlib import Path

# Streamlit puts frontend/ on sys.path; the backend lives one level up.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

FRONTEND = Path(__file__).resolve().parent
ASSETS = FRONTEND / "assets"
WIDE_PAGES = {"team_builder"}  # pages designed for the full width



def page_config(layout):
    """Set the page config exactly once per run: Streamlit doesn't reliably apply a
    second layout change in the same run (e.g. after st.rerun())."""
    st.set_page_config(page_title="CS 157C Project", page_icon=str(ASSETS / "icon.svg"), layout=layout)


def inject_style():
    """iOS-style card CSS. Call after st.navigation: elements written before it
    are dropped when the page changes."""
    st.html(FRONTEND / "style.css")


# Import order matters: backend/db.py raises at import time when .env is
# missing. require_backend() imports it inside a try and shows setup help, so
# nothing that imports `backend` (session, components, data, pages) may be
# imported above this point.
from frontend import startup  # noqa: E402

startup.require_backend()

from frontend import components, data, login, session  # noqa: E402

me = session.get_me()
user = data.get_user(me) if me else None
if me and user is None:  # e.g. the database was reloaded
    session.log_out()
    me = None

invites = data.pending_invite_count(me) if me else 0
pages = [
    st.Page("app_pages/discover.py", title="Home", icon=":material/home:", default=True),
    st.Page("app_pages/recommendations.py", title="For you", icon=":material/favorite:"),
    st.Page("app_pages/people.py", title="People", icon=":material/group:"),
    st.Page("app_pages/connections.py", title="Connections", icon=":material/route:"),
    st.Page("app_pages/team_builder.py", title="Team Builder", icon=":material/groups:"),
    st.Page("app_pages/projects.py", title="Projects", icon=":material/rocket_launch:"),
    st.Page("app_pages/inbox.py", title="Inbox", icon=":material/inbox:", url_path="inbox"),
    st.Page("app_pages/network.py", title="Network", icon=":material/hub:"),
    st.Page("app_pages/profile.py", title="Profile", icon=":material/person:"),
]

if not me:
    st.navigation(pages, position="hidden")
    page_config("wide")
    inject_style()
    login.render()
    st.stop()

st.logo(str(ASSETS / "icon.svg"), icon_image=str(ASSETS / "icon.svg"), size="large")
nav = st.navigation(pages, position="sidebar")
page_config("wide" if nav.url_path in WIDE_PAGES else "centered")
inject_style()
if invites:
    # Burgundy count bubble next to "Inbox" in the sidebar (number changes, so it's built here).
    st.html(f"<style>a[href$='/inbox']::after {{ content: '{int(invites)}'; }}</style>")

with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                  key="account_bar", gap="small"):
    st.page_link(components.INBOX, label=str(invites) if invites else "\u200b",
                 icon=":material/notifications:", help="Invites waiting for you" if invites else "Inbox")
    choice = st.menu_button(session.display_name(user), ["My profile", "Log out"],
                            key="account_menu", icon=":material/account_circle:", type="tertiary")
if choice == "My profile":
    st.switch_page(components.PROFILE, query_params={"user": me})
elif choice == "Log out":
    session.log_out()
    st.rerun()

components.show_flash()
nav.run()
