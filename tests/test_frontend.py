"""Headless tests for the Streamlit frontend (streamlit.testing AppTest).

Logged out, only the login screen exists. Every feature page is rendered as
Alice and as Lee, plus a few checks of page-specific behaviour. Read-only:
nothing here clicks Follow.

They need Neo4j credentials in .env and the seed graph loaded (README,
"Running the frontend"); otherwise they're skipped.

Run:  pytest tests/test_frontend.py -v
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "app.py")

ALICE, BOB = "k1001", "k1002"
LEE = "u5eed0000000000000000000000000002"
USERS = {"alice": ALICE, "lee": LEE}
PAGES = ["discover", "profile", "recommendations", "team_builder", "projects", "inbox", "network"]


@pytest.fixture(scope="module", autouse=True)
def seed_loaded():
    """Skip unless Neo4j is reachable and holds the seed users."""
    try:
        from backend import users
        if users.get_user(ALICE) is None or users.get_user(LEE) is None:
            pytest.skip("database doesn't hold the seed graph")
    except Exception as e:  # unreachable, bad credentials, ...
        pytest.skip(f"Neo4j not available: {e}")


def open_page(page, me=None, **query_params):
    """Run the app as `me`, then switch to `page`. The app has to run once
    first so frontend/app.py sets up imports and navigation."""
    at = AppTest.from_file(APP, default_timeout=30)
    if me:
        at.session_state["me"] = me
    at.run()
    at.switch_page(f"app_pages/{page}.py")
    for key, value in query_params.items():
        at.query_params[key] = value
    return at.run()


def assert_clean(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("who", USERS)
@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, who):
    assert_clean(open_page(page, USERS[who]))


def test_logged_out_shows_login():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert_clean(at)
    assert at.button(key="login_submit") and at.button(key="switch_to_signup")
    assert at.button(key=f"login_{ALICE}") and at.button(key=f"login_{LEE}")


def test_logging_in_opens_home():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.button(key=f"login_{ALICE}").click().run()
    assert_clean(at)
    assert at.session_state["me"] == ALICE
    assert at.title[0].value == "Hi, Alice"


def test_search_finds_alice():
    at = open_page("discover", ALICE)
    at.text_input(key="discover_q").input("alice").run()
    assert_clean(at)
    assert [c.value for c in at.caption][0] == "1 result"


def test_profile_of_someone_else():
    at = open_page("profile", ALICE, user=BOB)
    assert_clean(at)
    assert at.title[0].value == "Bob Smith"
    assert "Your profile" in [link.proto.label for link in at.get("page_link")]


def test_unknown_profile_shows_error():
    at = open_page("profile", ALICE, user="nobody")
    assert not at.exception
    assert "No user with ID" in at.error[0].value


def test_new_user_gets_popular_fallback():
    at = open_page("recommendations", LEE)
    assert_clean(at)
    assert [s.value for s in at.subheader] == ["Popular in the community"]


def test_new_user_network_empty_state():
    at = open_page("network", LEE)
    assert_clean(at)
    assert "aren't connected to anyone yet" in at.info[0].value


def test_team_builder_builds_team():
    at = open_page("team_builder", ALICE)
    at.multiselect(key="team_skills_analysis").set_value(["nlp"])
    at.multiselect(key="team_skills_technique").set_value(["computer vision"])
    at.button(key="build_team").click()
    at.run()
    assert_clean(at)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Members"] == "3 / 3"
    assert metrics["Skills covered"] == "2 / 2"


def test_team_builder_cleared_after_switching_user():
    at = open_page("team_builder", ALICE)
    at.multiselect(key="team_skills_analysis").set_value(["nlp"])
    at.button(key="build_team").click()
    at.run()
    at.session_state["me"] = LEE
    at.run()
    assert_clean(at)
    assert not at.metric
    assert "switched users" in at.info[0].value
