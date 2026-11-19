"""Load the graph CSVs into Neo4j. See docs/csv_contract.md.

Examples:
    python scripts/load_neo4j.py --data-dir data/seed --check-only
    python scripts/load_neo4j.py --data-dir data/seed --wipe
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter
from itertools import combinations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(ROOT, "database", "schema.cypher")
BATCH_SIZE = 10_000
AURA_FREE_NODE_CAP = 200_000
AURA_FREE_REL_CAP = 400_000
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LoadError(Exception):
    pass


class CsvReader:
    """Reads the graph CSVs from one folder and converts their values."""

    COLUMNS = {
        "users": ["userId", "username", "displayName", "tier", "country", "registerDate",
                  "compTier", "golds", "silvers", "bronzes", "source"],
        "skills": ["name", "category", "tagId"],
        "interests": ["name", "category", "tagId"],
        "competitions": ["competitionId", "slug", "title", "segment", "year", "maxTeamSize", "totalTeams"],
        "teams": ["teamId", "competitionId", "teamName", "medal", "privateRank", "rankPct", "teamSize"],
        "member_of": ["userId", "teamId"],
        "competition_skill": ["competitionId", "skill"],
        "competition_interest": ["competitionId", "interest"],
        "user_skill": ["userId", "skill", "weight", "competitions", "medals", "source"],
        "user_interest": ["userId", "interest", "weight", "competitions", "source"],
        "follows": ["followerId", "followeeId", "since"],
    }
    INT_COLS = {
        "users": {"golds", "silvers", "bronzes"},
        "skills": {"tagId"},
        "interests": {"tagId"},
        "competitions": {"competitionId", "year", "maxTeamSize", "totalTeams"},
        "teams": {"teamId", "competitionId", "privateRank", "teamSize"},
        "member_of": {"teamId"},
        "competition_skill": {"competitionId"},
        "competition_interest": {"competitionId"},
        "user_skill": {"competitions", "medals"},
        "user_interest": {"competitions"},
    }
    FLOAT_COLS = {
        "teams": {"rankPct"},
        "user_skill": {"weight"},
        "user_interest": {"weight"},
    }

    def __init__(self, data_dir):
        self.data_dir = data_dir

    def read_all(self):
        return {name: self.read(name) for name in self.COLUMNS}

    def read(self, name):
        path = os.path.join(self.data_dir, f"{name}.csv")
        if not os.path.exists(path):
            raise LoadError(f"missing file: {path}")
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self._check_header(name, reader.fieldnames or [])
            return [self._convert_row(name, raw, lineno)
                    for lineno, raw in enumerate(reader, start=2)]

    def _check_header(self, name, fieldnames):
        missing = [c for c in self.COLUMNS[name] if c not in fieldnames]
        if missing:
            raise LoadError(f"{name}.csv is missing columns: {', '.join(missing)}")

    def _convert_row(self, name, raw, lineno):
        row = {}
        for col in self.COLUMNS[name]:
            row[col] = self._convert_value(name, col, raw[col], lineno)
        return row

    def _convert_value(self, name, col, value, lineno):
        if value == "":
            return None
        where = f"{name}.csv line {lineno} column {col}"
        if col in self.INT_COLS.get(name, ()):
            return self._parse(int, value, where)
        if col in self.FLOAT_COLS.get(name, ()):
            return self._parse(float, value, where)
        return value

    @staticmethod
    def _parse(fn, value, where):
        try:
            return fn(value)
        except ValueError:
            raise LoadError(f"{where}: bad value {value!r}") from None


class DataChecker:
    """Checks the CSV tables before anything is sent to the database."""

    def __init__(self, tables):
        self.t = tables
        self.errors = []

    def run(self):
        self._check_unique_keys()
        self._check_users()
        self._check_tags()
        self._check_teams()
        self._check_competition_links()
        self._check_user_links()
        self._check_follows()
        self._check_kaggle_users()
        return self.errors

    def _duplicates(self, name, rows, key):
        for value, n in Counter(r[key] for r in rows).items():
            if n > 1:
                self.errors.append(f"{name}: duplicate {key}={value!r} ({n} rows)")

    def _duplicate_pairs(self, name, rows, a, b):
        for pair, n in Counter((r[a], r[b]) for r in rows).items():
            if n > 1:
                self.errors.append(f"{name}: duplicate pair {a},{b}={pair} ({n} rows)")

    def _check_unique_keys(self):
        self._duplicates("users", self.t["users"], "userId")
        self._duplicates("users", self.t["users"], "username")
        self._duplicates("skills", self.t["skills"], "name")
        self._duplicates("interests", self.t["interests"], "name")
        self._duplicates("competitions", self.t["competitions"], "competitionId")
        self._duplicates("teams", self.t["teams"], "teamId")

    def _check_users(self):
        for r in self.t["users"]:
            if r["source"] not in ("kaggle", "app"):
                self.errors.append(f"users: {r['userId']} has source {r['source']!r}")
        self._check_iso("users", self.t["users"], "registerDate")

    def _check_iso(self, name, rows, col):
        for r in rows:
            if r[col] is not None and not ISO_DATE.match(r[col]):
                self.errors.append(f"{name}: {col} is not YYYY-MM-DD: {r[col]!r}")

    def _check_tags(self):
        for name in sorted(self._skill_names() & self._interest_names()):
            self.errors.append(f"tag {name!r} is both a skill and an interest")

    def _check_teams(self):
        comp_ids = {r["competitionId"] for r in self.t["competitions"]}
        for r in self.t["teams"]:
            if r["medal"] not in ("gold", "silver", "bronze"):
                self.errors.append(f"teams: {r['teamId']} has medal {r['medal']!r}")
            if r["rankPct"] is not None and not 0 <= r["rankPct"] <= 1:
                self.errors.append(f"teams: {r['teamId']} rankPct {r['rankPct']} outside 0..1")
            if r["competitionId"] not in comp_ids:
                self.errors.append(f"teams: {r['teamId']} references unknown competition {r['competitionId']}")

    def _check_competition_links(self):
        comp_ids = {r["competitionId"] for r in self.t["competitions"]}
        for r in self.t["competition_skill"]:
            if r["competitionId"] not in comp_ids:
                self.errors.append(f"competition_skill: unknown competition {r['competitionId']}")
            if r["skill"] not in self._skill_names():
                self.errors.append(f"competition_skill: unknown skill {r['skill']!r}")
        self._duplicate_pairs("competition_skill", self.t["competition_skill"], "competitionId", "skill")

        for r in self.t["competition_interest"]:
            if r["competitionId"] not in comp_ids:
                self.errors.append(f"competition_interest: unknown competition {r['competitionId']}")
            if r["interest"] not in self._interest_names():
                self.errors.append(f"competition_interest: unknown interest {r['interest']!r}")
        self._duplicate_pairs("competition_interest", self.t["competition_interest"], "competitionId", "interest")

    def _check_user_links(self):
        user_ids = self._user_ids()
        team_ids = {r["teamId"] for r in self.t["teams"]}
        team_sizes = Counter()
        for r in self.t["member_of"]:
            if r["userId"] not in user_ids:
                self.errors.append(f"member_of: unknown user {r['userId']}")
            if r["teamId"] not in team_ids:
                self.errors.append(f"member_of: unknown team {r['teamId']}")
            team_sizes[r["teamId"]] += 1
        self._duplicate_pairs("member_of", self.t["member_of"], "userId", "teamId")

        for r in self.t["teams"]:
            if team_sizes[r["teamId"]] != r["teamSize"]:
                self.errors.append(f"teams: {r['teamId']} teamSize={r['teamSize']} but "
                                   f"{team_sizes[r['teamId']]} member rows")
            if team_sizes[r["teamId"]] < 2:
                self.errors.append(f"teams: {r['teamId']} has fewer than 2 members")

        self._check_user_tags("user_skill", "skill", self._skill_names())
        self._check_user_tags("user_interest", "interest", self._interest_names())

    def _check_user_tags(self, name, tag_col, valid_tags):
        user_ids = self._user_ids()
        for r in self.t[name]:
            if r["userId"] not in user_ids:
                self.errors.append(f"{name}: unknown user {r['userId']}")
            if r[tag_col] not in valid_tags:
                self.errors.append(f"{name}: unknown {tag_col} {r[tag_col]!r}")
            if not 0 <= r["weight"] <= 1:
                self.errors.append(f"{name}: weight {r['weight']} outside 0..1 for {r['userId']}")
            if r["source"] not in ("kaggle", "self"):
                self.errors.append(f"{name}: source {r['source']!r} for {r['userId']}")
        self._duplicate_pairs(name, self.t[name], "userId", tag_col)

    def _check_follows(self):
        user_ids = self._user_ids()
        for r in self.t["follows"]:
            if r["followerId"] not in user_ids or r["followeeId"] not in user_ids:
                self.errors.append(f"follows: {r['followerId']} -> {r['followeeId']} has an unknown user")
            if r["followerId"] == r["followeeId"]:
                self.errors.append(f"follows: self-follow {r['followerId']}")
        self._duplicate_pairs("follows", self.t["follows"], "followerId", "followeeId")
        self._check_iso("follows", self.t["follows"], "since")

    def _check_kaggle_users(self):
        team_counts = Counter(r["userId"] for r in self.t["member_of"])
        for r in self.t["users"]:
            uid = r["userId"]
            if r["source"] == "kaggle" and team_counts[uid] == 0:
                self.errors.append(f"users: kaggle user {uid} has no MEMBER_OF rows")
            if r["source"] == "app" and team_counts[uid] > 0:
                self.errors.append(f"users: app user {uid} should have no teams")

    def _user_ids(self):
        return {r["userId"] for r in self.t["users"]}

    def _skill_names(self):
        return {r["name"] for r in self.t["skills"]}

    def _interest_names(self):
        return {r["name"] for r in self.t["interests"]}


class GraphData:
    """The graph tables, loaded from CSV, plus the numbers derived from them."""

    def __init__(self, tables):
        self.tables = tables

    @classmethod
    def from_dir(cls, data_dir):
        return cls(CsvReader(data_dir).read_all())

    def problems(self):
        return DataChecker(self.tables).run()

    def worked_with_pairs(self):
        members = {}
        for r in self.tables["member_of"]:
            members.setdefault(r["teamId"], []).append(r["userId"])
        pairs = Counter()
        for team_members in members.values():
            for a, b in combinations(sorted(team_members), 2):
                pairs[(a, b)] += 1
        return dict(pairs)

    def expected_counts(self):
        t = self.tables
        return {
            "nodes": {
                "User": len(t["users"]),
                "Skill": len(t["skills"]),
                "Interest": len(t["interests"]),
                "Competition": len(t["competitions"]),
                "Team": len(t["teams"]),
            },
            "rels": {
                "MEMBER_OF": len(t["member_of"]),
                "PARTICIPATED_IN": len(t["teams"]),
                "USES_SKILL": len(t["competition_skill"]),
                "ABOUT": len(t["competition_interest"]),
                "HAS_SKILL": len(t["user_skill"]),
                "INTERESTED_IN": len(t["user_interest"]),
                "FOLLOWS": len(t["follows"]),
                "WORKED_WITH": len(self.worked_with_pairs()),
            },
        }


class Neo4jLoader:
    """Writes GraphData into Neo4j and checks the counts afterwards."""

    NODE_QUERIES = [
        ("skills", """
            UNWIND $rows AS r
            MERGE (s:Skill {name: r.name})
            SET s.category = r.category, s.tagId = r.tagId"""),
        ("interests", """
            UNWIND $rows AS r
            MERGE (i:Interest {name: r.name})
            SET i.category = r.category, i.tagId = r.tagId"""),
        ("competitions", """
            UNWIND $rows AS r
            MERGE (c:Competition {competitionId: r.competitionId})
            SET c.slug = r.slug, c.title = r.title, c.segment = r.segment, c.year = r.year,
                c.maxTeamSize = r.maxTeamSize, c.totalTeams = r.totalTeams"""),
        ("teams", """
            UNWIND $rows AS r
            MERGE (t:Team {teamId: r.teamId})
            SET t.teamName = r.teamName, t.medal = r.medal, t.privateRank = r.privateRank,
                t.rankPct = r.rankPct, t.teamSize = r.teamSize
            WITH t, r
            MATCH (c:Competition {competitionId: r.competitionId})
            MERGE (t)-[:PARTICIPATED_IN]->(c)"""),
        ("users", """
            UNWIND $rows AS r
            MERGE (u:User {userId: r.userId})
            SET u.username = r.username, u.displayName = r.displayName, u.tier = r.tier,
                u.country = r.country, u.registerDate = date(r.registerDate),
                u.compTier = r.compTier, u.golds = coalesce(r.golds, 0),
                u.silvers = coalesce(r.silvers, 0), u.bronzes = coalesce(r.bronzes, 0),
                u.source = r.source"""),
    ]

    REL_QUERIES = [
        ("member_of", """
            UNWIND $rows AS r
            MATCH (u:User {userId: r.userId})
            MATCH (t:Team {teamId: r.teamId})
            MERGE (u)-[:MEMBER_OF]->(t)"""),
        ("competition_skill", """
            UNWIND $rows AS r
            MATCH (c:Competition {competitionId: r.competitionId})
            MATCH (s:Skill {name: r.skill})
            MERGE (c)-[:USES_SKILL]->(s)"""),
        ("competition_interest", """
            UNWIND $rows AS r
            MATCH (c:Competition {competitionId: r.competitionId})
            MATCH (i:Interest {name: r.interest})
            MERGE (c)-[:ABOUT]->(i)"""),
        ("user_skill", """
            UNWIND $rows AS r
            MATCH (u:User {userId: r.userId})
            MATCH (s:Skill {name: r.skill})
            MERGE (u)-[h:HAS_SKILL]->(s)
            SET h.weight = r.weight, h.competitions = r.competitions,
                h.medals = r.medals, h.source = r.source"""),
        ("user_interest", """
            UNWIND $rows AS r
            MATCH (u:User {userId: r.userId})
            MATCH (i:Interest {name: r.interest})
            MERGE (u)-[h:INTERESTED_IN]->(i)
            SET h.weight = r.weight, h.competitions = r.competitions, h.source = r.source"""),
        ("follows", """
            UNWIND $rows AS r
            MATCH (a:User {userId: r.followerId})
            MATCH (b:User {userId: r.followeeId})
            MERGE (a)-[f:FOLLOWS]->(b)
            SET f.since = date(r.since)"""),
    ]

    # Same as the contract's section 6.
    WORKED_WITH_QUERY = """
        MATCH (a:User)-[:MEMBER_OF]->(t:Team)<-[:MEMBER_OF]-(b:User)
        WHERE a.userId < b.userId
        WITH a, b, count(t) AS times
        CALL (a, b, times) {
          MERGE (a)-[w:WORKED_WITH]-(b)
          SET w.times = times
        } IN TRANSACTIONS OF 10000 ROWS"""

    def __init__(self, session, data):
        self.session = session
        self.data = data

    def wipe(self):
        self.session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS").consume()

    def apply_schema(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            for statement in self._split_cypher(f.read()):
                self.session.run(statement).consume()

    @staticmethod
    def _split_cypher(text):
        lines = [re.sub(r"//.*$", "", line) for line in text.splitlines()]
        return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]

    def load_nodes(self):
        for name, query in self.NODE_QUERIES:
            self._write_rows(query, self.data.tables[name])

    def load_relationships(self):
        for name, query in self.REL_QUERIES:
            self._write_rows(query, self.data.tables[name])

    def derive_worked_with(self):
        self.session.run(self.WORKED_WITH_QUERY).consume()

    def _write_rows(self, query, rows):
        for start in range(0, len(rows), BATCH_SIZE):
            self.session.execute_write(self._run_batch, query, rows[start:start + BATCH_SIZE])

    @staticmethod
    def _run_batch(tx, query, rows):
        tx.run(query, rows=rows).consume()

    def count(self, cypher):
        return self.session.run(cypher).single()["c"]

    def existing_users(self):
        return self.count("MATCH (u:User) RETURN count(u) AS c")

    def validate(self):
        problems = []
        expected = self.data.expected_counts()
        print("\nCounts (database vs CSV):")
        for label, want in expected["nodes"].items():
            got = self.count(f"MATCH (n:{label}) RETURN count(n) AS c")
            print(f"  {label:<16} {got:>8}  expected {want}")
            if got != want:
                problems.append(f"{label} nodes: {got} != {want}")
        for rel, want in expected["rels"].items():
            got = self.count(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")
            print(f"  {rel:<16} {got:>8}  expected {want}")
            if got != want:
                problems.append(f"{rel} relationships: {got} != {want}")

        checks = {
            "teams with no competition":
                "MATCH (t:Team) WHERE NOT (t)-[:PARTICIPATED_IN]->() RETURN count(t) AS c",
            "teams with fewer than 2 members":
                "MATCH (t:Team) WHERE COUNT { (t)<-[:MEMBER_OF]-() } < 2 RETURN count(t) AS c",
            "kaggle users with no team":
                "MATCH (u:User {source: 'kaggle'}) WHERE NOT (u)-[:MEMBER_OF]->() RETURN count(u) AS c",
        }
        for label, cypher in checks.items():
            n = self.count(cypher)
            print(f"  {label}: {n}")
            if n:
                problems.append(f"{n} {label}")

        total_nodes = sum(expected["nodes"].values())
        total_rels = sum(expected["rels"].values())
        print(f"\nTotals: {total_nodes} nodes, {total_rels} relationships "
              f"(AuraDB Free cap: {AURA_FREE_NODE_CAP} / {AURA_FREE_REL_CAP})")
        if total_nodes > AURA_FREE_NODE_CAP or total_rels > AURA_FREE_REL_CAP:
            print("WARNING: over the AuraDB Free cap.")
        return problems


class LoadCli:
    """Runs the whole job from the command line."""

    def __init__(self, argv=None):
        parser = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--data-dir", default=os.path.join(ROOT, "data", "processed"),
                            help="folder with the CSVs (default: data/processed)")
        parser.add_argument("--wipe", action="store_true", help="delete everything in the database first")
        parser.add_argument("--check-only", action="store_true", help="check the CSVs only, no database")
        self.args = parser.parse_args(argv)

    def run(self):
        try:
            data = GraphData.from_dir(self.args.data_dir)
        except LoadError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

        errors = data.problems()
        if errors:
            print(f"CSV check failed with {len(errors)} problem(s):", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print(f"CSV check passed: {self.args.data_dir}")
        if self.args.check_only:
            return 0

        uri = os.environ.get("NEO4J_URI")
        password = os.environ.get("NEO4J_PASSWORD")
        if not uri or password is None:
            print("ERROR: set NEO4J_URI and NEO4J_PASSWORD.", file=sys.stderr)
            return 2
        username = os.environ.get("NEO4J_USERNAME", "neo4j")
        database = os.environ.get("NEO4J_DATABASE", "neo4j")

        return self._load(uri, username, password, database, data)

    def _load(self, uri, username, password, database, data):
        from neo4j import GraphDatabase

        with GraphDatabase.driver(uri, auth=(username, password)) as driver:
            driver.verify_connectivity()
            with driver.session(database=database) as session:
                loader = Neo4jLoader(session, data)
                existing = loader.existing_users()
                if existing and not self.args.wipe:
                    print(f"ERROR: database already has {existing} User nodes. Use --wipe to replace them.",
                          file=sys.stderr)
                    return 1
                if self.args.wipe:
                    print(f"Wiping {database} at {uri} ...")
                    loader.wipe()
                loader.apply_schema()
                loader.load_nodes()
                loader.load_relationships()
                loader.derive_worked_with()
                problems = loader.validate()

        if problems:
            print("\nValidation FAILED:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        print("\nLoad and validation passed.")
        return 0


def main(argv=None):
    return LoadCli(argv).run()


if __name__ == "__main__":
    sys.exit(main())
