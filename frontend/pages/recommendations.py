import streamlit as st

from frontend import components, data
from frontend.session import require_me

st.title("People to follow")
me = require_me("get recommendations")

recs = data.recommend_users(me, limit=10)

if not recs:
    components.empty_state("No one to recommend right now. You may already follow everyone nearby.")
    st.stop()

if recs[0].get("fallback"):
    st.subheader("Popular in the community")
    st.caption("We don't know your skills, interests or connections yet, so here are well-followed people "
               "to start with. Follow a few and recommendations will get personal.")
else:
    st.caption("Ranked by shared skills and interests (rarer ones count more), mutual connections, "
               "and past teams. People you already follow are left out.")

for rec in recs:
    with st.container(border=True):
        left, right = st.columns([5, 1], vertical_alignment="center")
        with left:
            components.user_link(rec)
            components.user_badges(rec)
            components.bullets(rec["reasons"])
        with right:
            components.follow_button(me, rec, key=f"rec_follow_{rec['userId']}")
            if not rec.get("fallback"):
                st.caption(f"Match score {rec['score']:.2f}",
                           help="Sum of the signals: "
                                + ", ".join(f"{k.replace('_', ' ')} {v:.2f}"
                                            for k, v in rec["breakdown"].items()))
