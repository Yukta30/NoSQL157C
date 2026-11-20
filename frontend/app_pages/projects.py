"""Projects: create a project, invite people (team builder suggestions), manage the team.

Without ?project=... this lists your projects; with it, it shows one project.
"""

import streamlit as st

from frontend import components, data
from frontend.session import display_name, require_me


@st.dialog("New project", width="large")
def new_project_dialog(me):
    with st.form("new_project_form", border=False):
        title = st.text_input("Title", key="new_project_title", max_chars=80,
                              placeholder="e.g. Kaggle LLM competition")
        description = st.text_area("What's it about?", key="new_project_description", max_chars=500,
                                   placeholder="Goal, timeline, what kind of teammates you're looking for…")
        st.markdown("**Skills the team needs**")
        skills = components.tag_picker(data.list_skills(), "new_project_skills")
        size = st.number_input("Team size (including you)", min_value=2, max_value=8, value=4, step=1,
                               key="new_project_size", width=200)
        submitted = st.form_submit_button("Create project", key="new_project_submit", type="primary",
                                          icon=":material/add:")
    if submitted:
        try:
            project = data.create_project(me, title, description, skills, int(size))
        except ValueError as e:
            st.error(str(e), icon=":material/error:")
            return
        st.session_state["flash"] = ("ok", "Project created. Now invite your team!")
        st.query_params["project"] = project["projectId"]
        st.rerun()


# ---------- list ----------

def project_list(me):
    components.page_header("Projects", "Your projects",
                           "Start a project, invite the right people, and build your team.")
    if st.button("New project", key="new_project", type="primary", icon=":material/add:"):
        new_project_dialog(me)

    rows = data.user_projects(me)
    if not rows:
        components.empty_state("No projects yet. Create one and the team builder will suggest who to invite.",
                               icon=":material/rocket_launch:")
        return
    for row in rows:
        p = row["project"]
        with components.card(f"project_{p['projectId']}"):
            body, go = st.columns([5, 1.4], vertical_alignment="center")
            with body:
                st.markdown(f"#### {p['title']}")
                with st.container(horizontal=True, gap="small"):
                    components.status_badge(p["status"])
                    st.badge("Owner" if row["role"] == "owner" else f"Member · owner {display_name(row['owner'])}",
                             color="primary" if row["role"] == "owner" else "gray")
                    st.badge(f"{row['memberCount']}/{p['teamSize']} members", icon=":material/group:",
                             color="gray")
                    if row["role"] == "owner" and row["pendingInvites"]:
                        st.badge(f"{row['pendingInvites']} pending", icon=":material/schedule:", color="orange")
                components.skill_badges(row["skills"])
            with go:
                st.page_link(components.PROJECTS, label="Open", icon=":material/chevron_right:",
                             query_params={"project": p["projectId"]})


# ---------- one project ----------

def members_card(project):
    components.section(f"Team · {len(project['members'])} of {project['teamSize']}")
    with components.card("project_members"):
        for m in project["members"]:
            pic, body = st.columns([0.9, 6], vertical_alignment="center")
            with pic:
                components.avatar(m["user"], size=38)
            with body:
                components.user_link(m["user"])
                if m["role"] == "owner":
                    st.badge("Owner", color="primary")
        if project["openSpots"]:
            st.caption(f"{project['openSpots']} open spot{'s' if project['openSpots'] != 1 else ''}")


def coverage_card(project):
    if not project["coverage"]:
        return
    components.section("Skill coverage")
    with components.card("project_coverage"):
        st.dataframe(
            project["coverage"], hide_index=True,
            column_order=["skill", "weight", "coveredBy"],
            column_config={
                "skill": "Skill",
                "weight": st.column_config.ProgressColumn("Best on the team", min_value=0.0, max_value=1.0,
                                                          format="%.2f"),
                "coveredBy": st.column_config.TextColumn("Covered by", default="nobody yet"),
            },
            alt="How strongly the current team covers each needed skill",
        )


def invites_card(project, me):
    if not project["invites"]:
        return
    components.section("Invites")
    with components.card("project_invites"):
        for inv in project["invites"]:
            body, action = st.columns([5, 1.6], vertical_alignment="center")
            with body:
                with st.container(horizontal=True, gap="small", vertical_alignment="center"):
                    components.user_link(inv["user"])
                    components.status_badge(inv["status"])
                if inv.get("message"):
                    st.caption(f"“{inv['message']}”")
            with action:
                if inv["status"] == "pending":
                    st.button("Cancel", key=f"cancel_{inv['user']['userId']}", type="tertiary",
                              icon=":material/close:", on_click=components.run_action,
                              args=(data.cancel_invite, "Invite cancelled", project["projectId"], me,
                                    inv["user"]["userId"]))


