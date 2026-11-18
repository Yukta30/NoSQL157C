"""
Week-1 source checks for docs/csv_contract.md section 8.

Usage:
    pip install duckdb
    python scripts/verify_sources.py data/raw

Runs four checks and prints what to record in the contract:
  1. HostSegmentTitle values (and how many tagged competitions each has)
  2. Competitions date format
  3. PerformanceTier mapping (known grandmasters should be 4)
  4. Subset size sweep over MIN_YEAR / MIN_COMPS vs. the target DB limits

Scans multi-GB files (Users 2.7 GB, UserAchievements 10.4 GB); expect a few minutes.
"""
import sys
import time

import duckdb

RAW = sys.argv[1] if len(sys.argv) > 1 else "data/raw"

# --- Edit these after looking at the output -------------------------------
SEGMENTS = ["Featured", "Research", "Playground", "Recruitment"]
KNOWN_GRANDMASTERS = ["cdeotte", "abhishek", "titericz", "cpmpml"]  # any GM usernames work
YEARS_TO_TRY = [2010, 2015, 2018, 2020, 2022]
MIN_COMPS_TO_TRY = [None, 3]       # None = no activity filter (rule 4 off)
NODE_LIMIT = 200_000                # AuraDB Free caps - check current numbers
REL_LIMIT = 400_000
SKILL_CATS = ("data type", "task", "technique", "analysis")
INTEREST_CATS = ("subject",)
# ---------------------------------------------------------------------------

con = duckdb.connect()
t0 = time.time()


def src(name, file):
    # all_varchar: no type sniffing surprises; we parse explicitly below.
    con.execute(f"""
        CREATE OR REPLACE VIEW {name} AS
        SELECT * FROM read_csv('{RAW}/{file}', header=true, all_varchar=true,
                               quote='"', escape='"', max_line_size=50000000)
    """)


def header(title):
    print(f"\n{'=' * 70}\n{title}   [{time.time() - t0:.0f}s]\n{'=' * 70}")


for name, file in [
    ("comps", "Competitions.csv"), ("ctags", "CompetitionTags.csv"),
    ("tags", "Tags.csv"), ("teams", "Teams.csv"), ("tm", "TeamMemberships.csv"),
    ("users", "Users.csv"), ("ua", "UserAchievements.csv"),
    ("follows", "UserFollowers.csv"),
]:
    src(name, file)

# Small helper tables reused by several checks
con.execute("""
    CREATE TABLE tagcat AS
    SELECT Id AS tag_id, lower(Name) AS name, lower(trim(split_part(FullPath, '>', 1))) AS cat
    FROM tags
""")
con.execute("""
    CREATE TABLE ct AS
    SELECT DISTINCT c.CompetitionId AS cid, t.name, t.cat
    FROM ctags c JOIN tagcat t ON t.tag_id = c.TagId
""")
con.execute("""
    CREATE TABLE c_small AS
    SELECT Id AS cid, HostSegmentTitle AS seg, EnabledDate, DeadlineDate
    FROM comps
""")

# ---------------------------------------------------------------------------
header("1. HostSegmentTitle values")
con.sql("""
    SELECT seg AS HostSegmentTitle,
           count(*) AS competitions,
           count(*) FILTER (WHERE cid IN (SELECT cid FROM ct)) AS tagged
    FROM c_small GROUP BY 1 ORDER BY tagged DESC, competitions DESC
""").show(max_rows=50)
print("-> Put the segments you want in SEGMENTS (top of this file) and in contract section 2.")

