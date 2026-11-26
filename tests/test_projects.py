"""Projects and team invites (backend/projects.py and the Projects/Inbox pages).
Works on either dataset (seed or Meta Kaggle).

These tests WRITE to the database: they create "zz_test_" users and their
projects, and delete them again (DETACH DELETE) after each test.

Run:  pytest tests/test_projects.py -v
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

from backend import accounts, projects, users  # noqa: E402
from backend.db import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "app.py")
PREFIX = "zz_test_"


def _clean():
    db.execute_query(f"MATCH (u:User)-[:OWNS]->(p:Project) WHERE u.username STARTS WITH '{PREFIX}' "
                     "DETACH DELETE p", write=True)
    db.execute_query(f"MATCH (u:User) WHERE u.username STARTS WITH '{PREFIX}' DETACH DELETE u", write=True)


@pytest.fixture(autouse=True)
def clean():
    try:
        db.verify_connection()
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")
    _clean()
    yield
    _clean()


@pytest.fixture(scope="module")
def skills():
    names = [s["name"] for s in users.list_skills()]
    if len(names) < 3:
        pytest.skip("skill vocabulary not loaded")
    return names


def user(name, skill_names=()):
    return accounts.register_user(PREFIX + name, name.title(), f"{name}@example.com", "password-123",
                                  skills=list(skill_names))["userId"]


@pytest.fixture
def team(skills):
    owner, bob, cara = user("owner", skills[:1]), user("bob", skills[1:2]), user("cara")
    p = projects.create_project(owner, "LLM comp", "Need help", skills[:3], team_size=3)
    return {"owner": owner, "bob": bob, "cara": cara, "pid": p["projectId"], "skills": skills[:3]}


# ---------- backend ----------

def test_create_project(team):
    p = projects.get_project(team["pid"])
    assert p["projectId"].startswith("p") and p["status"] == "open" and p["teamSize"] == 3
    assert p["owner"]["userId"] == team["owner"] and p["skills"] == sorted(team["skills"])
    assert [(m["user"]["userId"], m["role"]) for m in p["members"]] == [(team["owner"], "owner")]
    assert p["openSpots"] == 2 and p["invites"] == []
    assert [r["role"] for r in projects.get_user_projects(team["owner"])] == ["owner"]


@pytest.mark.parametrize("kw, message", [
    ({"title": "  "}, "title"),
    ({"team_size": 1}, "between 2 and"),
    ({"team_size": 9}, "between 2 and"),
    ({"skills": ["not-a-skill"]}, "not-a-skill"),
])
def test_create_project_validation(kw, message):
    owner = user("owner")
    args = {"title": "T", "description": "", "skills": [], "team_size": 3, **kw}
    with pytest.raises(ValueError, match=message):
        projects.create_project(owner, **args)


def test_invite_accept_flow(team):
    pid, owner, bob = team["pid"], team["owner"], team["bob"]
    projects.invite(pid, owner, bob, "join us!")
    assert projects.pending_invite_count(bob) == 1
    (inv,) = projects.get_inbox(bob)
    assert inv["project"]["projectId"] == pid and inv["message"] == "join us!"
    assert inv["inviter"]["userId"] == owner

    projects.respond(pid, bob, accept=True)
    p = projects.get_project(pid)
    assert {m["user"]["userId"] for m in p["members"]} == {owner, bob}
    assert p["invites"][0]["status"] == "accepted" and p["invites"][0]["respondedAt"]
    assert projects.pending_invite_count(bob) == 0
    assert [r["role"] for r in projects.get_user_projects(bob)] == ["member"]
    # Coverage now counts Bob's skill.
    assert any(c["coveredBy"] == "Bob" for c in p["coverage"])


def test_decline_and_reinvite(team):
    pid, owner, bob = team["pid"], team["owner"], team["bob"]
    projects.invite(pid, owner, bob)
    projects.respond(pid, bob, accept=False)
    p = projects.get_project(pid)
    assert p["invites"][0]["status"] == "declined" and len(p["members"]) == 1
    projects.invite(pid, owner, bob, "second try")  # allowed after a decline
    assert projects.get_inbox(bob)[0]["message"] == "second try"


def test_invite_rules(team):
    pid, owner, bob, cara = team["pid"], team["owner"], team["bob"], team["cara"]
    with pytest.raises(ValueError, match="Only the project owner"):
        projects.invite(pid, bob, cara)
    with pytest.raises(ValueError, match="already on this project"):
        projects.invite(pid, owner, owner)
    projects.invite(pid, owner, bob)
    with pytest.raises(ValueError, match="pending invite"):
        projects.invite(pid, owner, bob)
    with pytest.raises(ValueError, match="no pending invite"):
        projects.respond(pid, cara, accept=True)
    projects.cancel_invite(pid, owner, bob)
    assert projects.get_inbox(bob) == []


def test_team_fills_up_and_reopens(team):
    pid, owner, bob, cara = team["pid"], team["owner"], team["bob"], team["cara"]
    extra = user("dan")
    for person in (bob, cara, extra):
        projects.invite(pid, owner, person)
    projects.respond(pid, bob, True)
    projects.respond(pid, cara, True)
    assert projects.get_project(pid)["status"] == "full"
    with pytest.raises(ValueError, match="already full"):
        projects.respond(pid, extra, True)
    with pytest.raises(ValueError, match="isn't taking new members"):
        projects.invite(pid, owner, user("eve"))
    projects.leave(pid, cara)
    p = projects.get_project(pid)
    assert p["status"] == "open" and p["openSpots"] == 1


def test_owner_controls(team):
    pid, owner, bob = team["pid"], team["owner"], team["bob"]
    with pytest.raises(ValueError, match="Owners can't leave"):
        projects.leave(pid, owner)
    with pytest.raises(ValueError, match="Only the project owner"):
        projects.delete_project(pid, bob)
    projects.set_status(pid, owner, "closed")
    assert projects.get_project(pid)["status"] == "closed"
    assert projects.get_invitable_projects(owner, bob) == []
    projects.set_status(pid, owner, "open")
    assert [p["projectId"] for p in projects.get_invitable_projects(owner, bob)] == [pid]
    projects.delete_project(pid, owner)
    assert projects.get_project(pid) is None


def test_suggestions_build_on_current_members(team):
    pid, owner, bob = team["pid"], team["owner"], team["bob"]
    projects.invite(pid, owner, bob)
    projects.respond(pid, bob, True)
    result = projects.suggest_members(pid)
    ids = [m["userId"] for m in result["members"]]
    assert ids[:2] == [owner, bob]
    assert result["members"][1]["isMember"] and "Already on the team" in result["members"][1]["reasons"]
    assert len(ids) <= 3 and len(set(ids)) == len(ids)


def test_suggestions_skip_pending_and_declined(team):
    pid, owner = team["pid"], team["owner"]
    first = projects.suggest_members(pid)
    picked = [m["userId"] for m in first["members"] if not m["isYou"]]
    if not picked:
        pytest.skip("no one in the graph has these skills")
    projects.invite(pid, owner, picked[0])
    again = [m["userId"] for m in projects.suggest_members(pid)["members"]]
    assert picked[0] not in again


# ---------- pages ----------

def _app_as(user_id, page, **query):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = user_id
    at.run()
    at.switch_page(f"app_pages/{page}.py")
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def _clean_run(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_projects_page_lists_and_opens_project(team):
    at = _app_as(team["owner"], "projects")
    _clean_run(at)
    assert at.button(key="new_project")
    at = _app_as(team["owner"], "projects", project=team["pid"])
    _clean_run(at)
    assert at.title[0].value == "LLM comp"
    assert at.button(key="project_close") and at.button(key="project_delete")


def test_invite_from_suggestions_then_accept_in_inbox(team):
    at = _app_as(team["owner"], "projects", project=team["pid"])
    invite_buttons = [b for b in at.button if b.key and b.key.startswith("invite_")]
    if not invite_buttons:
        pytest.skip("no suggestions for these skills")
    invitee = invite_buttons[0].key.removeprefix("invite_")
    invite_buttons[0].click().run()
    _clean_run(at)
    assert projects.pending_invite_count(invitee) == 1
    projects.cancel_invite(team["pid"], team["owner"], invitee)  # don't leave invites on real users

    projects.invite(team["pid"], team["owner"], team["bob"], "come join")
    at = _app_as(team["bob"], "inbox")
    _clean_run(at)
    at.button(key=f"accept_{team['pid']}").click().run()
    _clean_run(at)
    assert team["bob"] in {m["user"]["userId"] for m in projects.get_project(team["pid"])["members"]}


def test_profile_has_invite_button_for_owner(team):
    at = _app_as(team["owner"], "profile", user=team["cara"])
    _clean_run(at)
    assert at.button(key=f"profile_invite_{team['pid']}")
