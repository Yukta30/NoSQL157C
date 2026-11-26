import streamlit as st

from backend.accounts import can_edit_profile
from frontend import components, data
from frontend.session import display_name, get_me


@st.dialog("Edit profile", width="large")
def edit_profile(profile):
    """UC-4: change name, email and bio (plus country and self-declared skills/interests).
    The username can't be changed. App accounts only."""
    my_skills = [s["skill"] for s in profile["skills"]]
    my_interests = [i["interest"] for i in profile["interests"]]
    with st.form("edit_profile_form", border=False):
        st.text_input("Username", value=f"@{profile['username']}", disabled=True, key="edit_username",
                      help="Usernames can't be changed after registration.")
        left, right = st.columns(2)
        display = left.text_input("Name", value=profile.get("displayName") or "", key="edit_display")
        email = right.text_input("Email", value=profile.get("email") or "", key="edit_email",
                                 icon=":material/mail:")
        bio = st.text_area("Bio", value=profile.get("bio") or "", key="edit_bio", max_chars=300, height=80,
                           placeholder="A line about you (optional)")
        country = st.text_input("Country", value=profile.get("country") or "", key="edit_country",
                                icon=":material/public:")
        st.markdown("**Skills**")
        skills = components.tag_picker(data.list_skills(), "edit_skills", default=my_skills)
        with st.expander("Interests", icon=":material/interests:", expanded=bool(my_interests)):
            interests = components.tag_picker(data.list_interests(), "edit_interests", default=my_interests)
        saved = st.form_submit_button("Save changes", key="edit_save", type="primary", icon=":material/check:")
    if saved:
        try:
            data.update_profile(profile["userId"], display_name=display, email=email, bio=bio,
                                country=country, skills=skills, interests=interests)
        except ValueError as e:
            st.error(str(e), icon=":material/error:")
            return
        st.session_state["flash"] = ("ok", "Profile updated")
        st.rerun()


me = get_me()
user_id = st.query_params.get("user") or me

if not user_id:
    st.title("Profile", anchor=False)
    components.empty_state("Find someone on Home to see their profile.",
                           icon=":material/person:")
    st.page_link(components.DISCOVER, label="Go to Home", icon=":material/search:")
    st.stop()

profile = data.get_user_profile(user_id)
if profile is None:
    st.title("Profile", anchor=False)
    st.error(f"No user with ID `{user_id}`.")
    st.page_link(components.DISCOVER, label="Search for people", icon=":material/search:")
    st.stop()

is_me = user_id == me
name = display_name(profile)

if me and not is_me:
    st.page_link(components.PROFILE, label="Your profile", icon=":material/chevron_left:",
                 query_params={"user": me})

# ---------- header ----------
components.eyebrow("Your profile" if is_me else "Profile")
with components.card("profile_header"):
    pic, head, actions = st.columns([1.3, 5, 2], vertical_alignment="center")
    with pic:
        components.avatar(profile, size=72)
    with head:
        st.title(name, anchor=False)
        details = [f"@{profile['username']}"]
        if profile.get("country"):
            details.append(profile["country"])
        if profile.get("registerDate"):
            details.append(f"joined {profile['registerDate'][:4]}")
        st.markdown(":gray[" + " · ".join(details) + "]")
        if is_me and profile.get("email"):  # UC-3: email is only shown to its owner
            st.markdown(f":material/mail: {profile['email']}")
        if profile.get("bio"):
            st.markdown(f"_{profile['bio']}_")
        components.user_badges(profile)
    with actions:
        components.follow_button(me, profile, key="profile_follow")
        if me and not is_me:
            invitable = data.invitable_projects(me, user_id)
            if invitable:
                with st.popover("Invite", icon=":material/send:", width="stretch"):
                    st.markdown(f"**Invite {name.split()[0]} to a project**")
                    message = st.text_input("Message (optional)", key="profile_invite_message", max_chars=200,
                                            placeholder="Hi! Want to team up?")
                    for proj in invitable:
                        st.button(proj["title"], key=f"profile_invite_{proj['projectId']}",
                                  icon=":material/rocket_launch:", width="stretch",
                                  on_click=components.run_action,
                                  args=(data.invite, f"Invite sent to {name}", proj["projectId"], me, user_id),
                                  kwargs={"message": message})
        if is_me and can_edit_profile(profile):
            if st.button("Edit profile", key="profile_edit", icon=":material/edit:", width="stretch"):
                edit_profile(profile)

