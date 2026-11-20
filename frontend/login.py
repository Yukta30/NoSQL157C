"""Login screen, shown in place of every page until someone is logged in.

Layout: a colourful hero panel on the left (an illustrated network plus live
numbers from Neo4j) and an auth card on the right, with a separate card
underneath to switch between logging in and signing up.

Three ways in:
  * Log in       username + password, for accounts created in the app
  * Sign up      create an app account (backend/accounts.py)
  * Explore as   pick an imported Meta Kaggle member; they have no password,
                 so this is a read-and-try demo of their view
"""

import math
from html import escape

import streamlit as st

from frontend import components, data
from frontend.session import DEMO_USERS, display_name, set_me

# Burgundy-to-beige palette for the hero (matches the .auth-* rules in style.css).
GRADIENT = ["#4A0E1F", "#6D1A36", "#8C2A44", "#A65B5B", "#B98A68"]
BURGUNDY = "#800020"
# Well-known Kaggle grandmasters to fill the hero ring (skipped if not in the loaded data).
FEATURED_USERNAMES = ["abhishek", "cpmpml", "hengck23", "philippsinger", "titericz", "cdeotte"]
NODE_COLORS = ["#800020", "#A0522D", "#9E3B4E", "#8B6B3D", "#6D1A36", "#B5654F"]


def _set_mode(mode):
    st.session_state["login_mode"] = mode


def _welcome(user, message):
    set_me(user["userId"])
    st.session_state["flash"] = ("ok", message)
    st.rerun()


# ---------- hero ----------

def hero_svg(stats, people):
    """A phone-sized illustration: you in the middle of a small network, plus live counts."""
    w, h, cx, cy, r = 380, 560, 190, 270, 118
    stops = "".join(f"<stop offset='{i / (len(GRADIENT) - 1):.2f}' stop-color='{c}'/>"
                    for i, c in enumerate(GRADIENT))
    nodes, lines = [], []
    for i, name in enumerate(people[:7]):
        angle = -math.pi / 2 + i * 2 * math.pi / max(len(people[:7]), 1)
        x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
        dash = "" if i % 2 else " stroke-dasharray='5 5'"
        lines.append(f"<line x1='{cx}' y1='{cy}' x2='{x:.0f}' y2='{y:.0f}' stroke='white' "
                     f"stroke-opacity='0.75' stroke-width='2'{dash}/>")
        if i:
            px = cx + r * math.cos(angle - 2 * math.pi / len(people[:7]))
            py = cy + r * math.sin(angle - 2 * math.pi / len(people[:7]))
            lines.append(f"<line x1='{px:.0f}' y1='{py:.0f}' x2='{x:.0f}' y2='{y:.0f}' stroke='white' "
                         f"stroke-opacity='0.35' stroke-width='1.5'/>")
        initials = "".join(part[0] for part in name.split()[:2]).upper()
        color = NODE_COLORS[i % len(NODE_COLORS)]
        nodes.append(
            f"<circle cx='{x:.0f}' cy='{y:.0f}' r='25' fill='#FBF7F0' fill-opacity='0.97'/>"
            f"<text x='{x:.0f}' y='{y + 5:.0f}' text-anchor='middle' font-size='14' font-weight='700' "
            f"fill='{color}'>{escape(initials)}</text>"
            f"<text x='{x:.0f}' y='{y + 43:.0f}' text-anchor='middle' font-size='11' fill='white' "
            f"fill-opacity='0.9'>{escape(name if len(name) <= 14 else name.split()[0])}</text>")
    pills = [(f"{stats['users']:,}", "Kagglers"), (f"{stats['teams']:,}", "teams"),
             (f"{stats['follows']:,}", "follows")]
    pill_svg = "".join(
        f"<g transform='translate({22 + i * 114}, 476)'>"
        f"<rect width='106' height='56' rx='16' fill='#F5EBDD' fill-opacity='0.16'/>"
        f"<text x='53' y='25' text-anchor='middle' font-size='17' font-weight='800' fill='white'>{v}</text>"
        f"<text x='53' y='43' text-anchor='middle' font-size='11' fill='white' fill-opacity='0.85'>{label}</text>"
        f"</g>" for i, (v, label) in enumerate(pills))
    return f"""<svg viewBox='0 0 {w} {h}' width='100%' role='img' aria-label='Illustrated network of Kaggle members'
     xmlns='http://www.w3.org/2000/svg' font-family='Inter, -apple-system, Helvetica, Arial, sans-serif'>
  <defs>
    <linearGradient id='heroGrad' x1='0' y1='0' x2='0.7' y2='1'>{stops}</linearGradient>
    <filter id='glow' x='-50%' y='-50%' width='200%' height='200%'>
      <feGaussianBlur stdDeviation='10' result='b'/><feMerge><feMergeNode in='b'/><feMergeNode in='SourceGraphic'/></feMerge>
    </filter>
  </defs>
  <rect width='{w}' height='{h}' rx='40' fill='url(#heroGrad)'/>
  <circle cx='330' cy='70' r='90' fill='#F5EBDD' fill-opacity='0.10'/>
  <circle cx='40' cy='420' r='70' fill='#F5EBDD' fill-opacity='0.12'/>
  <text x='28' y='58' font-size='24' font-weight='800' fill='white'>Find your next</text>
  <text x='28' y='88' font-size='24' font-weight='800' fill='white'>Kaggle team.</text>
  <text x='28' y='114' font-size='13' fill='#F5EBDD' fill-opacity='0.9'>Real teammates, real medals, one graph.</text>
  {''.join(lines)}
  <circle cx='{cx}' cy='{cy}' r='40' fill='#FBF7F0' filter='url(#glow)'/>
  <text x='{cx}' y='{cy + 6}' text-anchor='middle' font-size='17' font-weight='800' fill='{BURGUNDY}'>You</text>
  {''.join(nodes)}
  {pill_svg}
</svg>"""


