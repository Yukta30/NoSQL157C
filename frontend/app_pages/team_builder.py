"""Team builder: pick skills (form view), then see Team Recommendations (results view).

Session state:
  team_request   (skills, size, me, include_me) of the last build
  team_pinned    people added by hand from "Top individuals"; the team is rebuilt around them
  team_editing   True while the form is reopened with "Edit requirements"
"""

from html import escape
from pathlib import Path

import streamlit as st

from frontend import components, data
from frontend.session import display_name, get_me

ART = Path(__file__).resolve().parent.parent / "assets" / "team_cards.svg"
SORTS = {
    "Total strength": lambda c: (-c["totalWeight"], c["username"]),
    "Skills matched": lambda c: (-c["skillsMatched"], -c["totalWeight"], c["username"]),
    "Coverage gain": lambda c: (-c["gain"], -c["totalWeight"], c["username"]),
}

me = get_me()
skills = data.list_skills()
st.session_state.setdefault("team_pinned", [])


# ---------- state changes (button callbacks) ----------

def edit_requirements():
    st.session_state["team_editing"] = True


def build_another():
    for key in ("team_request", "team_editing"):
        st.session_state.pop(key, None)
    st.session_state["team_pinned"] = []
    for category in {s["category"] for s in skills}:
        st.session_state[f"team_skills_{category}"] = []


def pin(user_id):
    if user_id not in st.session_state["team_pinned"]:
        st.session_state["team_pinned"].append(user_id)


def unpin(user_id):
    st.session_state["team_pinned"] = [u for u in st.session_state["team_pinned"] if u != user_id]


# ---------- form view ----------

def form_view():
    components.page_header(
        "Team builder", "Build a team",
        "Pick the skills your project needs. The builder picks people who together cover them best, instead "
        "of just the top individuals, and favours people who've worked together before.", art=ART)

    with st.form("team_form", border=False), components.card("team_form"):
        components.form_title("What skills does your project need?",
                              "Pick from each category. Type to search, or choose as many as you like.")
        required = components.tag_picker(skills, "team_skills", persist=True, style="dropdown")
        components.soft_divider()
        with st.container(horizontal=True, vertical_alignment="bottom", gap="large", key="team_actions"):
            team_size = st.number_input("Team size", min_value=1, max_value=6, value=3, step=1,
                                        key="team_size", persist_state="session", width=150)
            components.vertical_divider()
            include_me = st.toggle("Include me", value=bool(me), disabled=not me, key="team_include_me",
                                   help="Start the team with you; your skills count toward coverage.")
            st.space("stretch")
            submitted = st.form_submit_button("Build team :material/arrow_forward:", key="build_team",
                                              type="primary", icon=":material/groups:")

    if submitted:
        if not required:
            st.warning("Pick at least one skill.")
            return
        request = (tuple(required), int(team_size), me, include_me and bool(me))
        if request[:2] != (st.session_state.get("team_request") or (None, None))[:2]:
            st.session_state["team_pinned"] = []  # new requirements: start over
        st.session_state["team_request"] = request
        st.session_state["team_editing"] = False
        st.rerun()


# ---------- results view ----------

def results_header():
    with st.container(horizontal=True, vertical_alignment="bottom", gap="large"):
        with st.container(gap="small"):
            st.html("<div class='breadcrumb'>Team Builder &nbsp;›&nbsp; <b>Results</b></div>")
            st.title("Team Recommendations", anchor=False)
            st.markdown("People who best match your project's skill needs, with coverage and strength insights.")
        with st.container(horizontal=True, gap="small", width="content"):
            st.button("Edit requirements", key="edit_requirements", icon=":material/edit:",
                      on_click=edit_requirements)
            st.button("Build another team", key="build_another", icon=":material/person_add:", type="primary",
                      on_click=build_another)


def stats_card(result):
    covered = len(result["coverage"]) - len(result["missingSkills"])
    stats = [
        ("target", "Coverage", f"{result['coverageScore']:.0%}",
         "Average over the required skills of the best strength anyone on the team has"),
        ("people", "Members", f"{len(result['members'])} / {result['teamSize']}", None),
        ("layers", "Skills covered", f"{covered} / {len(result['coverage'])}", None),
    ]
    with components.card("team_stats"):
        for col, (icon, label, value, help_text) in zip(st.columns(3), stats):
            with col, st.container(horizontal=True, vertical_alignment="center", gap="medium"):
                components.icon_circle(icon)
                st.metric(label, value, help=help_text)


def member_row(m, i, pinned):
    pic, body, action = st.columns([0.8, 6, 1.6], vertical_alignment="center")
    with pic:
        components.avatar(m, size=48)
    with body:
        if m["isYou"]:
            st.markdown(f"**{i}. {display_name(m)} (you)**")
        else:
            components.user_link(m, label=f"**{i}. {display_name(m)}** · @{m['username']}")
        components.user_badges(m)
        reasons = ["Added by you" if r == "Already on the team" else r for r in m["reasons"]]
        components.bullets(reasons)
        if not m["isYou"] and not m.get("isMember"):
            with st.container(horizontal=True, gap="small"):
                st.badge(f"+{m['coverageGain']:.2f} coverage", icon=":material/trending_up:", color="green")
                if m["chemistryBonus"]:
                    st.badge(f"+{m['chemistryBonus']:.2f} chemistry", icon=":material/favorite:", color="orange")
    with action:
        if m["userId"] in pinned:
            st.button("Remove", key=f"unpin_{m['userId']}", icon=":material/close:", type="tertiary",
                      on_click=unpin, args=(m["userId"],))
        components.follow_button(me, m, key=f"team_follow_{m['userId']}", outline=True)


