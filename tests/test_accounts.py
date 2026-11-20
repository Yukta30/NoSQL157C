"""User registration, password login and profile editing (backend/accounts.py
and the login screen). Works on either dataset (seed or Meta Kaggle).

These tests WRITE to the database: every account they create has a username
starting with "zz_test_" and is deleted again (DETACH DELETE) after each test.

Run:  pytest tests/test_accounts.py -v
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

from backend import accounts, recommendations, users  # noqa: E402
from backend.db import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "app.py")
PREFIX = "zz_test_"
PASSWORD = "correct-horse-1"


def _delete_test_users():
    db.execute_query(f"MATCH (u:User) WHERE u.username STARTS WITH '{PREFIX}' DETACH DELETE u", write=True)


@pytest.fixture(autouse=True)
def clean_accounts():
    try:
        db.verify_connection()
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")
    _delete_test_users()
    yield
    _delete_test_users()


@pytest.fixture(scope="module")
def vocab():
    skills = [s["name"] for s in users.list_skills()]
    interests = [i["name"] for i in users.list_interests()]
    if not skills or not interests:
        pytest.skip("no skill/interest vocabulary loaded")
    return skills, interests


def register(name="jane", **kw):
    kw.setdefault("display_name", "Jane Doe")
    kw.setdefault("password", PASSWORD)
    return accounts.register_user(PREFIX + name, **kw)


# ---------- backend ----------

def test_register_creates_app_user_with_self_declared_tags(vocab):
    skills, interests = vocab
    user = register(skills=skills[:2], interests=interests[:1], country="Canada")
    assert user["userId"].startswith("u") and len(user["userId"]) == 33
    assert user["source"] == "app" and user["country"] == "Canada" and user["tier"] is None
    assert user["golds"] == 0 and user["registerDate"]
    got = users.get_user_skills(user["userId"])
    assert {s["skill"] for s in got} == set(skills[:2])
    assert all(s["weight"] == 0.5 and s["competitions"] == 0 and s["source"] == "self" for s in got)
    assert [i["interest"] for i in users.get_user_interests(user["userId"])] == interests[:1]
    assert users.get_user_teams(user["userId"]) == []


def test_password_is_hashed_and_never_returned():
    user = register()
    stored = db.execute_query("MATCH (u:User {userId: $id}) RETURN u.passwordHash AS h",
                              {"id": user["userId"]})[0]["h"]
    assert stored.startswith("scrypt$") and PASSWORD not in stored
    assert "passwordHash" not in users.get_user(user["userId"])
    assert "passwordHash" not in users.get_user_profile(user["userId"])
    # Same password twice gives different hashes (random salt).
    assert accounts.hash_password(PASSWORD) != accounts.hash_password(PASSWORD)


def test_login():
    user = register()
    assert accounts.authenticate(PREFIX + "jane", PASSWORD)["userId"] == user["userId"]
    assert accounts.authenticate(f"  {PREFIX.upper()}JANE ", PASSWORD) is not None  # case/space-insensitive
    assert accounts.authenticate(PREFIX + "jane", "wrong-password") is None
    assert accounts.authenticate(PREFIX + "nobody", PASSWORD) is None


def test_imported_users_cannot_log_in_with_a_password():
    some = db.execute_query("MATCH (u:User) WHERE u.passwordHash IS NULL RETURN u.username AS n LIMIT 1")
    if some:
        assert accounts.authenticate(some[0]["n"], "") is None


@pytest.mark.parametrize("kw, message", [
    ({"name": "x"}, "Username must be"),                       # too short
    ({"name": "Bad Name!"}, "Username must be"),
    ({"password": "short"}, "at least 8"),
    ({"display_name": "   "}, "Display name"),
    ({"skills": ["not-a-real-skill"]}, "not-a-real-skill"),
])
def test_register_rejects_bad_input(kw, message):
    name = kw.pop("name", "jane")
    with pytest.raises(ValueError, match=message):
        accounts.register_user(name if name in ("x", "Bad Name!") else PREFIX + name,
                               **{"display_name": "Jane", "password": PASSWORD, **kw})


def test_username_must_be_unique():
    register()
    with pytest.raises(ValueError, match="already taken"):
        register(display_name="Someone else")
    taken = db.execute_query("MATCH (u:User) WHERE u.source <> 'app' RETURN u.username AS n LIMIT 1")
    if taken:  # imported usernames are taken too
        with pytest.raises(ValueError, match="already taken"):
            accounts.register_user(taken[0]["n"], "X", PASSWORD)


def test_update_profile_replaces_self_declared_tags(vocab):
    skills, interests = vocab
    user = register(skills=skills[:2], interests=interests[:2])
    accounts.update_profile(user["userId"], "Jane D.", country="", skills=[skills[2]], interests=[])
    assert users.get_user(user["userId"])["displayName"] == "Jane D."
    assert users.get_user(user["userId"])["country"] is None
    assert [s["skill"] for s in users.get_user_skills(user["userId"])] == [skills[2]]
    assert users.get_user_interests(user["userId"]) == []


def test_only_app_accounts_are_editable():
    some = db.execute_query("MATCH (u:User) WHERE u.source <> 'app' RETURN u.userId AS id LIMIT 1")
    if some:
        with pytest.raises(ValueError, match="Only accounts created in the app"):
            accounts.update_profile(some[0]["id"], "Hacker")


def test_new_user_gets_recommendations(vocab):
    skills, _ = vocab
    empty = register("empty")
    recs = recommendations.recommend_users(empty["userId"], limit=3)
    assert recs and all(r["fallback"] for r in recs)  # popular users
    with_skills = register("skilled", skills=skills[:3])
    recs = recommendations.recommend_users(with_skills["userId"], limit=3)
    assert recs and not recs[0]["fallback"] and recs[0]["sharedSkills"]


# ---------- login screen ----------

def _app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_signup_form_creates_account_and_logs_in(vocab):
    skills, _ = vocab
    at = _app()
    at.button(key="switch_to_signup").click().run()
    at.text_input(key="signup_username").input(PREFIX + "form")
    at.text_input(key="signup_display").input("Form User")
    at.text_input(key="signup_password").input(PASSWORD)
    at.text_input(key="signup_confirm").input(PASSWORD)
    at.button(key="signup_submit").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    created = users.get_user_by_username(PREFIX + "form")
    assert created and at.session_state["me"] == created["userId"]
    assert at.title[0].value == "Hi, Form"


def test_signup_form_shows_errors():
    register()  # take the username
    at = _app()
    at.button(key="switch_to_signup").click().run()
    at.text_input(key="signup_username").input(PREFIX + "jane")
    at.text_input(key="signup_display").input("Jane")
    at.text_input(key="signup_password").input(PASSWORD)
    at.text_input(key="signup_confirm").input("different-pass")
    at.button(key="signup_submit").click().run()
    assert "don't match" in at.error[0].value
    at.text_input(key="signup_confirm").input(PASSWORD)
    at.button(key="signup_submit").click().run()
    assert "already taken" in at.error[0].value
    assert "me" not in at.session_state


def test_switching_between_login_and_signup():
    at = _app()
    assert at.button(key="login_submit")
    at.button(key="switch_to_signup").click().run()
    assert at.button(key="signup_submit")
    at.button(key="switch_to_login").click().run()
    assert at.button(key="login_submit")


def test_login_form():
    user = register()
    at = _app()
    at.text_input(key="login_username").input(PREFIX + "jane")
    at.text_input(key="login_password").input("wrong-password")
    at.button(key="login_submit").click().run()
    assert "username or password was incorrect" in at.error[0].value
    at.text_input(key="login_password").input(PASSWORD)
    at.button(key="login_submit").click().run()
    assert not at.exception
    assert at.session_state["me"] == user["userId"]


def test_own_profile_has_edit_button_only_for_app_accounts():
    user = register()
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = user["userId"]
    at.run()
    at.switch_page("app_pages/profile.py")
    at.run()
    assert not at.exception
    assert at.button(key="profile_edit")
