"""Turn the raw Meta Kaggle CSVs into the graph CSVs. See docs/csv_contract.md.

    python scripts/preprocess_data.py                      # data/raw -> data/processed
    python scripts/preprocess_data.py --raw-dir data/raw --out-dir data/processed
    python scripts/preprocess_data.py --min-year 2018      # only if the graph outgrows AuraDB Free

Then check and load the output:

    python scripts/load_neo4j.py --data-dir data/processed --check-only
    python scripts/load_neo4j.py --data-dir data/processed --wipe

Uses DuckDB so the multi-GB files (Users 2.7 GB, UserAchievements 10.4 GB) are
streamed, not loaded into memory. Expect a few minutes.
"""
import argparse
import os
import sys
import time

import duckdb

# Contract section 1: the files we read.
SOURCES = {
    "comps": "Competitions.csv",
    "ctags": "CompetitionTags.csv",
    "tags": "Tags.csv",
    "teams_raw": "Teams.csv",
    "tm_raw": "TeamMemberships.csv",
    "users_raw": "Users.csv",
    "ua_raw": "UserAchievements.csv",
    "follows_raw": "UserFollowers.csv",
}

# Contract section 2: competition segments we keep.
SEGMENTS = ("Featured", "Research", "Playground", "Recruitment")
# Contract section 3: which tag categories become Skill / Interest nodes.
SKILL_CATS = ("data type", "task", "technique", "analysis", "packages")
INTEREST_CATS = ("subject",)
KAGGLE_BOT_ID = 1

# Contract section 3: output files and column order (must match load_neo4j.py).
OUTPUTS = [
    "skills", "interests", "competitions", "teams", "users",
    "member_of", "competition_skill", "competition_interest",
    "user_skill", "user_interest", "follows",
]

AURA_FREE_NODE_CAP = 200_000
AURA_FREE_REL_CAP = 400_000

TIER_SQL = """CASE {col}
    WHEN 0 THEN 'novice' WHEN 1 THEN 'novice' WHEN 2 THEN 'expert'
    WHEN 3 THEN 'master' WHEN 4 THEN 'grandmaster' WHEN 5 THEN 'staff' END"""


def sql_list(values):
    return "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in values) + ")"


