import streamlit as st

from frontend import components, data
from frontend.session import display_name, get_me

st.title("Build a team")
st.caption("Pick the skills your project needs. The builder picks people who together cover them best, "
           "instead of just the top individuals, and favours people who've worked together before.")

me = get_me()
skills = data.list_skills()
labels = {s["name"]: f"{s['name']} ({s['category']})" for s in skills}

with st.form("team_form", border=True):
    required = st.multiselect("Required skills", options=list(labels), format_func=labels.get,
                              placeholder="e.g. nlp, computer vision")
    left, right = st.columns(2, vertical_alignment="bottom")
    team_size = left.slider("Team size", min_value=1, max_value=6, value=3)
    include_me = right.toggle("Include me", value=bool(me), disabled=not me,
                              help="Start the team with you; your skills count toward coverage."
                                   if me else "Log in from the sidebar to include yourself.")
    submitted = st.form_submit_button("Build team", type="primary", icon=":material/groups:")

if submitted:
    if not required:
        st.warning("Pick at least one skill.")
        st.stop()
    st.session_state["team_request"] = (tuple(required), team_size, me, include_me and bool(me))

request = st.session_state.get("team_request")
if not request:
    st.stop()

req_skills, req_size, req_me, req_include = request
if req_me != me:  # the team was built for whoever was logged in before
    st.session_state.pop("team_request", None)
    components.empty_state("You switched users, so the previous team was cleared. Build a new one above.",
                           icon=":material/swap_horiz:")
    st.stop()

try:
    result = data.build_team(req_skills, req_size, req_me, req_include)
except ValueError as e:
    st.error(str(e))
    st.stop()

# ---------- summary ----------
st.divider()
cols = st.columns(3)
cols[0].metric("Coverage", f"{result['coverageScore']:.0%}",
               help="Average over required skills of the best strength anyone on the team has")
cols[1].metric("Members", f"{len(result['members'])} / {result['teamSize']}")
cols[2].metric("Skills covered", f"{len(result['coverage']) - len(result['missingSkills'])} / "
                                 f"{len(result['coverage'])}")

if result["unknownSkills"]:
    st.warning("Not in the skill list: " + ", ".join(result["unknownSkills"]))
if result["missingSkills"]:
    st.warning(result["note"])
elif result["note"]:
    st.info(result["note"])

team_col, compare_col = st.columns([3, 2], gap="large")

# ---------- the team ----------
with team_col:
    st.subheader("Suggested team")
    if not result["members"]:
        components.empty_state("Nobody in the graph has these skills.")
    for i, m in enumerate(result["members"], start=1):
        with st.container(border=True):
            left, right = st.columns([5, 2], vertical_alignment="center")
            with left:
                if m["isYou"]:
                    st.markdown(f"**{i}. {display_name(m)} (you)**")
                else:
                    components.user_link(m, label=f"{i}. {display_name(m)} · @{m['username']}")
                components.user_badges(m)
                components.bullets(m["reasons"])
            with right:
                components.follow_button(me, m, key=f"team_follow_{m['userId']}")
                if not m["isYou"]:
                    st.caption(f"Coverage +{m['coverageGain']:.2f}"
                               + (f" · chemistry +{m['chemistryBonus']:.2f}" if m["chemistryBonus"] else ""))

    if result["coverage"]:
        st.markdown("**Coverage by skill**")
        st.dataframe(
            result["coverage"], hide_index=True,
            column_order=["skill", "weight", "coveredByName"],
            column_config={
                "skill": "Skill",
                "weight": st.column_config.ProgressColumn("Best strength", min_value=0.0, max_value=1.0,
                                                          format="%.2f"),
                "coveredByName": st.column_config.TextColumn("Covered by", default="nobody"),
            },
        )

    if result["links"]:
        names = {m["userId"]: display_name(m) for m in result["members"]}
        st.markdown("**Existing ties within the team**")
        for link in result["links"]:
            if link["type"] == "WORKED_WITH":
                st.markdown(f"- {names[link['a']]} and {names[link['b']]} worked together "
                            f"({link['times']} team{'s' if link['times'] != 1 else ''})")
            else:
                st.markdown(f"- {names[link['a']]} and {names[link['b']]} are connected by a follow")

# ---------- compare with "just take the top N" ----------
with compare_col:
    st.subheader("Top individuals")
    st.caption("The strongest people for these skills on their own, for comparison. A team of the top few "
               "can overlap and leave gaps.")
    top = data.rank_candidates(req_skills, limit=8)
    if not top:
        components.empty_state("Nobody has these skills.")
    team_ids = {m["userId"] for m in result["members"]}
    for c in top:
        with st.container(border=True):
            components.user_link(c)
            matched = ", ".join(s["skill"] for s in c["skills"])
            st.caption(f"{c['skillsMatched']}/{c['skillsRequired']} skills ({matched}) · "
                       f"total strength {c['totalWeight']:.2f}"
                       + (" · on the team" if c["userId"] in team_ids else ""))
