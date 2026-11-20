"""Inbox: project invites waiting for an answer."""

import streamlit as st

from frontend import components, data
from frontend.session import display_name, require_me

me = require_me("see your invites")
invites = data.inbox(me)

components.page_header("Inbox", "Invites",
                       "People who want you on their team. Accept to join the project.")

if not invites:
    components.empty_state("No invites right now. When someone invites you to a project, it shows up here.",
                           icon=":material/inbox:")
    st.page_link(components.PROJECTS, label="Start your own project", icon=":material/add:")
    st.stop()

for inv in invites:
    p = inv["project"]
    with components.card(f"invite_{p['projectId']}"):
        pic, body = st.columns([0.9, 6])
        with pic:
            components.avatar(inv["inviter"] or inv["owner"])
        with body:
            st.markdown(f"**{display_name(inv['inviter'] or inv['owner'])}** invited you to "
                        f"**{p['title']}**")
            if p.get("description"):
                st.markdown(f":gray[{p['description']}]")
            if inv.get("message"):
                st.markdown(f"> {inv['message']}")
            components.skill_badges(inv["skills"], color="primary")
            st.caption(f"{inv['memberCount']}/{p['teamSize']} members so far")
            with st.container(horizontal=True, gap="small"):
                st.button("Accept", key=f"accept_{p['projectId']}", type="primary", icon=":material/check:",
                          on_click=components.run_action,
                          args=(data.respond_invite, f"You joined {p['title']}!", p["projectId"], me, True))
                st.button("Decline", key=f"decline_{p['projectId']}", icon=":material/close:",
                          on_click=components.run_action,
                          args=(data.respond_invite, "Invite declined", p["projectId"], me, False))
                st.page_link(components.PROJECTS, label="View project", icon=":material/open_in_new:",
                             query_params={"project": p["projectId"]})
