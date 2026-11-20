import streamlit as st

from frontend import components, data
from frontend.session import require_me

components.page_header("Recommendations", "For you")
me = require_me("get recommendations")

recs = data.recommend_users(me, limit=10)

if not recs:
    components.empty_state("No one to recommend right now. You may already follow everyone nearby.")
    st.stop()

if recs[0].get("fallback"):
    st.subheader("Popular in the community", anchor=False)
    st.markdown(":gray[We don't know your skills, interests or connections yet, so here are well-followed "
                "people to start with. Follow a few and this list gets personal.]")
else:
    st.markdown(":gray[Ranked by shared skills and interests (rarer ones count more), mutual connections, "
                "and past teams. People you already follow are left out.]")


def score_badge(rec):
    def show():
        if not rec.get("fallback"):
            st.badge(f"Match {rec['score']:.2f}", icon=":material/bolt:", color="primary",
                     help="Sum of the signals: "
                          + ", ".join(f"{k.replace('_', ' ')} {v:.2f}" for k, v in rec["breakdown"].items()))
    return show


for rec in recs:
    components.person_card(rec, key=f"rec_{rec['userId']}", me=me, lines=rec["reasons"],
                           extra=score_badge(rec))
