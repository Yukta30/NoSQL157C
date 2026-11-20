"""Offline tests for scripts/preprocess_data.py on a tiny hand-made Meta Kaggle
sample (no download, no Neo4j). Each case maps to a rule in
docs/csv_contract.md sections 2-4.

Run:  pytest tests/test_preprocess.py -v
"""
import csv
import math

import pytest

pytest.importorskip("duckdb")

import preprocess_data  # noqa: E402  (tests/conftest.py puts scripts/ on sys.path)
from load_neo4j import GraphData  # noqa: E402

# Raw files exactly as Kaggle ships them: every value quoted, US dates.
RAW = {
    "Tags.csv": [
        ["Id", "Name", "FullPath"],
        ["10", "nlp", "analysis > nlp"],
        ["11", "tabular", "data type > tabular"],
        ["12", "tensorflow", "packages > tensorflow"],
        ["20", "health", "subject > health and fitness"],
        ["30", "english", "language > english"],
    ],
    "Competitions.csv": [
        ["Id", "Slug", "Title", "HostSegmentTitle", "EnabledDate", "DeadlineDate", "MaxTeamSize",
         "TotalTeams", "Overview"],
        ["100", "nlp-comp", "NLP, the comp", "Featured", "01/01/2021 00:00:00", "06/30/2021 23:59:00",
         "5", "40", "multi\nline overview"],
        ["200", "tab-comp", "Tabular", "Playground", "01/01/2022 00:00:00", "03/01/2022 23:59:00",
         "3", "10", ""],
        ["300", "community", "Community comp", "Community", "01/01/2022 00:00:00", "03/01/2022 23:59:00",
         "3", "10", ""],
        ["400", "untagged", "No tags", "Featured", "01/01/2022 00:00:00", "03/01/2022 23:59:00",
         "3", "10", ""],
    ],
    "CompetitionTags.csv": [
        ["Id", "CompetitionId", "TagId"],
        ["1", "100", "10"], ["2", "100", "20"], ["3", "100", "30"],
        ["4", "200", "11"], ["5", "200", "12"],
        ["6", "300", "10"],
    ],
    "Teams.csv": [
        ["Id", "CompetitionId", "TeamName", "IsBenchmark", "Medal", "PrivateLeaderboardRank"],
        ["1001", "100", "Gold \"Team\", A", "False", "1", "1"],    # graph team: alice, bob
        ["1002", "100", "Solo gold", "False", "1", "2"],           # 1 member -> not a graph team
        ["1003", "100", "Benchmark", "True", "", "3"],              # benchmark -> ignored
        ["1004", "100", "Top quarter", "False", "", "10"],          # history: alice, rankPct 0.25
        ["1005", "100", "Unranked", "False", "", ""],                # not ranked -> ignored
        ["1006", "100", "Last", "False", "0", "40"],                 # sets fieldSize 40
        ["2001", "200", "Silver squad", "False", "2", "1"],         # graph team: bob, carol, deleted
        ["2002", "200", "Bot team", "False", "3", "2"],              # bob + Kaggle bot -> 1 member
        ["3001", "300", "Community gold", "False", "1", "1"],       # dropped segment
    ],
    "TeamMemberships.csv": [
        ["Id", "TeamId", "UserId"],
        ["1", "1001", "11"], ["2", "1001", "12"],
        ["3", "1002", "13"],
        ["4", "1003", "11"], ["5", "1003", "14"],
        ["6", "1004", "11"],
        ["7", "1006", "14"],
        ["8", "2001", "12"], ["9", "2001", "13"], ["10", "2001", "99"],  # 99 doesn't exist
        ["11", "2002", "12"], ["12", "2002", "1"],
        ["13", "3001", "14"], ["14", "3001", "15"],
    ],
    "Users.csv": [
        ["Id", "UserName", "DisplayName", "RegisterDate", "PerformanceTier", "Country"],
        ["1", "kaggle", "Kaggle Team", "01/01/2010", "5", ""],
        ["11", "alice", "Alice, PhD", "03/14/2017", "2", "Canada"],
        ["12", "bob", "Bob 🚀", "08/02/2016", "4", ""],
        ["13", "carol", "Carol", "01/05/2020", "1", ""],
        ["14", "dave", "Dave", "01/05/2020", "1", ""],
        ["15", "erin", "Erin", "01/05/2020", "1", ""],
    ],
    "UserAchievements.csv": [
        ["Id", "UserId", "AchievementType", "Tier", "TotalGold", "TotalSilver", "TotalBronze"],
        ["1", "11", "Competitions", "2", "1", "0", "0"],
        ["2", "11", "Scripts", "4", "9", "9", "9"],
        ["3", "12", "Competitions", "3", "1", "1", "1"],
    ],
    "UserFollowers.csv": [
        ["Id", "UserId", "FollowingUserId", "CreationDate"],
        ["1", "11", "12", "02/01/2021"],
        ["2", "12", "11", "02/03/2021"],
        ["3", "11", "14", "02/03/2021"],   # dave isn't kept -> dropped
    ],
}


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    for name, rows in RAW.items():
        with open(raw / name, "w", newline="", encoding="utf-8") as f:
            csv.writer(f, quoting=csv.QUOTE_ALL).writerows(rows)
    out_dir = tmp_path_factory.mktemp("processed")
    preprocess_data.main(["--raw-dir", str(raw), "--out-dir", str(out_dir)])
    return out_dir