# ---------------------------------------------------------------------------
header("2. Competitions date format")
con.sql("""
    SELECT col, count(*) AS non_empty,
           count(*) FILTER (WHERE try_strptime(v, '%m/%d/%Y') IS NOT NULL) AS plain_ok,
           count(*) FILTER (WHERE try_strptime(v, '%m/%d/%Y %H:%M:%S') IS NOT NULL) AS with_time_ok,
           any_value(v) AS example
    FROM (SELECT 'EnabledDate' AS col, EnabledDate AS v FROM c_small
          UNION ALL SELECT 'DeadlineDate', DeadlineDate FROM c_small)
    WHERE v IS NOT NULL
    GROUP BY col
""").show()
con.sql("""
    SELECT DeadlineDate AS unparsed_examples FROM c_small
    WHERE DeadlineDate IS NOT NULL
      AND try_strptime(DeadlineDate, '%m/%d/%Y') IS NULL
      AND try_strptime(DeadlineDate, '%m/%d/%Y %H:%M:%S') IS NULL
    LIMIT 10
""").show()
print("-> plain_ok == non_empty: contract's %m/%d/%Y is right.\n"
      "   with_time_ok == non_empty instead: parse with '%m/%d/%Y %H:%M:%S' and keep the date.\n"
      "   Anything in unparsed_examples: add that format to preprocessing.")

# ---------------------------------------------------------------------------
header("3. PerformanceTier mapping")
con.execute("CREATE TABLE u_small AS SELECT Id AS uid, UserName, PerformanceTier, RegisterDate FROM users")
con.sql("SELECT PerformanceTier, count(*) AS users FROM u_small GROUP BY 1 ORDER BY 1").show()
names = ",".join(f"'{n}'" for n in KNOWN_GRANDMASTERS)
con.sql(f"""
    WITH gm AS (SELECT * FROM u_small WHERE UserName IN ({names}))
    SELECT gm.UserName, gm.PerformanceTier AS overall_tier,
           ua.Tier AS competitions_tier, ua.TotalGold, ua.TotalSilver, ua.TotalBronze
    FROM gm LEFT JOIN ua ON ua.UserId = gm.uid AND ua.AchievementType = 'Competitions'
""").show()
print("-> Expect: overall/competitions tier 4 for grandmasters; counts shrink sharply 0 -> 4;\n"
      "   tier 5 is a small staff group (user 'kaggleteam' is 5). If so, the mapping is confirmed.")

# ---------------------------------------------------------------------------
header("4. Subset size sweep")
con.execute("""
    CREATE TABLE cand_comps AS
    SELECT cid, seg,
           year(coalesce(try_strptime(DeadlineDate, '%m/%d/%Y'),
                         try_strptime(DeadlineDate, '%m/%d/%Y %H:%M:%S'))) AS yr
    FROM c_small WHERE cid IN (SELECT cid FROM ct)
""")
con.execute("""
    CREATE TABLE cand_teams AS
    SELECT Id AS tid, CompetitionId AS cid FROM teams
    WHERE CompetitionId IN (SELECT cid FROM cand_comps) AND IsBenchmark = 'False'
""")
con.execute("""
    CREATE TABLE cand_mem AS
    SELECT DISTINCT m.TeamId AS tid, m.UserId AS uid
    FROM tm m
    WHERE m.TeamId IN (SELECT tid FROM cand_teams) AND m.UserId <> '1'
      AND m.UserId IN (SELECT uid FROM u_small)          -- drop deleted accounts
""")
con.execute("""
    CREATE TABLE cand_follows AS
    SELECT UserId AS a, FollowingUserId AS b FROM follows
    WHERE UserId IN (SELECT uid FROM cand_mem) AND FollowingUserId IN (SELECT uid FROM cand_mem)
""")

seg_list = ",".join(f"'{s}'" for s in SEGMENTS)
skill_list = ",".join(f"'{c}'" for c in SKILL_CATS)
interest_list = ",".join(f"'{c}'" for c in INTEREST_CATS)
rows = []