class Pipeline:
    def __init__(self, raw_dir, out_dir, min_year=None):
        self.raw_dir = raw_dir
        self.out_dir = out_dir
        self.min_year = min_year
        self.con = duckdb.connect()
        self.t0 = time.time()

    def log(self, message):
        print(f"[{time.time() - self.t0:6.0f}s] {message}", flush=True)

    def run(self):
        self.check_sources()
        self.register_sources()
        self.build_subset()
        self.build_nodes()
        self.build_relationships()
        self.write_outputs()
        self.report()

    # ---------- inputs ----------

    def check_sources(self):
        missing = [f for f in SOURCES.values() if not os.path.exists(os.path.join(self.raw_dir, f))]
        if missing:
            sys.exit(f"Missing in {self.raw_dir}: {', '.join(missing)}. See docs/csv_contract.md section 1.")

    def register_sources(self):
        # all_varchar: no type sniffing surprises on huge files; every value is
        # parsed explicitly below with TRY_CAST / strptime.
        for name, file in SOURCES.items():
            path = os.path.join(self.raw_dir, file).replace("'", "''")
            self.con.execute(f"""
                CREATE OR REPLACE VIEW {name} AS
                SELECT * FROM read_csv('{path}', header=true, all_varchar=true,
                                       quote='"', escape='"', max_line_size=50000000)
            """)

    def q(self, sql):
        self.con.execute(sql)

    # ---------- section 2: subset ----------

    def build_subset(self):
        self.log("Tags and candidate competitions")
        self.q(f"""
            CREATE TABLE tag AS
            SELECT TRY_CAST(Id AS BIGINT) AS tag_id, lower(Name) AS name,
                   lower(trim(split_part(FullPath, '>', 1))) AS category
            FROM tags
        """)
        self.q(f"""
            CREATE TABLE tag_kind AS
            SELECT tag_id, name, category,
                   CASE WHEN category IN {sql_list(SKILL_CATS)} THEN 'skill'
                        WHEN category IN {sql_list(INTEREST_CATS)} THEN 'interest' END AS kind
            FROM tag
        """)
        year_filter = (f"AND year(strptime(DeadlineDate, '%m/%d/%Y %H:%M:%S')) >= {int(self.min_year)}"
                       if self.min_year else "")
        self.q(f"""
            CREATE TABLE candidate_comp AS
            SELECT TRY_CAST(Id AS BIGINT) AS cid, Slug AS slug, Title AS title,
                   HostSegmentTitle AS segment,
                   year(strptime(DeadlineDate, '%m/%d/%Y %H:%M:%S')) AS year,
                   TRY_CAST(MaxTeamSize AS BIGINT) AS max_team_size,
                   TRY_CAST(TotalTeams AS BIGINT) AS total_teams
            FROM comps
            WHERE HostSegmentTitle IN {sql_list(SEGMENTS)}
              AND TRY_CAST(Id AS BIGINT) IN (SELECT TRY_CAST(CompetitionId AS BIGINT) FROM ctags)
              {year_filter}
        """)
        self.q("""
            CREATE TABLE comp_tag AS
            SELECT DISTINCT TRY_CAST(c.CompetitionId AS BIGINT) AS cid, t.name, t.kind
            FROM ctags c JOIN tag_kind t ON t.tag_id = TRY_CAST(c.TagId AS BIGINT)
            WHERE t.kind IS NOT NULL
              AND TRY_CAST(c.CompetitionId AS BIGINT) IN (SELECT cid FROM candidate_comp)
        """)

        self.log("Teams in candidate competitions (Teams.csv, 800 MB)")
        self.q("""
            CREATE TABLE cand_team AS
            SELECT TRY_CAST(Id AS BIGINT) AS team_id, TRY_CAST(CompetitionId AS BIGINT) AS cid,
                   TeamName AS team_name, IsBenchmark AS is_benchmark,
                   TRY_CAST(TRY_CAST(nullif(Medal, '') AS DOUBLE) AS INTEGER) AS medal,
                   TRY_CAST(TRY_CAST(nullif(PrivateLeaderboardRank, '') AS DOUBLE) AS BIGINT) AS private_rank
            FROM teams_raw
            WHERE TRY_CAST(CompetitionId AS BIGINT) IN (SELECT cid FROM candidate_comp)
        """)
        # rankPct denominator: max rank over all ranked teams in the competition.
        self.q("""
            CREATE TABLE field_size AS
            SELECT cid, max(private_rank) AS field_size
            FROM cand_team WHERE private_rank IS NOT NULL GROUP BY cid
        """)
        # History teams: ranked, non-benchmark (contract section 4).
        self.q("""
            CREATE TABLE history_team AS
            SELECT t.team_id, t.cid, t.team_name, t.private_rank,
                   CASE WHEN t.medal IN (1, 2, 3) THEN t.medal END AS medal,
                   round(t.private_rank / f.field_size, 4) AS rank_pct
            FROM cand_team t JOIN field_size f USING (cid)
            WHERE t.is_benchmark = 'False' AND t.private_rank IS NOT NULL
        """)

        self.log("Existing users (Users.csv, 2.7 GB)")
        self.q(f"""
            CREATE TABLE existing_user AS
            SELECT DISTINCT TRY_CAST(Id AS BIGINT) AS uid FROM users_raw
            WHERE TRY_CAST(Id AS BIGINT) IS NOT NULL AND TRY_CAST(Id AS BIGINT) <> {KAGGLE_BOT_ID}
        """)

        self.log("Memberships of history teams (TeamMemberships.csv, 443 MB)")
        self.q("""
            CREATE TABLE history_member AS
            SELECT DISTINCT TRY_CAST(m.UserId AS BIGINT) AS uid, TRY_CAST(m.TeamId AS BIGINT) AS team_id
            FROM tm_raw m
            WHERE TRY_CAST(m.TeamId AS BIGINT) IN (SELECT team_id FROM history_team)
              AND TRY_CAST(m.UserId AS BIGINT) IN (SELECT uid FROM existing_user)
        """)

        # Graph teams: medal teams with >= 2 existing members.
        self.q("""
            CREATE TABLE graph_team AS
            SELECT h.*, s.team_size
            FROM history_team h
            JOIN (SELECT team_id, count(*) AS team_size FROM history_member GROUP BY team_id) s
              USING (team_id)
            WHERE h.medal IS NOT NULL AND s.team_size >= 2
        """)
        self.q("""
            CREATE TABLE graph_member AS
            SELECT uid, team_id FROM history_member
            WHERE team_id IN (SELECT team_id FROM graph_team)
        """)
        self.q("CREATE TABLE kept_user AS SELECT DISTINCT uid FROM graph_member")
        self.q("""
            CREATE TABLE final_comp AS
            SELECT * FROM candidate_comp WHERE cid IN (SELECT cid FROM graph_team)
        """)
        # Every history team of a kept user (for weights, not exported).
        self.q("""
            CREATE TABLE user_history AS
            SELECT m.uid, h.team_id, h.cid, h.medal, h.rank_pct
            FROM history_member m JOIN history_team h USING (team_id)
            WHERE m.uid IN (SELECT uid FROM kept_user)
        """)

    # ---------- section 3: node files ----------

    def build_nodes(self):
        self.log("Node tables")
        self.q("""
            CREATE TABLE out_competitions AS
            SELECT cid AS competitionId, slug, title, segment, year,
                   max_team_size AS maxTeamSize, total_teams AS totalTeams
            FROM final_comp ORDER BY cid
        """)
        self.q("""
            CREATE TABLE out_teams AS
            SELECT team_id AS teamId, cid AS competitionId, team_name AS teamName,
                   CASE medal WHEN 1 THEN 'gold' WHEN 2 THEN 'silver' WHEN 3 THEN 'bronze' END AS medal,
                   private_rank AS privateRank, rank_pct AS rankPct, team_size AS teamSize
            FROM graph_team ORDER BY team_id
        """)
        for kind, table in (("skill", "out_skills"), ("interest", "out_interests")):
            self.q(f"""
                CREATE TABLE {table} AS
                SELECT DISTINCT t.name, t.category, t.tag_id AS tagId
                FROM tag_kind t
                WHERE t.kind = '{kind}'
                  AND t.name IN (SELECT name FROM comp_tag
                                 WHERE kind = '{kind}' AND cid IN (SELECT cid FROM final_comp))
                ORDER BY t.name
            """)

        self.log("User details (UserAchievements.csv, 10.4 GB - the slow part)")
        self.q("""
            CREATE TABLE comp_achievement AS
            SELECT TRY_CAST(UserId AS BIGINT) AS uid,
                   TRY_CAST(TRY_CAST(nullif(Tier, '') AS DOUBLE) AS INTEGER) AS tier,
                   coalesce(TRY_CAST(TRY_CAST(nullif(TotalGold, '') AS DOUBLE) AS BIGINT), 0) AS golds,
                   coalesce(TRY_CAST(TRY_CAST(nullif(TotalSilver, '') AS DOUBLE) AS BIGINT), 0) AS silvers,
                   coalesce(TRY_CAST(TRY_CAST(nullif(TotalBronze, '') AS DOUBLE) AS BIGINT), 0) AS bronzes
            FROM ua_raw
            WHERE AchievementType = 'Competitions'
              AND TRY_CAST(UserId AS BIGINT) IN (SELECT uid FROM kept_user)
        """)
        self.q(f"""
            CREATE TABLE out_users AS
            SELECT 'k' || CAST(u.uid AS VARCHAR) AS userId,
                   r.UserName AS username, r.DisplayName AS displayName,
                   {TIER_SQL.format(col="TRY_CAST(TRY_CAST(nullif(r.PerformanceTier, '') AS DOUBLE) AS INTEGER)")}
                       AS tier,
                   nullif(r.Country, '') AS country,
                   strftime(TRY_STRPTIME(r.RegisterDate, '%m/%d/%Y'), '%Y-%m-%d') AS registerDate,
                   {TIER_SQL.format(col="a.tier")} AS compTier,
                   coalesce(a.golds, 0) AS golds, coalesce(a.silvers, 0) AS silvers,
                   coalesce(a.bronzes, 0) AS bronzes,
                   'kaggle' AS source
            FROM kept_user u
            JOIN (SELECT * FROM users_raw WHERE TRY_CAST(Id AS BIGINT) IN (SELECT uid FROM kept_user)) r
              ON TRY_CAST(r.Id AS BIGINT) = u.uid
            LEFT JOIN (SELECT uid, any_value(tier) AS tier, any_value(golds) AS golds,
                              any_value(silvers) AS silvers, any_value(bronzes) AS bronzes
                       FROM comp_achievement GROUP BY uid) a
              ON a.uid = u.uid
            QUALIFY row_number() OVER (PARTITION BY u.uid ORDER BY r.UserName) = 1
            ORDER BY u.uid
        """)

    # ---------- sections 3 + 4: relationship files ----------

    def build_relationships(self):
        self.log("Relationship tables")
        self.q("""
            CREATE TABLE out_member_of AS
            SELECT 'k' || CAST(uid AS VARCHAR) AS userId, team_id AS teamId
            FROM graph_member ORDER BY uid, team_id
        """)
        for kind, table, col in (("skill", "out_competition_skill", "skill"),
                                 ("interest", "out_competition_interest", "interest")):
            self.q(f"""
                CREATE TABLE {table} AS
                SELECT cid AS competitionId, name AS {col}
                FROM comp_tag
                WHERE kind = '{kind}' AND cid IN (SELECT cid FROM final_comp)
                ORDER BY cid, name
            """)

        # Pairs exist from graph teams; weights come from all history teams.
        self.q("""
            CREATE TABLE skill_pair AS
            SELECT DISTINCT m.uid, ct.name AS skill
            FROM graph_member m JOIN graph_team g USING (team_id)
            JOIN comp_tag ct ON ct.cid = g.cid AND ct.kind = 'skill'
        """)
        self.q("""
            CREATE TABLE out_user_skill AS
            SELECT 'k' || CAST(p.uid AS VARCHAR) AS userId, p.skill,
                   round(1 - exp(-sum(CASE h.medal WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1
                                       ELSE CASE WHEN h.rank_pct <= 0.25 THEN 0.75 ELSE 0.25 END
                                   END) / 3.0), 4) AS weight,
                   count(*) AS competitions,
                   count(h.medal) AS medals,
                   'kaggle' AS source
            FROM skill_pair p
            JOIN user_history h ON h.uid = p.uid
            JOIN comp_tag ct ON ct.cid = h.cid AND ct.kind = 'skill' AND ct.name = p.skill
            GROUP BY p.uid, p.skill
            ORDER BY p.uid, p.skill
        """)
        self.q("""
            CREATE TABLE interest_pair AS
            SELECT DISTINCT m.uid, ct.name AS interest
            FROM graph_member m JOIN graph_team g USING (team_id)
            JOIN comp_tag ct ON ct.cid = g.cid AND ct.kind = 'interest'
        """)
        self.q("""
            CREATE TABLE out_user_interest AS
            SELECT 'k' || CAST(p.uid AS VARCHAR) AS userId, p.interest,
                   round(1 - exp(-count(*) / 2.0), 4) AS weight,
                   count(*) AS competitions,
                   'kaggle' AS source
            FROM interest_pair p
            JOIN user_history h ON h.uid = p.uid
            JOIN comp_tag ct ON ct.cid = h.cid AND ct.kind = 'interest' AND ct.name = p.interest
            GROUP BY p.uid, p.interest
            ORDER BY p.uid, p.interest
        """)

        self.log("Follows between kept users (UserFollowers.csv)")
        self.q("""
            CREATE TABLE out_follows AS
            SELECT DISTINCT 'k' || CAST(TRY_CAST(UserId AS BIGINT) AS VARCHAR) AS followerId,
                   'k' || CAST(TRY_CAST(FollowingUserId AS BIGINT) AS VARCHAR) AS followeeId,
                   strftime(TRY_STRPTIME(CreationDate, '%m/%d/%Y'), '%Y-%m-%d') AS since
            FROM follows_raw
            WHERE TRY_CAST(UserId AS BIGINT) IN (SELECT uid FROM kept_user)
              AND TRY_CAST(FollowingUserId AS BIGINT) IN (SELECT uid FROM kept_user)
              AND UserId <> FollowingUserId
            ORDER BY followerId, followeeId
        """)

    # ---------- output ----------

    def write_outputs(self):
        os.makedirs(self.out_dir, exist_ok=True)
        for name in OUTPUTS:
            path = os.path.join(self.out_dir, f"{name}.csv").replace("'", "''")
            # Nulls become empty strings; DuckDB quotes only fields that need it.
            self.q(f"COPY out_{name} TO '{path}' (HEADER, DELIMITER ',', QUOTE '\"', NULLSTR '')")
        self.log(f"Wrote {len(OUTPUTS)} files to {self.out_dir}")

    def count(self, table):
        return self.con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def report(self):
        nodes = {n: self.count(f"out_{n}") for n in ("users", "teams", "competitions", "skills", "interests")}
        rels = {n: self.count(f"out_{n}") for n in ("member_of", "competition_skill", "competition_interest",
                                                    "user_skill", "user_interest", "follows")}
        rels["participated_in"] = nodes["teams"]
        worked_with = self.con.execute("""
            SELECT count(*) FROM (
              SELECT DISTINCT a.uid, b.uid FROM graph_member a JOIN graph_member b
                ON a.team_id = b.team_id AND a.uid < b.uid)
        """).fetchone()[0]
        rels["worked_with (derived on load)"] = worked_with

        dupes = self.con.execute(
            "SELECT count(*) - count(DISTINCT username) FROM out_users").fetchone()[0]
        no_skill = self.con.execute(
            "SELECT count(*) FROM out_users WHERE userId NOT IN (SELECT userId FROM out_user_skill)").fetchone()[0]
        no_interest = self.con.execute(
            "SELECT count(*) FROM out_users WHERE userId NOT IN (SELECT userId FROM out_user_interest)"
        ).fetchone()[0]
        years = self.con.execute("SELECT min(year), max(year) FROM out_competitions").fetchone()

        total_nodes, total_rels = sum(nodes.values()), sum(rels.values())
        print("\nNodes")
        for k, v in nodes.items():
            print(f"  {k:<32}{v:>10,}")
        print(f"  {'TOTAL':<32}{total_nodes:>10,}   (AuraDB Free cap {AURA_FREE_NODE_CAP:,})")
        print("Relationships")
        for k, v in rels.items():
            print(f"  {k:<32}{v:>10,}")
        print(f"  {'TOTAL':<32}{total_rels:>10,}   (AuraDB Free cap {AURA_FREE_REL_CAP:,})")
        print("Checks")
        print(f"  competition years               {years[0]}-{years[1]}")
        print(f"  duplicate usernames             {dupes}")
        print(f"  users without HAS_SKILL         {no_skill:,}")
        print(f"  users without INTERESTED_IN     {no_interest:,}")
        if total_nodes > AURA_FREE_NODE_CAP or total_rels > AURA_FREE_REL_CAP:
            print("\nWARNING: over the AuraDB Free cap. Re-run with --min-year (contract section 2).")
        self.log("Done")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", default="data/raw", help="folder with the Meta Kaggle CSVs")
    parser.add_argument("--out-dir", default="data/processed", help="where to write the graph CSVs")
    parser.add_argument("--min-year", type=int, default=None,
                        help="optional: only competitions with a deadline in or after this year")
    args = parser.parse_args(argv)
    Pipeline(args.raw_dir, args.out_dir, args.min_year).run()


if __name__ == "__main__":
    main()