def test_subset_keeps_medal_teams_with_two_existing_members(out):
    teams = {t["teamId"]: t for t in read(out / "teams.csv")}
    assert set(teams) == {"1001", "2001"}
    assert teams["1001"]["teamName"] == 'Gold "Team", A'
    assert teams["1001"]["medal"] == "gold" and teams["1001"]["rankPct"] == "0.025"
    assert teams["2001"]["teamSize"] == "2"  # deleted user 99 doesn't count


def test_users_are_members_of_graph_teams(out):
    users = {u["userId"]: u for u in read(out / "users.csv")}
    assert set(users) == {"k11", "k12", "k13"}
    alice, bob, carol = users["k11"], users["k12"], users["k13"]
    assert alice["displayName"] == "Alice, PhD" and alice["registerDate"] == "2017-03-14"
    assert alice["tier"] == "expert" and alice["compTier"] == "expert" and alice["golds"] == "1"
    assert bob["displayName"] == "Bob 🚀" and bob["tier"] == "grandmaster" and bob["compTier"] == "master"
    assert carol["compTier"] == "" and carol["golds"] == "0" and carol["country"] == ""


def test_competitions_and_tags(out):
    comps = {c["competitionId"]: c for c in read(out / "competitions.csv")}
    assert set(comps) == {"100", "200"}
    assert comps["100"]["year"] == "2021" and comps["100"]["title"] == "NLP, the comp"
    assert {s["name"] for s in read(out / "skills.csv")} == {"nlp", "tabular", "tensorflow"}
    assert {i["name"]: i["category"] for i in read(out / "interests.csv")} == {"health": "subject"}


def test_skill_weights_use_full_history(out):
    skills = {(r["userId"], r["skill"]): r for r in read(out / "user_skill.csv")}
    # Alice: gold (3) + top-quarter non-medal (0.75) in nlp.
    alice = skills[("k11", "nlp")]
    assert alice["competitions"] == "2" and alice["medals"] == "1"
    assert float(alice["weight"]) == round(1 - math.exp(-3.75 / 3), 4)
    # Bob: graph team silver (2) + bot team bronze (1), both history teams in comp 200.
    bob = skills[("k12", "tabular")]
    assert bob["competitions"] == "2" and float(bob["weight"]) == round(1 - math.exp(-3 / 3), 4)
    assert ("k13", "nlp") not in skills  # carol's nlp team was solo: no pair


def test_interest_weights(out):
    rows = {(r["userId"], r["interest"]): r for r in read(out / "user_interest.csv")}
    assert float(rows[("k11", "health")]["weight"]) == round(1 - math.exp(-2 / 2), 4)
    assert set(rows) == {("k11", "health"), ("k12", "health")}


def test_follows_only_between_kept_users(out):
    follows = read(out / "follows.csv")
    assert {(f["followerId"], f["followeeId"]) for f in follows} == {("k11", "k12"), ("k12", "k11")}
    assert follows[0]["since"] == "2021-02-01"


def test_output_passes_the_loader_checks(out):
    data = GraphData.from_dir(str(out))
    assert data.problems() == []