with components.card("profile_stats"):
    cols = st.columns(4)
    cols[0].metric("Followers", profile["followers"])
    cols[1].metric("Following", profile["following"])
    cols[2].metric("Collaborators", profile["collaborators"], help="People they've shared a team with")
    cols[3].metric(components.MEDALS_LABEL, components.medals_text(profile), help="Gold · silver · bronze")

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
        explanation = data.explain_recommendation(me, user_id)
        reasons = explanation["reasons"] if explanation else []
        if facts or reasons:
            components.section("You and " + name.split()[0])
            with components.card("profile_connection"):
                if facts:
                    st.markdown(" · ".join(f"**{f}**" for f in facts))
                components.bullets(reasons)

st.page_link(components.NETWORK, label=f"View {'your' if is_me else name + '’s'} network",
             icon=":material/hub:", query_params={"user": user_id})
st.space("small")

# ---------- details ----------
skills_tab, interests_tab, teams_tab, people_tab = st.tabs(
    [f"Skills ({len(profile['skills'])})", f"Interests ({len(profile['interests'])})",
     f"Teams ({len(profile['teams'])})", "Connections"]
)

STRENGTH = st.column_config.ProgressColumn("Strength", min_value=0.0, max_value=1.0, format="%.2f",
                                           help="Grows with competitions and medals in this area")

with skills_tab:
    if profile["skills"]:
        components.card("profile_skills").dataframe(
            profile["skills"], hide_index=True,
            column_order=["skill", "category", "weight", "competitions", "medals"],
            column_config={"skill": "Skill", "category": "Category", "weight": STRENGTH,
                           "competitions": "Competitions", "medals": "Medals"},
        )
    else:
        components.empty_state("No skills yet. Skills come from competition history." if not is_me
                               else "You haven't added any skills yet. Use Edit profile to add some.")

with interests_tab:
    if profile["interests"]:
        components.card("profile_interests").dataframe(
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
    for t, team in enumerate(profile["teams"]):
        with components.card(f"profile_team_{t}"):
            medal = components.MEDAL_ICONS.get(team["medal"] or "", "")
            st.markdown(f"**{team['competition']}** ({team['year']}) {medal}")
            rank = f"Rank #{team['privateRank']}" if team.get("privateRank") else "Unranked"
            if team.get("rankPct") is not None:
                pct = team["rankPct"] * 100
                rank += " · top <0.1%" if pct < 0.1 else f" · top {pct:.1f}%"
            st.caption(f"Team “{team['teamName']}” · {team['teamSize']} members · {rank}")
            if team["teammates"]:
                with st.container(horizontal=True, gap="small"):
                    for mate in team["teammates"]:
                        st.page_link(components.PROFILE, label=display_name(mate),
                                     icon=":material/person:", query_params={"user": mate["userId"]})

CONNECTIONS_SHOWN = 25  # real users can have thousands of followers

with people_tab:
    groups = [
        ("Followers", data.followers(user_id), None),
        ("Following", data.following(user_id), None),
        ("Collaborators", data.collaborators(user_id), "times"),
    ]
    for col, (title, rows, extra) in zip(st.columns(3), groups):
        with col, components.card(f"profile_{title.lower()}"):
            st.markdown(f"**{title}** :gray[{len(rows)}]")
            if not rows:
                st.caption("Nobody yet.")
            for row in rows[:CONNECTIONS_SHOWN]:
                help_text = f"{row[extra]} shared team(s)" if extra else None
                components.user_link(row["user"], label=display_name(row["user"]), help=help_text)
            if len(rows) > CONNECTIONS_SHOWN:
                st.caption(f"+{len(rows) - CONNECTIONS_SHOWN:,} more")