def suggested_tab(result, pinned):
    with components.card("team_members"):
        if not result["members"]:
            components.empty_state("Nobody in the graph has these skills.")
        for i, m in enumerate(result["members"], start=1):
            if i > 1:
                components.soft_divider()
            member_row(m, i, pinned)

    left, right = st.columns([1.55, 1], gap="medium")
    with left, components.card("team_coverage"):
        components.card_title("target", "Coverage by skill")
        st.dataframe(
            result["coverage"], hide_index=True,
            column_order=["skill", "weight", "coveredByName"],
            column_config={
                "skill": "Skill",
                "weight": st.column_config.ProgressColumn("Best strength", min_value=0.0, max_value=1.0,
                                                          format="%.2f"),
                "coveredByName": st.column_config.TextColumn("Covered by", default="nobody"),
            },
            alt="How strongly the team covers each required skill",
        )
    with right, components.card("team_ties"):
        components.card_title("ties", "Existing ties within the team")
        names = {m["userId"]: display_name(m) for m in result["members"]}
        ties = []
        for link in result["links"]:
            if link["type"] == "WORKED_WITH":
                ties.append(f"{names[link['a']]} and {names[link['b']]} worked together "
                            f"({link['times']} team{'s' if link['times'] != 1 else ''})")
            else:
                ties.append(f"{names[link['a']]} and {names[link['b']]} are connected by a follow")
        if ties:
            components.bullets(ties)
        else:
            st.caption("No one on this team has worked together or followed each other yet.")


def _short(skill):
    return {"automatic speech recognition": "ASR", "natural language processing": "NLP"}.get(skill, skill)


def individual_card(c, team_ids, pinned, team_full):
    with components.card(f"top_{c['userId']}"):
        pic, who, action = st.columns([0.85, 1.9, 2.25], vertical_alignment="top", gap="small")
        with pic:
            components.avatar(c, size=50)
        with who:
            st.markdown(f"**{display_name(c)}**  \n:gray[@{c['username']}]")
            components.user_badges(c)
        with action:
            if c["userId"] in team_ids:
                st.button("On team", key=f"pin_{c['userId']}", icon=":material/check:", disabled=True,
                          width="stretch")
            else:
                st.button("Add", key=f"pin_{c['userId']}", icon=":material/add:", width="stretch",
                          disabled=team_full, help="Team is full" if team_full else None,
                          on_click=pin, args=(c["userId"],))
        st.html(
            "<div class='stat-strip'>"
            f"<div><div class='v'>{c['skillsMatched']} / {c['skillsRequired']}</div><div class='l'>Skills</div></div>"
            f"<div><div class='v'>{c['totalWeight']:.2f}</div><div class='l'>Total strength</div></div>"
            f"<div><div class='v gain'>+{c['gain']:.2f}</div><div class='l'>Coverage</div></div>"
            "</div>")
        st.markdown("**Top skills**")
        top = [_short(s["skill"]) for s in c["skills"]]
        shown = top[:3] + ([f"+{len(top) - 3}"] if len(top) > 3 else [])
        components.skill_badges(shown)


def individuals_tab(req_skills, result, pinned, team_full):
    my_weights = {}
    if result["members"] and result["members"][0]["isYou"]:
        my_weights = {s["skill"]: s["weight"] for s in result["members"][0]["skills"]}
    top = data.rank_candidates(req_skills, limit=12, exclude=(me,) if me else ())
    if not top:
        components.empty_state("Nobody has these skills.")
        return
    for c in top:  # what each person would add on top of you
        c["gain"] = sum(max(0.0, s["weight"] - my_weights.get(s["skill"], 0.0)) for s in c["skills"])

    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("The strongest people for these skills on their own. Add someone and the team is rebuilt "
                   "around them.")
        st.space("stretch")
        sort = st.selectbox("Sort by", list(SORTS), key="top_sort", format_func=lambda s: f"Sort by: {s}",
                            label_visibility="collapsed", width=230)
    top = sorted(top, key=SORTS[sort])
    team_ids = {m["userId"] for m in result["members"]}
    for i in range(0, len(top), 3):
        for col, c in zip(st.columns(3, gap="medium"), top[i:i + 3]):
            with col:
                individual_card(c, team_ids, pinned, team_full)


def results_view(request):
    req_skills, req_size, req_me, req_include = request
    pinned = st.session_state["team_pinned"]
    try:
        result = data.build_team(req_skills, req_size, req_me, req_include, tuple(pinned))
    except ValueError as e:
        st.error(str(e))
        return
    team_full = len(pinned) + (1 if req_include else 0) >= req_size

    results_header()
    stats_card(result)
    if result["unknownSkills"]:
        st.warning("Not in the skill list: " + ", ".join(result["unknownSkills"]))
    if result["missingSkills"]:
        st.warning(result["note"])
    elif result["note"]:
        st.info(result["note"])

    suggested, individuals = st.tabs(["Suggested team", "Top individuals"])
    with suggested:
        suggested_tab(result, pinned)
    with individuals:
        individuals_tab(req_skills, result, pinned, team_full)


# ---------- page ----------
request = st.session_state.get("team_request")
if request and request[2] != me:  # built for whoever was logged in before
    st.session_state.pop("team_request", None)
    st.session_state["team_pinned"] = []
    form_view()
    components.empty_state("You switched users, so the previous team was cleared. Build a new one above.",
                           icon=":material/swap_horiz:")
elif request and not st.session_state.get("team_editing"):
    results_view(request)
else:
    form_view()
