"""The assignment's graph use cases: UC-5, 8, 9, 10, 12, 13 (backend and pages).
Works on either dataset (seed or Meta Kaggle).

Builds its own small follow graph out of "zz_test_" users so the expected
answers are exact, and deletes those users again after each test:

    ann -> bob -> cat -> dan        ann -> eve -> cat
    ann -> fay                      bob -> fay

Run:  pytest tests/test_use_cases.py -v
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from streamlit.testing.v1 import AppTest  # noqa: E402

from backend import accounts, social, users  # noqa: E402
from backend.db import db  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "frontend", "app.py")
PREFIX = "zz_test_"
NAMES = ["ann", "bob", "cat", "dan", "eve", "fay"]
EDGES = [("ann", "bob"), ("bob", "cat"), ("cat", "dan"), ("ann", "eve"), ("eve", "cat"),
         ("ann", "fay"), ("bob", "fay")]


def _clean():
    db.execute_query(f"MATCH (u:User) WHERE u.username STARTS WITH '{PREFIX}' DETACH DELETE u", write=True)


@pytest.fixture
def g():
    try:
        db.verify_connection()
    except Exception as e:
        pytest.skip(f"Neo4j not available: {e}")
    _clean()
    ids = {n: accounts.register_user(PREFIX + n, n.title(), f"{n}@example.com", "password-123")["userId"]
           for n in NAMES}
    for a, b in EDGES:
        social.follow_user(ids[a], ids[b])
    yield ids
    _clean()


def names(rows):
    return sorted(r["user"]["username"].removeprefix(PREFIX) for r in rows)


# ---------- UC-5 / UC-6 / UC-7 ----------

def test_uc5_follow_errors_and_no_duplicate(g):
    with pytest.raises(ValueError, match="can't follow yourself"):
        social.follow_user(g["ann"], g["ann"])
    with pytest.raises(ValueError, match="already follow Bob"):
        social.follow_user(g["ann"], g["bob"])
    count = db.execute_query("MATCH (:User {userId: $a})-[f:FOLLOWS]->(:User {userId: $b}) RETURN count(f) AS n",
                             {"a": g["ann"], "b": g["bob"]})[0]["n"]
    assert count == 1
    assert social.follow_user(g["dan"], g["ann"]) is True


def test_uc6_uc7_unfollow_and_separate_lists(g):
    assert names(social.get_following(g["ann"])) == ["bob", "eve", "fay"]
    assert names(social.get_followers(g["cat"])) == ["bob", "eve"]
    assert social.unfollow_user(g["ann"], g["bob"]) is True
    assert names(social.get_following(g["ann"])) == ["eve", "fay"]
    assert social.unfollow_user(g["ann"], g["bob"]) is False


# ---------- UC-8 ----------

def test_uc8_mutual_connections(g):
    assert names(social.get_mutual_following(g["ann"], g["bob"])) == ["fay"]
    assert names(social.get_mutual_following(g["bob"], g["eve"])) == ["cat"]
    assert social.get_mutual_following(g["dan"], g["ann"]) == []


# ---------- UC-9 ----------

def test_uc9_exactly_two_hops_each_person_once(g):
    rows = social.get_two_hop_recommendations(g["ann"])
    # ann -> bob -> cat, ann -> eve -> cat (cat once, via 2); ann -> bob -> fay is already followed.
    assert names(rows) == ["cat"]
    assert rows[0]["viaCount"] == 2 and sorted(rows[0]["viaNames"]) == ["Bob", "Eve"]
    # dan is three hops away (ann -> bob -> cat -> dan): not included.
    assert names(social.get_two_hop_recommendations(g["bob"])) == ["dan"]
    assert social.get_two_hop_recommendations(g["dan"]) == []


# ---------- UC-10 / UC-12 ----------

def test_uc10_all_users_pages_include_everyone(g):
    total = users.count_users()
    assert total >= len(NAMES)
    page = users.user_page_of(PREFIX + "ann", 25)
    rows = users.list_all_users(page * 25, 25)
    assert PREFIX + "ann" in [r["username"] for r in rows]
    assert {"username", "displayName", "followers"} <= rows[0].keys()


def test_uc12_popular_sorted_by_followers(g):
    rows = social.get_popular_users(limit=10)
    counts = [r["followers"] for r in rows]
    assert counts == sorted(counts, reverse=True) and len(rows) == 10


# ---------- UC-13 ----------

def test_uc13_degrees_of_separation(g):
    r = social.degrees_of_separation(PREFIX + "ann", PREFIX + "dan")
    assert r["found"] and r["degrees"] == 3
    assert [u["username"].removeprefix(PREFIX) for u in r["path"]][0] == "ann"
    assert [u["username"].removeprefix(PREFIX) for u in r["path"]][-1] == "dan"
    # Direction matters: nobody follows back.
    assert social.degrees_of_separation(PREFIX + "dan", PREFIX + "ann")["found"] is False
    assert social.degrees_of_separation(PREFIX + "ann", PREFIX + "ann")["degrees"] == 0
    with pytest.raises(ValueError, match="No user with username"):
        social.degrees_of_separation(PREFIX + "ann", PREFIX + "nobody")


def test_uc13_max_four_hops(g):
    chain = [g["dan"]] + [accounts.register_user(f"{PREFIX}x{i}", f"X{i}", f"x{i}@example.com",
                                                 "password-123")["userId"] for i in range(2)]
    for a, b in zip(chain, chain[1:]):
        social.follow_user(a, b)
    # ann -> bob -> cat -> dan -> x0 -> x1 is 5 hops: beyond the limit.
    assert social.degrees_of_separation(PREFIX + "ann", PREFIX + "x0")["degrees"] == 4
    assert social.degrees_of_separation(PREFIX + "ann", PREFIX + "x1")["found"] is False


# ---------- pages ----------

def _page(me, page):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["me"] = me
    at.run()
    at.switch_page(f"app_pages/{page}.py")
    return at.run()


def _clean_run(at):
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("view", ["all", "popular", "may_know"])
def test_people_page_views(g, view):
    at = _page(g["ann"], "people")
    at.segmented_control(key="people_view").set_value(view).run()
    _clean_run(at)
    assert not at.error
    if view == "may_know":
        assert any(b.key == f"mayknow_{g['cat']}" for b in at.button)


def test_follow_by_username_shows_errors(g):
    at = _page(g["ann"], "people")
    at.text_input(key="follow_username").input(PREFIX + "ann")
    at.button(key="follow_submit").click().run()
    assert "can't follow yourself" in at.error[0].value
    at.text_input(key="follow_username").input(PREFIX + "bob")
    at.button(key="follow_submit").click().run()
    assert "already follow" in at.error[0].value
    at.text_input(key="follow_username").input(PREFIX + "dan")
    at.button(key="follow_submit").click().run()
    _clean_run(at)
    assert social.is_following(g["ann"], g["dan"])


def test_all_users_find_me(g):
    at = _page(g["ann"], "people")
    at.button(key="people_find_me").click().run()
    _clean_run(at)
    assert any(b.key == f"all_{g['ann']}" for b in at.button)  # your own row is listed


def test_connections_page_degrees_and_mutual(g):
    at = _page(g["ann"], "connections")
    at.text_input(key="degrees_to").input(PREFIX + "dan")
    at.button(key="degrees_submit").click().run()
    _clean_run(at)
    assert at.metric[0].value == "3"

    at.segmented_control(key="connections_view").set_value("mutual").run()
    at.text_input(key="mutual_to").input(PREFIX + "bob")
    at.button(key="mutual_submit").click().run()
    _clean_run(at)
    assert any(b.key == f"mutual_follow_{g['fay']}" for b in at.button)
