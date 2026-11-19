"""Backend integration tests against the deterministic seed dataset.

These tests do NOT wipe anything. They need:
  * Neo4j credentials in .env (or the shell): NEO4J_URI, NEO4J_USERNAME,
    NEO4J_PASSWORD, NEO4J_DATABASE
  * the database loaded with exactly the seed data:
        python scripts/load_neo4j.py --data-dir data/seed --wipe

If the database doesn't look like the seed (e.g. it holds real Meta Kaggle
data), every test is skipped. The follow/unfollow test writes one FOLLOWS
relationship and always removes it again.

Run:  pytest tests/test_backend.py -v
"""
import collections
import csv
import math
import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_ENV = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
if not all(os.environ.get(k) for k in _ENV):
    pytest.skip("needs " + ", ".join(_ENV) + " (in .env or the shell)", allow_module_level=True)

from backend import recommendations, social, team_builder, users  # noqa: E402
from backend.db import db  # noqa: E402

ALICE, BOB, CAROL, ERIN = "k1001", "k1002", "k1003", "k1005"
HEIDI, PEGGY, WENDY = "k1008", "k1014", "k1025"
SAM = "u5eed0000000000000000000000000001"
LEE = "u5eed0000000000000000000000000002"


@pytest.fixture(scope="module", autouse=True)
def seed_database():
    """Skip unless the database contains exactly the seed graph."""
    counts = db.execute_query(
        """
        RETURN COUNT { (n) } AS nodes, COUNT { ()-[]->() } AS rels,
               COUNT { (:User {userId: $alice, username: 'alicechen'}) } AS alice,
               COUNT { (:User {userId: $lee, username: 'lee_app'}) } AS lee
        """,
        {"alice": ALICE, "lee": LEE},
    )[0]
    if counts != {"nodes": 64, "rels": 231, "alice": 1, "lee": 1}:
        pytest.skip(
            f"database is not the seed graph ({counts}); reload with "
            "`python scripts/load_neo4j.py --data-dir data/seed --wipe`"
        )
    yield
    # Leave the graph exactly as the loader tests expect it.
    assert db.execute_query("MATCH ()-[f:FOLLOWS]->() RETURN count(f) AS n")[0]["n"] == 18


# ------------------------------------------------------------------ users.py

@pytest.mark.parametrize("term, expected", [
    ("alice", ["alicechen"]),
    ("chen", ["alicechen"]),          # matches display name "Alice Chen"
    ("ALICE", ["alicechen"]),
    ("carol phd", ["carolwu"]),       # every word must match
    ("sam", ["newbie_sam"]),
    ("zzz", []),
    ("", []),
    ("   ", []),
    ("a(b", []),                      # Lucene special chars are escaped
    ('"', []),
])
def test_search_users(term, expected):
    assert [u["username"] for u in users.search_users(term)] == expected


def test_search_users_limit():
    assert len(users.search_users("a", limit=2)) <= 2


def test_profile_alice():
    p = users.get_user_profile(ALICE)
    assert p["username"] == "alicechen"
    assert p["displayName"] == "Alice Chen"
    assert p["source"] == "kaggle"
    assert p["registerDate"] == "2017-03-14"          # ISO string, not neo4j Date
    assert (p["golds"], p["silvers"], p["bronzes"]) == (1, 1, 0)
    assert (p["followers"], p["following"], p["collaborators"]) == (4, 2, 2)


def test_skills_sorted_strongest_first():
    skills = users.get_user_skills(ALICE)
    assert [s["skill"] for s in skills] == ["nlp", "text", "time series analysis"]
    assert skills[0] == {"skill": "nlp", "category": "analysis", "weight": 0.8647,
                         "competitions": 4, "medals": 2, "source": "kaggle"}


def test_interests_sorted_strongest_first():
    assert [i["interest"] for i in users.get_user_interests(ALICE)] == ["health", "finance", "medicine"]


def test_teams_newest_first_with_teammates():
    teams = users.get_user_teams(ALICE)
    assert [t["teamId"] for t in teams] == [90002, 90001]
    assert teams[0]["competition"] == "Seed Market Sentiment" and teams[0]["year"] == 2024
    assert [m["username"] for m in teams[0]["teammates"]] == ["bobsmith"]
    assert [m["username"] for m in teams[1]["teammates"]] == ["bobsmith", "carolwu"]
    assert teams[1]["teamName"] == "Notes, Notes & More"