for min_year in YEARS_TO_TRY:
    for min_comps in MIN_COMPS_TO_TRY:
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE s_mem0 AS
            SELECT m.tid, m.uid, t.cid
            FROM cand_mem m
            JOIN cand_teams t USING (tid)
            JOIN cand_comps c USING (cid)
            WHERE c.seg IN ({seg_list}) AND c.yr >= {min_year}
        """)
        if min_comps:
            con.execute(f"""
                CREATE OR REPLACE TEMP TABLE s_keep AS
                WITH ts AS (SELECT tid, count(*) AS sz FROM s_mem0 GROUP BY tid)
                SELECT m.uid FROM s_mem0 m JOIN ts USING (tid)
                GROUP BY m.uid
                HAVING max(ts.sz) >= 2 OR count(DISTINCT m.cid) >= {min_comps}
            """)
        else:
            con.execute("CREATE OR REPLACE TEMP TABLE s_keep AS SELECT DISTINCT uid FROM s_mem0")
        con.execute("""
            CREATE OR REPLACE TEMP TABLE s_mem AS
            SELECT * FROM s_mem0 WHERE uid IN (SELECT uid FROM s_keep)
        """)
        r = con.execute(f"""
            WITH
              u   AS (SELECT DISTINCT uid FROM s_mem),
              t   AS (SELECT DISTINCT tid, cid FROM s_mem),
              c   AS (SELECT DISTINCT cid FROM s_mem),
              cs  AS (SELECT DISTINCT cid, name, cat FROM ct WHERE cid IN (SELECT cid FROM c)),
              us  AS (SELECT DISTINCT m.uid, cs.name, cs.cat FROM s_mem m JOIN cs USING (cid)),
              ww  AS (SELECT DISTINCT a.uid AS x, b.uid AS y FROM s_mem a
                      JOIN s_mem b ON a.tid = b.tid AND a.uid < b.uid),
              fo  AS (SELECT * FROM cand_follows
                      WHERE a IN (SELECT uid FROM u) AND b IN (SELECT uid FROM u))
            SELECT
              (SELECT count(*) FROM u),
              (SELECT count(*) FROM t),
              (SELECT count(*) FROM c),
              (SELECT count(DISTINCT name) FROM cs WHERE cat IN ({skill_list})),
              (SELECT count(DISTINCT name) FROM cs WHERE cat IN ({interest_list})),
              (SELECT count(*) FROM s_mem),
              (SELECT count(*) FROM cs WHERE cat IN ({skill_list}, {interest_list})),
              (SELECT count(*) FROM us WHERE cat IN ({skill_list})),
              (SELECT count(*) FROM us WHERE cat IN ({interest_list})),
              (SELECT count(*) FROM fo),
              (SELECT count(*) FROM ww)
        """).fetchone()
        users, teams_n, comps_n, skills, interests, mem, comp_tags, has_skill, interested, fol, ww = r
        nodes = users + teams_n + comps_n + skills + interests
        rels = mem + teams_n + comp_tags + has_skill + interested + fol + ww   # teams_n = PARTICIPATED_IN
        fits = "FITS" if nodes <= NODE_LIMIT and rels <= REL_LIMIT else "too big"
        rows.append((min_year, min_comps or "-", users, teams_n, comps_n, nodes, mem, has_skill,
                     interested, fol, ww, rels, fits))

cols = ("MIN_YEAR", "MIN_COMPS", "users", "teams", "comps", "NODES", "member_of",
        "has_skill", "interested", "follows", "worked_with", "RELS", "vs limit")
widths = [max(len(str(x)) for x in col) for col in zip(cols, *rows)]
print("  ".join(c.rjust(w) for c, w in zip(cols, widths)))
for row in rows:
    print("  ".join(f"{v:,}".rjust(w) if isinstance(v, int) else str(v).rjust(w)
                    for v, w in zip(row, widths)))
print(f"\n-> Pick the loosest row marked FITS (leave ~20% headroom for app users and FOLLOWS\n"
      f"   created in the demo). Record MIN_YEAR / MIN_COMPS in contract section 8.\n"
      f"   Limits used: {NODE_LIMIT:,} nodes / {REL_LIMIT:,} rels.   [total {time.time() - t0:.0f}s]")
