import streamlit as st

from frontend import components, data
from frontend.session import display_name, get_me

me = get_me()
user = data.get_user(me)

components.page_header("Home", f"Hi, {display_name(user).split()[0]}",
                       "Who do you want to work with today?")

term = st.text_input("Search people", key="discover_q", placeholder="Search by name or username",
                     icon=":material/search:", label_visibility="collapsed")

if not term.strip():
    components.section("Get started")
    shortcuts = [
        ("blue", ":material/favorite:", "People for you",
         "Matches from shared skills, interests and connections", components.RECOMMENDATIONS, None),
        ("orange", ":material/groups:", "Build a team",
         "Pick skills and get a team that covers them together", components.TEAM_BUILDER, None),
        ("red", ":material/rocket_launch:", "Your projects",
         "Start a project and invite people to your team", components.PROJECTS, None),
        ("green", ":material/hub:", "Your network",
         "Who you follow and who you've worked with", components.NETWORK, None),
        ("violet", ":material/person:", "Your profile",
         "Skills, interests, teams and medals", components.PROFILE, {"user": me}),
    ]
    for color, icon, title, blurb, page, params in shortcuts:
        with components.card(f"home_{title}"):
            text, go = st.columns([6, 1], vertical_alignment="center")
            with text:
                st.markdown(f"##### :{color}[{icon}] {title}", anchors=False)
                st.markdown(f":gray[{blurb}]")
            with go:
                st.page_link(page, label="Open", icon=":material/chevron_right:", query_params=params)
    st.stop()

results = data.search_users(term, limit=30)
if not results:
    components.empty_state(f"No users match “{term.strip()}”.", icon=":material/search_off:")
    st.stop()

st.caption(f"{len(results)} result{'s' if len(results) != 1 else ''}")
for result in results:
    components.person_card(result, key=f"search_{result['userId']}", me=me)