def test_app_user_with_self_declared_skills():
    p = users.get_user_profile(SAM)
    assert p["source"] == "app" and p["tier"] is None and p["country"] is None
    assert {(s["skill"], s["weight"], s["source"]) for s in p["skills"]} == {
        ("nlp", 0.5, "self"), ("text", 0.5, "self")}
    assert p["teams"] == []


def test_app_user_with_nothing():
    p = users.get_user_profile(LEE)
    assert p["skills"] == p["interests"] == p["teams"] == []
    assert (p["followers"], p["following"], p["collaborators"]) == (0, 0, 0)


def test_unknown_user():
    assert users.get_user_profile("nope") is None
    assert users.get_user("nope") is None
    assert users.user_exists("nope") is False
    assert users.user_exists(ALICE) is True
    assert users.get_user_by_username("bobsmith")["userId"] == BOB


def test_vocabulary():
    assert len(users.list_skills()) == 9
    assert len(users.list_interests()) == 5


# ----------------------------------------------------------------- social.py

def _names(rows):
    return [r["user"]["username"] for r in rows]


def test_following_and_followers():
    following = social.get_following(ALICE)
    assert [(r["user"]["username"], r["since"]) for r in following] == [
        ("erinokafor", "2022-09-09"), ("bobsmith", "2021-02-01")]
    assert _names(social.get_followers(ALICE)) == ["newbie_sam", "wendyclark", "carolwu", "bobsmith"]


def test_collaborators_and_mutuals():
    assert [(r["user"]["username"], r["times"]) for r in social.get_collaborators(ALICE)] == [
        ("bobsmith", 2), ("carolwu", 1)]
    assert _names(social.get_mutual_follows(ALICE)) == ["bobsmith"]


def test_is_following_is_directional():
    assert social.is_following(SAM, ALICE) is True
    assert social.is_following(ALICE, SAM) is False


def test_connection_status():
    s = social.get_connection_status(ALICE, BOB)
    assert s["mutual"] and s["workedTogether"] and s["workedTogetherTimes"] == 2
    s = social.get_connection_status(ALICE, LEE)
    assert not (s["following"] or s["followedBy"] or s["workedTogether"])
    assert social.get_connection_status(ALICE, "nope") is None


def test_ego_network():
    net = social.get_ego_network(ALICE)
    assert {n["userId"] for n in net["nodes"]} == {ALICE, BOB, CAROL, ERIN, WENDY, SAM}
    assert len(net["edges"]) == 11
    assert {"source": ALICE, "target": BOB, "type": "WORKED_WITH", "times": 2} in net["edges"]
    assert social.get_ego_network(LEE) == {
        "nodes": [{"userId": LEE, "username": "lee_app", "displayName": "Lee"}], "edges": []}
    assert social.get_ego_network("nope") == {"nodes": [], "edges": []}


def test_follow_unfollow_roundtrip():
    assert not social.is_following(LEE, ALICE)
    try:
        assert social.follow_user(LEE, ALICE) is True
        assert social.follow_user(LEE, ALICE) is False          # idempotent
        assert social.is_following(LEE, ALICE)
        rows = social.get_following(LEE)
        assert _names(rows) == ["alicechen"] and len(rows[0]["since"]) == 10
    finally:
        social.unfollow_user(LEE, ALICE)
    assert not social.is_following(LEE, ALICE)
    assert social.unfollow_user(LEE, ALICE) is False


def test_follow_existing_keeps_since():
    assert social.follow_user(SAM, ALICE) is False
    assert social.get_following(SAM)[0]["since"] == "2026-11-02"


@pytest.mark.parametrize("a, b", [(ALICE, ALICE), (ALICE, "nope"), ("nope", ALICE)])
def test_follow_invalid(a, b):
    with pytest.raises(ValueError):
        social.follow_user(a, b)


# -------------------------------------------------------- recommendations.py

