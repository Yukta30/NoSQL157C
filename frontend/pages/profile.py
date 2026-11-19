import streamlit as st

from frontend import components, data
from frontend.session import display_name, get_me

me = get_me()
user_id = st.query_params.get("user") or me

if not user_id:
    st.title("Profile")
    components.empty_state("Pick a user in the sidebar to see your profile, or find someone on Discover.",
                           icon=":material/person:")
    st.page_link(components.DISCOVER, label="Go to Discover", icon=":material/search:")
    st.stop()

profile = data.get_user_profile(user_id)
if profile is None:
    st.title("Profile")
    st.error(f"No user with ID `{user_id}`.")
    st.page_link(components.DISCOVER, label="Search for people", icon=":material/search:")
    st.stop()

is_me = user_id == me
name = display_name(profile)

if me and not is_me:
    st.page_link(components.PROFILE, label="Your profile", icon=":material/arrow_back:",
                 query_params={"user": me})

# ---------- header ----------
head, actions = st.columns([4, 1], vertical_alignment="bottom")
with head:
    st.title(name + (" (you)" if is_me else ""))
    details = [f"@{profile['username']}"]
    if profile.get("country"):
        details.append(profile["country"])
    if profile.get("registerDate"):
        details.append(f"joined {profile['registerDate'][:4]}")
    st.caption(" · ".join(details))
    components.user_badges(profile)
with actions:
    components.follow_button(me, profile, key="profile_follow")

cols = st.columns(4)
cols[0].metric("Followers", profile["followers"])
cols[1].metric("Following", profile["following"])
cols[2].metric("Collaborators", profile["collaborators"], help="People they've shared a team with")
cols[3].metric("Medals", components.medals_text(profile))

# ---------- how you're connected ----------
if me and not is_me:
    status = data.connection_status(me, user_id)
    if status:
        facts = []
        if status["mutual"]:
            facts.append("You follow each other")
        elif status["followedBy"]:
            facts.append("Follows you")
        if status["workedTogether"]:
            n = status["workedTogetherTimes"]
            facts.append(f"Worked together on {n} team{'s' if n != 1 else ''}")
        if status["mutualFollowing"]:
            n = status["mutualFollowing"]
            facts.append(f"You both follow {n} {'person' if n == 1 else 'people'}")
        if facts:
            st.markdown(" · ".join(f"**{f}**" for f in facts))

    explanation = data.explain_recommendation(me, user_id)
    if explanation and explanation["reasons"]:
        with st.expander("Why you might team up"):
            components.bullets(explanation["reasons"])

st.page_link(components.NETWORK, label=f"View {'your' if is_me else name + '’s'} network",
             icon=":material/hub:", query_params={"user": user_id})

# ---------- details ----------
skills_tab, interests_tab, teams_tab, people_tab = st.tabs(
    [f"Skills ({len(profile['skills'])})", f"Interests ({len(profile['interests'])})",
     f"Teams ({len(profile['teams'])})", "Connections"]
)

STRENGTH = st.column_config.ProgressColumn("Strength", min_value=0.0, max_value=1.0, format="%.2f",
                                           help="Grows with competitions and medals in this area")

with skills_tab:
    if profile["skills"]:
        st.dataframe(
            profile["skills"], hide_index=True,
            column_order=["skill", "category", "weight", "competitions", "medals"],
            column_config={"skill": "Skill", "category": "Category", "weight": STRENGTH,
                           "competitions": "Competitions", "medals": "Medals"},
        )
    else:
        components.empty_state("No skills yet. Skills come from competition history." if not is_me
                               else "You don't have any skills yet. They're built from competition history.")

with interests_tab:
    if profile["interests"]:
        st.dataframe(
            profile["interests"], hide_index=True,
            column_order=["interest", "category", "weight", "competitions"],
            column_config={"interest": "Interest", "category": "Category", "weight": STRENGTH,
                           "competitions": "Competitions"},
        )
    else:
        components.empty_state("No interests yet.")

with teams_tab:
    if not profile["teams"]:
        components.empty_state("No competition teams yet.")
    for team in profile["teams"]:
        with st.container(border=True):
            medal = components.MEDAL_ICONS.get(team["medal"] or "", "")
            st.markdown(f"**{team['competition']}** ({team['year']}) {medal}")
            rank = f"Rank #{team['privateRank']}" if team.get("privateRank") else "Unranked"
            if team.get("rankPct") is not None:
                rank += f" · top {team['rankPct'] * 100:.1f}%"
            st.caption(f"Team “{team['teamName']}” · {team['teamSize']} members · {rank}")
            if team["teammates"]:
                with st.container(horizontal=True, gap="small"):
                    for mate in team["teammates"]:
                        st.page_link(components.PROFILE, label=display_name(mate),
                                     icon=":material/person:", query_params={"user": mate["userId"]})

with people_tab:
    groups = [
        ("Followers", data.followers(user_id), None),
        ("Following", data.following(user_id), None),
        ("Collaborators", data.collaborators(user_id), "times"),
    ]
    for col, (title, rows, extra) in zip(st.columns(3), groups):
        with col:
            st.subheader(f"{title} ({len(rows)})")
            if not rows:
                st.caption("Nobody yet.")
            for row in rows:
                help_text = f"{row[extra]} shared team(s)" if extra else None
                components.user_link(row["user"], help=help_text)
