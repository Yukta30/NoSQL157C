"""Offline tests for the seed CSVs. No database needed."""
import copy
import shutil

import pytest

import load_neo4j as L


@pytest.fixture(scope="module")
def seed(seed_dir):
    return L.GraphData.from_dir(seed_dir)


def test_seed_passes_checks(seed):
    assert seed.problems() == []


def test_seed_node_counts(seed):
    assert seed.expected_counts()["nodes"] == {
        "User": 27, "Skill": 9, "Interest": 5, "Competition": 7, "Team": 16,
    }


def test_seed_relationship_counts(seed):
    assert seed.expected_counts()["rels"] == {
        "MEMBER_OF": 36, "PARTICIPATED_IN": 16, "USES_SKILL": 15, "ABOUT": 8,
        "HAS_SKILL": 74, "INTERESTED_IN": 42, "FOLLOWS": 18, "WORKED_WITH": 22,
    }


def test_seed_totals(seed):
    counts = seed.expected_counts()
    assert sum(counts["nodes"].values()) == 64
    assert sum(counts["rels"].values()) == 231


def test_worked_with_pairs(seed):
    pairs = seed.worked_with_pairs()
    assert len(pairs) == 22
    doubles = {pair for pair, times in pairs.items() if times == 2}
    assert doubles == {("k1001", "k1002"), ("k1004", "k1006")}
    assert set(pairs.values()) == {1, 2}


def test_grace_has_no_interest(seed):
    assert not [r for r in seed.tables["user_interest"] if r["userId"] == "k1007"]


def test_mallory_has_no_skill(seed):
    assert not [r for r in seed.tables["user_skill"] if r["userId"] == "k1011"]


def test_walter_has_no_comp_tier(seed):
    walter = next(r for r in seed.tables["users"] if r["userId"] == "k1018")
    assert walter["compTier"] is None
    assert (walter["golds"], walter["silvers"], walter["bronzes"]) == (0, 0, 0)


def test_app_users_have_no_teams(seed):
    app_ids = {r["userId"] for r in seed.tables["users"] if r["source"] == "app"}
    assert app_ids == {"u5eed0000000000000000000000000001", "u5eed0000000000000000000000000002"}
    assert not [r for r in seed.tables["member_of"] if r["userId"] in app_ids]


def _mutated(seed):
    return L.GraphData(copy.deepcopy(seed.tables))


def test_catches_team_size_mismatch(seed):
    bad = _mutated(seed)
    bad.tables["teams"][0]["teamSize"] += 1
    assert any("teamSize" in e for e in bad.problems())


def test_catches_unknown_follow_target(seed):
    bad = _mutated(seed)
    bad.tables["follows"][0]["followeeId"] = "k9999"
    assert any("unknown user" in e for e in bad.problems())


def test_catches_self_follow(seed):
    bad = _mutated(seed)
    bad.tables["follows"][0]["followeeId"] = bad.tables["follows"][0]["followerId"]
    assert any("self-follow" in e for e in bad.problems())


def test_catches_bad_medal(seed):
    bad = _mutated(seed)
    bad.tables["teams"][0]["medal"] = "platinum"
    assert any("medal" in e for e in bad.problems())


def test_missing_column_is_reported(seed_dir, tmp_path):
    shutil.copy(f"{seed_dir}/users.csv", tmp_path / "users.csv")
    lines = (tmp_path / "users.csv").read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("registerDate,", "")
    (tmp_path / "users.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(L.LoadError, match="registerDate"):
        L.CsvReader(str(tmp_path)).read("users")


def test_bad_integer_is_reported(seed_dir, tmp_path):
    shutil.copy(f"{seed_dir}/teams.csv", tmp_path / "teams.csv")
    text = (tmp_path / "teams.csv").read_text(encoding="utf-8")
    (tmp_path / "teams.csv").write_text(text.replace(",2,0.0013,", ",2.0,0.0013,", 1), encoding="utf-8")
    with pytest.raises(L.LoadError, match="teams.csv"):
        L.CsvReader(str(tmp_path)).read("teams")


def test_cli_check_only(seed_dir):
    assert L.main(["--data-dir", seed_dir, "--check-only"]) == 0