def hero():
    stats = data.graph_stats()
    people = []
    for user_id, _ in DEMO_USERS:
        u = data.get_user(user_id)
        if u:
            people.append(display_name(u))
    for username in FEATURED_USERNAMES:
        u = data.get_user_by_username(username)
        if u and display_name(u) not in people:
            people.append(display_name(u))
    people = people[:7]
    st.image(hero_svg(stats, people), width="stretch",
             alt=f"Illustrated network of Kaggle members: {stats['users']:,} members, "
                 f"{stats['teams']:,} teams, {stats['follows']:,} follows")


# ---------- auth card ----------

def wordmark(subtitle):
    st.html(f"<div class='auth-wordmark'>CS 157C Project</div>"
            f"<div class='auth-subtitle'>{escape(subtitle)}</div>")


def divider(text="OR"):
    st.html(f"<div class='auth-divider'><span>{escape(text)}</span></div>")


def login_card():
    with st.container(key="auth_card", gap="small"):
        wordmark("See who you could team up with next.")
        with st.form("login_form", border=False):
            username = st.text_input("Username", key="login_username", placeholder="Username",
                                     label_visibility="collapsed", autocomplete="username")
            password = st.text_input("Password", type="password", key="login_password", placeholder="Password",
                                     label_visibility="collapsed", autocomplete="current-password")
            submitted = st.form_submit_button("Log in", key="login_submit", type="primary", width="stretch")
        if submitted:
            user = data.authenticate(username, password)
            if user is None:
                st.error("Sorry, your username or password was incorrect.", icon=":material/lock:")
            else:
                _welcome(user, f"Welcome back, {display_name(user).split()[0]}!")

        divider()
        st.caption("Explore as a Kaggle member", text_alignment="center")
        demos = [u for u in (data.get_user(uid) for uid, _ in DEMO_USERS) if u]
        with st.container(horizontal=True, horizontal_alignment="center", gap="small"):
            for user in demos:
                st.button(display_name(user).split()[0], key=f"login_{user['userId']}", type="tertiary",
                          icon=":material/travel_explore:", on_click=set_me, args=(user["userId"],),
                          help=f"@{user['username']}: see the app as this member (no password needed)")
        with st.popover("Find another member", icon=":material/search:", type="tertiary", width="stretch"):
            term = st.text_input("Find a member", key="login_search", placeholder="Search by name or username",
                                 icon=":material/search:", label_visibility="collapsed")
            if term.strip():
                results = data.search_users(term, limit=8)
                if not results:
                    st.caption("No matching users.")
                for r in results:
                    st.button(f"{display_name(r)} · @{r['username']}", key=f"login_search_{r['userId']}",
                              type="tertiary", on_click=set_me, args=(r["userId"],))

    with st.container(key="auth_switch", horizontal=True, horizontal_alignment="center"):
        st.button("Don't have an account? **Sign up**", key="switch_to_signup", type="tertiary",
                  on_click=_set_mode, args=("signup",))


def signup_card():
    with st.container(key="auth_card", gap="small"):
        wordmark("Sign up to find teammates, follow Kagglers and build your dream team.")
        with st.form("signup_form", border=False):
            display = st.text_input("Full name", key="signup_display", placeholder="Full name",
                                    label_visibility="collapsed", autocomplete="name")
            username = st.text_input("Username", key="signup_username", placeholder="Username",
                                     label_visibility="collapsed", autocomplete="username",
                                     help="3-30 characters: lowercase letters, numbers, '.', '_' or '-'")
            password = st.text_input("Password", type="password", key="signup_password",
                                     placeholder="Password (8+ characters)", label_visibility="collapsed",
                                     autocomplete="new-password")
            confirm = st.text_input("Confirm password", type="password", key="signup_confirm",
                                    placeholder="Confirm password", label_visibility="collapsed",
                                    autocomplete="new-password")
            country = st.text_input("Country", key="signup_country", placeholder="Country (optional)",
                                    label_visibility="collapsed", autocomplete="country-name")
            with st.expander("Add your skills and interests (optional)", icon=":material/auto_awesome:"):
                st.caption("Used for recommendations and team building. You can change them later.")
                skills = components.tag_picker(data.list_skills(), "signup_skills")
                st.markdown("**Interests**")
                interests = components.tag_picker(data.list_interests(), "signup_interests")
            st.caption("Your password is stored only as a salted hash.", text_alignment="center")
            submitted = st.form_submit_button("Sign up", key="signup_submit", type="primary", width="stretch")
        if submitted:
            if password != confirm:
                st.error("The passwords don't match.", icon=":material/lock:")
            else:
                try:
                    user = data.register_user(username=username, display_name=display, password=password,
                                              skills=skills, interests=interests, country=country)
                except ValueError as e:
                    st.error(str(e), icon=":material/error:")
                else:
                    _welcome(user, f"Welcome to CS 157C Project, {display_name(user).split()[0]}!")

    with st.container(key="auth_switch", horizontal=True, horizontal_alignment="center"):
        st.button("Have an account? **Log in**", key="switch_to_login", type="tertiary",
                  on_click=_set_mode, args=("login",))


def render():
    mode = st.session_state.get("login_mode", "login")
    with st.container(horizontal=True, horizontal_alignment="center", key="auth_page"):
        with st.container(width=900):
            left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
            with left:
                hero()
            with right:
                signup_card() if mode == "signup" else login_card()
            st.html("<div class='auth-footer'>CS 157C · NoSQL · Neo4j graph of Meta Kaggle "
                    "competitions, teams and follows</div>")