def suggestions_card(project, me):
    components.section("Suggested people")
    with components.card("project_suggestions"):
        if project["status"] != "open":
            st.caption("This project isn't taking new members, so there's no one to invite.")
            return
        if not project["skills"]:
            st.caption("Add needed skills to get suggestions.")
            return
        try:
            result = data.suggest_members(project["projectId"])
        except ValueError as e:
            st.caption(str(e))
            return
        picks = [m for m in result["members"] if not m["isYou"] and not m.get("isMember")]
        if not picks:
            st.caption(result.get("note") or "Your team already covers the needed skills.")
            return
        st.caption(f"The team builder picks people who complement your current team "
                   f"(team coverage would be {result['coverageScore']:.0%}).")
        message = st.text_input("Message (optional)", key="invite_message", max_chars=200,
                                placeholder="Hi! Want to team up for this?", icon=":material/chat:")
        for m in picks:
            pic, body, action = st.columns([0.9, 5, 1.8], vertical_alignment="center")
            with pic:
                components.avatar(m, size=38)
            with body:
                components.user_link(m)
                components.bullets(m["reasons"])
            with action:
                st.button("Invite", key=f"invite_{m['userId']}", type="primary", icon=":material/send:",
                          width="stretch", on_click=components.run_action,
                          args=(data.invite, f"Invite sent to {display_name(m)}", project["projectId"], me,
                                m["userId"]),
                          kwargs={"message": message})
        st.caption("You can also invite anyone from their profile page.")


@st.dialog("Delete project?")
def confirm_delete(project, me):
    st.write(f"This permanently deletes **{project['title']}**, its team and all invites.")
    if st.button("Delete project", key="confirm_delete", type="primary", icon=":material/delete:"):
        try:
            data.delete_project(project["projectId"], me)
        except ValueError as e:
            st.error(str(e))
            return
        st.session_state["flash"] = ("ok", "Project deleted")
        del st.query_params["project"]
        st.rerun()


def owner_actions(project, me):
    with st.container(horizontal=True, gap="small"):
        if project["status"] == "closed":
            st.button("Reopen", key="project_reopen", icon=":material/lock_open:",
                      on_click=components.run_action,
                      args=(data.set_project_status, "Project reopened", project["projectId"], me, "open"))
        else:
            st.button("Close to new members", key="project_close", icon=":material/lock:",
                      on_click=components.run_action,
                      args=(data.set_project_status, "Project closed", project["projectId"], me, "closed"))
        if st.button("Delete", key="project_delete", icon=":material/delete:", type="tertiary"):
            confirm_delete(project, me)


def invitee_actions(project, me):
    with components.card("project_my_invite"):
        st.markdown(f"**{display_name(project['owner'])}** invited you to join this project.")
        with st.container(horizontal=True, gap="small"):
            st.button("Accept", key="project_accept", type="primary", icon=":material/check:",
                      on_click=components.run_action,
                      args=(data.respond_invite, f"You joined {project['title']}!", project["projectId"], me,
                            True))
            st.button("Decline", key="project_decline", icon=":material/close:",
                      on_click=components.run_action,
                      args=(data.respond_invite, "Invite declined", project["projectId"], me, False))


def project_detail(project_id, me):
    st.page_link(components.PROJECTS, label="All projects", icon=":material/chevron_left:")
    project = data.get_project(project_id)
    if project is None:
        st.error("That project doesn't exist any more.")
        return

    is_owner = project["owner"]["userId"] == me
    is_member = any(m["user"]["userId"] == me for m in project["members"])
    my_invite = next((i for i in project["invites"]
                      if i["user"]["userId"] == me and i["status"] == "pending"), None)

    components.page_header("Project", project["title"], project.get("description"))
    with st.container(horizontal=True, gap="small"):
        components.status_badge(project["status"])
        st.badge(f"{len(project['members'])}/{project['teamSize']} members", icon=":material/group:",
                 color="gray")
        st.badge(f"Owner: {display_name(project['owner'])}", icon=":material/person:", color="gray")
    components.skill_badges(project["skills"], color="primary")

    if my_invite:
        invitee_actions(project, me)
    if is_owner:
        owner_actions(project, me)
    elif is_member:
        st.button("Leave project", key="project_leave", icon=":material/logout:", type="tertiary",
                  on_click=components.run_action,
                  args=(data.leave_project, f"You left {project['title']}", project_id, me))

    members_card(project)
    coverage_card(project)
    if is_owner:
        suggestions_card(project, me)
        invites_card(project, me)


me = require_me("see projects")
project_id = st.query_params.get("project")
if project_id:
    project_detail(project_id, me)
else:
    project_list(me)
