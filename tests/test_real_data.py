"""Smoke tests for the full Meta Kaggle graph (data/processed loaded into Neo4j).

The seed-graph suites (test_backend.py, test_frontend.py) skip themselves when
the real data is loaded; these do the opposite and skip on the seed graph.
Read-only: nothing here clicks Follow.

Run:  pytest tests/test_real_data.py -v
"""
import os
import time

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

from backend import recommendations, social, team_builder, users  # noqa: E402
from backend.db import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "app.py")

GIBA, CDEOTTE, FRANCOIS = "k54836", "k1723677", "k2909983"  # login-screen demo users


@pytest.fixture(scope="module", autouse=True)
def real_graph_loaded():
    try:
        n = db.execute_query("MATCH (u:User) RETURN count(u) AS n")[0]["n"]
    except Exception as e:  # unreachable, bad credentials, ...
        pytest.skip(f"Neo4j not available: {e}")
    if n < 10_000 or users.get_user(GIBA) is None:
        pytest.skip("database doesn't hold the Meta Kaggle graph (load data/processed)")


def test_demo_users_exist():
    for uid in (GIBA, CDEOTTE, FRANCOIS):
        assert users.get_user(uid) is not None, uid


def test_profile_counts_match_the_social_lists():
    profile = users.get_user_profile(GIBA)
    assert profile["followers"] == len(social.get_followers(GIBA)) > 1000
    assert profile["skills"] and profile["teams"]


@pytest.mark.parametrize("uid", [GIBA, CDEOTTE, FRANCOIS])
def test_recommendations_are_fast_and_explained(uid):
    start = time.time()
    recs = recommendations.recommend_users(uid, limit=10)
    assert time.time() - start < 15, "recommendations should not scan the whole graph"
    assert len(recs) == 10 and not recs[0]["fallback"]
    assert all(r["reasons"] for r in recs)
    assert [r["score"] for r in recs] == sorted((r["score"] for r in recs), reverse=True)
    following = {row["user"]["userId"] for row in social.get_following(uid)}
    assert not following & {r["userId"] for r in recs}


def test_ego_network_keeps_teammates_first():
    net = social.get_ego_network(GIBA, max_nodes=50)
    assert len(net["nodes"]) == 51  # Giba + the 50 closest of 1,000+
    teammates = {e["source"] if e["target"] == GIBA else e["target"]
                 for e in net["edges"] if e["type"] == "WORKED_WITH" and GIBA in (e["source"], e["target"])}
    assert len(teammates) == 50  # Giba has 100+ teammates, so they fill the view


def test_team_builder_covers_common_skills():
    team = team_builder.build_team(["nlp", "computer vision", "tabular"], team_size=3,
                                   current_user_id=FRANCOIS)
    assert team["missingSkills"] == [] and team["coverageScore"] > 0.9


@pytest.mark.parametrize("page", ["discover", "recommendations", "team_builder", "projects", "inbox", "network", "profile"])
def test_pages_render_as_giba(page):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = GIBA
    at.run()
    at.switch_page(f"app_pages/{page}.py")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_login_screen_offers_real_demo_users():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.button(key=f"login_{GIBA}") and at.button(key=f"login_{FRANCOIS}")


def test_team_builder_form_with_skill_chips_and_team_size():
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = FRANCOIS
    at.run()
    at.switch_page("app_pages/team_builder.py")
    at.run()
    at.multiselect(key="team_skills_analysis").set_value(["nlp"])
    at.multiselect(key="team_skills_technique").set_value(["computer vision"])
    at.number_input(key="team_size").set_value(4)
    at.button(key="build_team").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Members"].endswith("/ 4")
    assert metrics["Skills covered"] == "2 / 2"


def _built_team(skills=("nlp",), technique=("computer vision",)):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = FRANCOIS
    at.run()
    at.switch_page("app_pages/team_builder.py")
    at.run()
    at.multiselect(key="team_skills_analysis").set_value(list(skills))
    at.multiselect(key="team_skills_technique").set_value(list(technique))
    at.button(key="build_team").click()
    return at.run()


def test_results_view_and_edit_requirements():
    at = _built_team()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == "Team Recommendations"
    assert at.button(key="edit_requirements") and at.button(key="build_another")
    at.button(key="edit_requirements").click().run()
    assert at.button(key="build_team")  # back on the form ...
    assert at.multiselect(key="team_skills_analysis").value == ["nlp"]  # ... with the picks kept


def test_build_another_team_clears_everything():
    at = _built_team()
    at.button(key="build_another").click().run()
    assert not at.exception
    assert at.button(key="build_team") and not at.metric
    assert at.multiselect(key="team_skills_analysis").value == []


def test_add_to_team_pins_a_person():
    at = _built_team()
    team = {m.proto.label for m in at.get("page_link")}
    add = [b for b in at.button if b.key and b.key.startswith("pin_") and not b.disabled]
    assert add, "expected someone to add from Top individuals"
    person = add[-1].key.removeprefix("pin_")
    add[-1].click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["team_pinned"] == [person]
    assert at.button(key=f"unpin_{person}")  # shown on the suggested team with a Remove button
    at.button(key=f"unpin_{person}").click().run()
    assert at.session_state["team_pinned"] == []
    assert team  # page links rendered before and after