def _expected_recommendations(seed_dir):
    """Recompute every user's recommendation scores straight from the seed
    CSVs, independently of Cypher, using the formula documented in
    backend/recommendations.py."""
    def rd(name):
        with open(os.path.join(seed_dir, f"{name}.csv"), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    all_users = {u["userId"]: u["username"] for u in rd("users")}
    n = len(all_users)

    def tags(name, col):
        m = collections.defaultdict(dict)
        for r in rd(name):
            m[r["userId"]][r[col]] = float(r["weight"])
        return m

    def overlap(m, a, b):
        total = 0.0
        for t in m[a].keys() & m[b].keys():
            holders = sum(t in v for v in m.values())
            rarity = math.log(1 + n / holders) / math.log(1 + n)
            total += min(m[a][t], m[b][t]) * rarity
        return total

    skills, interests = tags("user_skill", "skill"), tags("user_interest", "interest")
    teams = collections.defaultdict(set)
    for r in rd("member_of"):
        teams[r["teamId"]].add(r["userId"])
    worked = {(a, b) for mem in teams.values() for a in mem for b in mem if a != b}
    adjacent = collections.defaultdict(set)
    follows = set()
    for r in rd("follows"):
        a, b = r["followerId"], r["followeeId"]
        follows.add((a, b))
        adjacent[a].add(b)
        adjacent[b].add(a)
    for a, b in worked:
        adjacent[a].add(b)

    w = recommendations.WEIGHTS
    expected = {}
    for me in all_users:
        scores = {}
        for c in all_users:
            if c == me or (me, c) in follows:
                continue
            score = (w["skills"] * overlap(skills, me, c)
                     + w["interests"] * overlap(interests, me, c)
                     + w["mutual"] * len((adjacent[me] & adjacent[c]) - {me, c})
                     + (w["worked_with"] if (me, c) in worked else 0))
            if score > 0:
                scores[all_users[c]] = score
        expected[me] = scores
    return expected


def test_recommendations_match_independent_computation(seed_dir):
    expected = _expected_recommendations(seed_dir)
    for me, scores in expected.items():
        got = recommendations.recommend_users(me, limit=100, fallback=False)
        assert {r["username"] for r in got} == set(scores), me
        for r in got:
            assert r["score"] == pytest.approx(scores[r["username"]], abs=0.01), (me, r["username"])
        assert [r["score"] for r in got] == sorted((r["score"] for r in got), reverse=True), me


def test_recommendations_exclude_self_and_followed():
    followed = {r["user"]["userId"] for r in social.get_following(ALICE)}
    recs = {r["userId"] for r in recommendations.recommend_users(ALICE, limit=100)}
    assert ALICE not in recs and not (followed & recs)


def test_recommendation_is_explained():
    top = recommendations.recommend_users(ALICE, limit=1)[0]
    assert top["username"] == "carolwu" and top["fallback"] is False
    assert top["reasons"] == [
        "Worked together on 1 team",
        "2 shared skills: nlp, text",   # equal strength: alphabetical
        "2 shared interests: medicine, health",
        "1 mutual connection: Bob Smith",
    ]
    assert top["score"] == pytest.approx(sum(top["breakdown"].values()), abs=0.002)


def test_cold_start_fallback():
    recs = recommendations.recommend_users(LEE, limit=3)
    assert [r["username"] for r in recs] == ["peggyhopper", "alicechen", "bobsmith"]
    assert all(r["fallback"] for r in recs)
    assert recs[0]["reasons"] == ["Popular in the community: 5 followers"]
    assert recommendations.recommend_users(LEE, fallback=False) == []


def test_explain_recommendation():
    e = recommendations.explain_recommendation(ALICE, BOB)    # already followed: still explainable
    assert e["workedTogetherTimes"] == 2 and "Worked together on 2 teams" in e["reasons"]
    # "Carol Wu, PhD" contains a comma, so people are separated with " · ".
    assert "2 mutual connections: Carol Wu, PhD · Erin Okafor" in e["reasons"]
    assert recommendations.explain_recommendation(ALICE, ALICE) is None
    assert recommendations.explain_recommendation(ALICE, "nope") is None
    assert recommendations.recommend_users("nope") == []


def test_verify_connection_retries_transient_errors(monkeypatch):
    from neo4j.exceptions import AuthError, ServiceUnavailable

    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ServiceUnavailable("Unable to retrieve routing information")

    monkeypatch.setattr(db.driver, "verify_connectivity", flaky)
    assert db.verify_connection(delay=0) is True and len(calls) == 3

    calls.clear()
    monkeypatch.setattr(db.driver, "verify_connectivity",
                        lambda: (calls.append(1), (_ for _ in ()).throw(AuthError("bad password"))))
    with pytest.raises(AuthError):
        db.verify_connection(delay=0)
    assert len(calls) == 1                     # wrong credentials are not retried


# ----------------------------------------------------------- team_builder.py

def _ids(result):
    return [m["userId"] for m in result["members"]]


def _check_invariants(result, min_gain=team_builder.MIN_GAIN):
    """Coverage = best weight among members; nobody added without real gain."""
    for c in result["coverage"]:
        weights = [s["weight"] for m in result["members"] for s in m["skills"] if s["skill"] == c["skill"]]
        assert c["weight"] == pytest.approx(max(weights, default=0.0))
    for m in result["members"]:
        if not m["isYou"]:
            assert m["coverageGain"] > 0 and m["coverageGain"] >= min_gain - 1e-9


def test_team_is_complementary_not_top_n():
    skills = ["nlp", "computer vision", "tensorflow"]
    team = team_builder.build_team(skills, team_size=3)
    assert _ids(team) == [PEGGY, HEIDI]       # Heidi fills Peggy's CV gap; a third adds nothing
    assert team["missingSkills"] == [] and team["coverageScore"] == 0.826
    assert "more people wouldn't add coverage" in team["note"]
    top3 = [r["userId"] for r in team_builder.rank_candidates(skills, limit=3)]
    assert top3 == [PEGGY, HEIDI, ERIN]       # individually ranked would include redundant Erin
    _check_invariants(team)


def test_team_with_owner_and_chemistry():
    team = team_builder.build_team(["nlp", "computer vision", "tensorflow"], 3, current_user_id=ALICE)
    assert _ids(team) == [ALICE, ERIN, PEGGY]
    assert team["members"][0]["isYou"]
    assert "Connected to Alice Chen" in team["members"][1]["reasons"]
    assert {"a": ALICE, "b": ERIN, "type": "FOLLOWS", "times": None} in team["links"]
    _check_invariants(team)


def test_min_gain_threshold():
    skills = ["nlp", "computer vision", "tensorflow"]
    loose = team_builder.build_team(skills, 3, current_user_id=ALICE, min_gain=0)
    assert _ids(loose)[2] == HEIDI            # tiny CV gain + chemistry wins without threshold
    _check_invariants(loose, min_gain=0)


def test_team_excluding_users():
    team = team_builder.build_team(["nlp", "computer vision", "tensorflow", "regression"], 5,
                                   exclude_user_ids=[PEGGY])
    assert PEGGY not in _ids(team) and len(team["members"]) == 3
    assert team["missingSkills"] == []
    _check_invariants(team)


@pytest.mark.parametrize("owner", [SAM, LEE])
def test_team_for_app_users(owner):
    team = team_builder.build_team(["tabular", "regression"], 3, current_user_id=owner)
    assert _ids(team)[0] == owner and team["members"][0]["coverageGain"] == 0
    assert team["missingSkills"] == []
    _check_invariants(team)


def test_team_owner_excluded_when_not_included():
    team = team_builder.build_team(["nlp"], 2, current_user_id=PEGGY, include_me=False)
    assert PEGGY not in _ids(team)


def test_skill_normalization_and_unknown_skills():
    team = team_builder.build_team([" NLP", "nlp", "Quantum Basket Weaving"], 2)
    assert team["requiredSkills"] == ["nlp", "quantum basket weaving"]
    assert team["unknownSkills"] == ["quantum basket weaving"]
    assert [c["skill"] for c in team["coverage"]] == ["nlp"]

    none_known = team_builder.build_team(["quantum"], 2)
    assert none_known["members"] == [] and "None of the requested skills" in none_known["note"]


@pytest.mark.parametrize("skills", [
    ["tabular", "image", "text"],
    ["binary classification", "regression", "time series analysis"],
    ["nlp", "tensorflow"],
    ["tabular", "image", "text", "nlp", "computer vision", "time series analysis",
     "regression", "binary classification", "tensorflow"],   # all 9 seed skills
])
def test_team_invariants_for_various_skill_sets(skills):
    for size in (1, 2, 4):
        team = team_builder.build_team(skills, size)
        assert len(team["members"]) <= size
        _check_invariants(team)


@pytest.mark.parametrize("kwargs", [
    {"required_skills": [], "team_size": 3},
    {"required_skills": ["nlp"], "team_size": 0},
    {"required_skills": ["nlp"], "current_user_id": "nope"},
])
def test_team_invalid_input(kwargs):
    with pytest.raises(ValueError):
        team_builder.build_team(**kwargs)
