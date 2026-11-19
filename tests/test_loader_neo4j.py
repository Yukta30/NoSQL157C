"""Database tests. These WIPE the target database.

Set NEO4J_URI, NEO4J_PASSWORD and NEO4J_TEST_ALLOW_WIPE=1 to run them.
Use a throwaway database, never the shared project one.
"""
import os

import pytest

import load_neo4j as L

pytestmark = pytest.mark.skipif(
    not (os.environ.get("NEO4J_URI") and os.environ.get("NEO4J_PASSWORD")
         and os.environ.get("NEO4J_TEST_ALLOW_WIPE") == "1"),
    reason="needs NEO4J_URI, NEO4J_PASSWORD and NEO4J_TEST_ALLOW_WIPE=1",
)


@pytest.fixture(scope="module")
def driver():
    from neo4j import GraphDatabase

    d = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ.get("NEO4J_USERNAME", "neo4j"), os.environ["NEO4J_PASSWORD"]),
    )
    d.verify_connectivity()
    yield d
    d.close()


@pytest.fixture(scope="module")
def loaded(seed_dir, driver):
    assert L.main(["--data-dir", seed_dir, "--wipe"]) == 0


def run(driver, cypher):
    database = os.environ.get("NEO4J_DATABASE", "neo4j")
    with driver.session(database=database) as session:
        return [dict(r) for r in session.run(cypher)]


def test_load_succeeds(loaded):
    pass


def test_node_counts(driver, loaded):
    expected = {"User": 27, "Skill": 9, "Interest": 5, "Competition": 7, "Team": 16}
    for label, n in expected.items():
        assert run(driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"] == n, label


def test_relationship_counts(driver, loaded):
    expected = {
        "MEMBER_OF": 36, "PARTICIPATED_IN": 16, "USES_SKILL": 15, "ABOUT": 8,
        "HAS_SKILL": 74, "INTERESTED_IN": 42, "FOLLOWS": 18, "WORKED_WITH": 22,
    }
    for rel, n in expected.items():
        assert run(driver, f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")[0]["c"] == n, rel


def test_worked_with_times(driver, loaded):
    rows = run(driver, """
        MATCH (a:User {username: 'alicechen'})-[w:WORKED_WITH]-(b:User {username: 'bobsmith'})
        RETURN w.times AS times""")
    assert rows == [{"times": 2}]


def test_grace_has_no_interest(driver, loaded):
    rows = run(driver, "MATCH (:User {username: 'gracekim'})-[:INTERESTED_IN]->() RETURN count(*) AS c")
    assert rows[0]["c"] == 0


def test_walter_comp_tier_is_null(driver, loaded):
    rows = run(driver, "MATCH (u:User {username: 'walterkaggle'}) RETURN u.compTier AS t")
    assert rows == [{"t": None}]


def test_app_user_has_no_relationships(driver, loaded):
    rows = run(driver, "MATCH (u:User {username: 'lee_app'})-[r]-() RETURN count(r) AS c")
    assert rows[0]["c"] == 0


def test_follow_has_since_date(driver, loaded):
    rows = run(driver, """
        MATCH (:User {username: 'newbie_sam'})-[f:FOLLOWS]->(:User {username: 'alicechen'})
        RETURN toString(f.since) AS since""")
    assert rows == [{"since": "2026-11-02"}]


def test_second_load_without_wipe_is_refused(seed_dir, driver, loaded):
    assert L.main(["--data-dir", seed_dir]) == 1


def test_wipe_and_reload(seed_dir, driver, loaded):
    assert L.main(["--data-dir", seed_dir, "--wipe"]) == 0
    assert run(driver, "MATCH (n) RETURN count(n) AS c")[0]["c"] == 64
