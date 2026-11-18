"""
Generate the hand-designed seed graph in data/seed/ (see data/seed/README.md).

    python scripts/make_seed.py

Deterministic: same output every run. Follows docs/csv_contract.md exactly,
including the section 4 derivation rules (pairs from graph teams, weights from
full history). Edit the scenario tables below, re-run, then update the expected
answers in data/seed/README.md if they change.

All IDs and people are fictional. Never load seed and real data into the same
database.
"""
import csv
import math
import os
from collections import defaultdict
from itertools import combinations

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "seed")

# ---------------------------------------------------------------------------
# Vocabulary (real Kaggle tag names and categories; tagIds are fictional)
# ---------------------------------------------------------------------------
SKILLS = [  # name, category, tagId
    ("tabular", "data type", 1001),
    ("image", "data type", 1002),
    ("text", "data type", 1003),
    ("nlp", "analysis", 1004),
    ("computer vision", "technique", 1005),
    ("time series analysis", "technique", 1006),
    ("regression", "task", 1007),
    ("binary classification", "task", 1008),
    ("tensorflow", "packages", 1009),
]
INTERESTS = [
    ("finance", "subject", 2001),
    ("health", "subject", 2002),
    ("sports", "subject", 2003),
    ("biology", "subject", 2004),
    ("medicine", "subject", 2005),
]
SKILL_NAMES = {s[0] for s in SKILLS}
INTEREST_NAMES = {i[0] for i in INTERESTS}

# ---------------------------------------------------------------------------
# Competitions in the graph
# key: (competitionId, slug, title, segment, year, maxTeamSize, totalTeams, tags)
# ---------------------------------------------------------------------------
COMPS = {
    "C1": (9001, "seed-credit-risk", "Seed Credit Risk", "Featured", 2021, 5, 1200,
           ["tabular", "binary classification", "finance"]),
    "C2": (9002, "seed-retina-scan", "Seed Retina Scan Challenge", "Research", 2022, 5, 800,
           ["image", "computer vision", "health", "medicine"]),
    "C3": (9003, "seed-clinical-notes", "Seed Clinical Notes NLP", "Featured", 2023, 5, 1500,
           ["text", "nlp", "health", "medicine"]),
    "C4": (9004, "seed-energy-forecast", "Seed Energy Demand Forecast", "Playground", 2024, 3, 600,
           ["tabular", "time series analysis", "regression"]),          # no interest tag
    "C5": (9005, "seed-match-outcome", "Seed Match Outcome Prediction", "Playground", 2022, 4, 400,
           ["sports"]),                                                  # no skill tag
    "C6": (9006, "seed-protein-atlas", "Seed Protein Image Atlas", "Research", 2025, 5, 300,
           ["image", "computer vision", "tensorflow", "biology"]),
    "C7": (9007, "seed-market-sentiment", "Seed Market Sentiment", "Featured", 2024, 5, 900,
           ["text", "nlp", "time series analysis", "finance"]),
}

# Candidate competitions that are NOT in the graph (no medal team of >= 2 kept
# users). They only feed history-based weights (contract section 4).
HIDDEN_COMPS = {
    "H1": (1500, ["text", "nlp", "health"]),
    "H2": (1000, ["tabular", "regression", "time series analysis"]),
    "H3": (700, ["image", "computer vision", "biology"]),
    "H4": (1100, ["tabular", "binary classification", "finance"]),
    "H5": (500, ["text", "nlp", "tensorflow", "sports"]),
}

# ---------------------------------------------------------------------------
# Users
# key: (userId, username, displayName, tier, compTier, country, registerDate, source)
# compTier None = no Competitions row in UserAchievements (medal totals stay 0)
# ---------------------------------------------------------------------------
USERS = {
    "alice":   ("k1001", "alicechen", "Alice Chen", "expert", "expert", "Canada", "2017-03-14", "kaggle"),
    "bob":     ("k1002", "bobsmith", "Bob Smith", "master", "expert", "", "2016-08-02", "kaggle"),
    "carol":   ("k1003", "carolwu", "Carol Wu, PhD", "novice", "novice", "", "2020-01-20", "kaggle"),
    "dave":    ("k1004", "davepatel", "Dave Patel", "master", "master", "India", "2015-05-30", "kaggle"),
    "erin":    ("k1005", "erinokafor", "Erin Okafor", "expert", "expert", "", "2018-11-11", "kaggle"),
    "frank":   ("k1006", "frankmuller", 'Frank "The Tank" Müller', "expert", "novice", "", "2019-02-05", "kaggle"),
    "grace":   ("k1007", "gracekim", "Grace Kim", "novice", "novice", "", "2023-06-17", "kaggle"),
    "heidi":   ("k1008", "heidilarsen", "Heidi Larsen", "expert", "expert", "", "2018-04-09", "kaggle"),
    "ivan":    ("k1009", "ivanpetrov", "Ivan Petrov", "novice", "novice", "", "2024-01-03", "kaggle"),
    "judy":    ("k1010", "judygarcia", "Judy García", "expert", "novice", "", "2019-09-22", "kaggle"),
    "mallory": ("k1011", "mallorystone", "Mallory Stone", "novice", "novice", "", "2021-07-07", "kaggle"),
    "niaj":    ("k1012", "niajsingh", "Niaj Singh", "novice", "novice", "", "2020-10-10", "kaggle"),
    "olivia":  ("k1013", "oliviabrown", "Olivia Brown", "novice", "novice", "", "2020-12-01", "kaggle"),
    "peggy":   ("k1014", "peggyhopper", "Peggy Hopper", "grandmaster", "grandmaster", "", "2012-02-29", "kaggle"),
    "trent":   ("k1015", "trentnguyen", "Trent Nguyen", "master", "expert", "", "2016-03-03", "kaggle"),
    "sybil":   ("k1016", "sybilrao", "Sybil Rao 🚀", "expert", "expert", "", "2019-05-15", "kaggle"),
    "victor":  ("k1017", "victorli", "李伟 (Victor Li)", "novice", "novice", "", "2022-08-08", "kaggle"),
    "walter":  ("k1018", "walterkaggle", "Walter (Kaggle Staff)", "staff", None, "", "2014-01-01", "kaggle"),
    "yolanda": ("k1019", "yolandaruiz", "Yolanda Ruiz", "expert", "novice", "", "2018-02-14", "kaggle"),
    "zara":    ("k1020", "zaraahmed", "Zara Ahmed", "novice", "novice", "", "2021-03-21", "kaggle"),
    "quentin": ("k1021", "quentinmoreau", "Quentin Moreau", "novice", "novice", "", "2021-04-01", "kaggle"),
    "rupert":  ("k1022", "rupertgray", "Rupert O'Neil Gray", "novice", "novice", "", "2021-04-02", "kaggle"),
    "uma":     ("k1023", "umasato", "Uma Sato", "expert", "expert", "", "2017-07-17", "kaggle"),
    "xavier":  ("k1024", "xavierdiaz", "Xavier Díaz", "novice", "novice", "", "2022-02-22", "kaggle"),
    "wendy":   ("k1025", "wendyclark", "Wendy Clark", "master", "master", "", "2015-10-31", "kaggle"),
    # App-registered users (no Kaggle history, no teams)
    "sam":     ("u5eed0000000000000000000000000001", "newbie_sam", "Sam (new here)", "", None, "", "2026-11-01", "app"),
    "lee":     ("u5eed0000000000000000000000000002", "lee_app", "Lee", "", None, "", "2026-11-15", "app"),
}

# Self-declared skills/interests for app users (weight 0.5, source 'self')
APP_SKILLS = {"sam": ["nlp", "text"], "lee": []}
APP_INTERESTS = {"sam": ["health"], "lee": []}

# ---------------------------------------------------------------------------
# Graph teams: key: (teamId, comp, teamName, medal, privateRank, members)
# ---------------------------------------------------------------------------
TEAMS = {
    "T1":  (90001, "C3", "Notes, Notes & More", "gold", 2, ["alice", "bob", "carol"]),
    "T2":  (90002, "C7", "Sentimental Value", "silver", 40, ["alice", "bob"]),
    "T3":  (90003, "C1", "Default Risk Takers", "gold", 4, ["dave", "frank"]),
    "T4":  (90004, "C4", "Watts Up", "silver", 25, ["dave", "frank", "grace"]),
    "T5":  (90005, "C2", "Eye See You", "bronze", 70, ["bob", "erin"]),
    "T6":  (90006, "C6", '"Cell" Shock', "gold", 3, ["erin", "heidi", "ivan"]),
    "T7":  (90007, "C2", "Fundus Fun", "silver", 30, ["heidi", "judy"]),
    "T8":  (90008, "C5", "Offside Trap", "bronze", 35, ["mallory", "niaj"]),
    "T9":  (90009, "C1", "Credit Where Due", "bronze", 110, ["niaj", "olivia"]),
    "T10": (90010, "C3", "Discharge Summary", "silver", 45, ["peggy", "trent"]),
    "T11": (90011, "C6", "🔬 Microscope Gang", "bronze", 28, ["peggy", "sybil"]),
    "T12": (90012, "C4", "李伟 & Peggy", "gold", 1, ["peggy", "victor"]),
    "T13": (90013, "C7", "Bull & Bear", "bronze", 88, ["walter", "yolanda"]),
    "T14": (90014, "C2", "Optic Nerds", "bronze", 75, ["zara", "quentin", "rupert"]),
    "T15": (90015, "C1", "Two Sigmoid", "silver", 40, ["uma", "xavier"]),
    "T16": (90016, "C7", "Alpha Seekers", "gold", 5, ["wendy", "trent"]),
}

# Extra history teams (ranked, not in the graph). result: gold/silver/bronze/top/plain
# top = no medal, rankPct <= 0.25 ; plain = no medal, otherwise
EXTRA_HISTORY = {
    "peggy":   [("H1", "gold"), ("H2", "gold"), ("H3", "silver"), ("H4", "gold"), ("H5", "gold")],
    "alice":   [("H1", "top"), ("H5", "plain")],
    "bob":     [("H3", "plain")],
    "dave":    [("H2", "bronze"), ("H4", "silver")],
    "erin":    [("H3", "top")],
    "grace":   [("H2", "plain")],
    "mallory": [("H1", "plain")],  # history alone must NOT create a HAS_SKILL pair
}

# FOLLOWS: (follower, followee, since)
FOLLOWS = [
    ("alice", "bob", "2021-02-01"), ("bob", "alice", "2021-02-03"),
    ("carol", "alice", "2023-05-10"), ("carol", "bob", "2023-05-10"),
    ("alice", "erin", "2022-09-09"),
    ("erin", "heidi", "2025-03-01"), ("heidi", "erin", "2025-03-02"),
    ("dave", "frank", "2021-06-06"), ("frank", "dave", "2021-06-07"),
    ("grace", "peggy", "2024-02-02"), ("sybil", "peggy", "2025-04-04"),
    ("trent", "peggy", "2023-01-15"), ("niaj", "peggy", "2022-03-03"),
    ("judy", "peggy", "2022-11-11"),
    ("judy", "heidi", "2022-07-01"),
    ("mallory", "niaj", "2022-05-05"),
    ("wendy", "alice", "2024-08-08"),
    ("sam", "alice", "2026-11-02"),
]

POINTS = {"gold": 3, "silver": 2, "bronze": 1, "top": 0.75, "plain": 0.25}


def write(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    uid = {k: v[0] for k, v in USERS.items()}
    comp_tags = {k: v[7] for k, v in COMPS.items()}
    comp_tags.update({k: v[1] for k, v in HIDDEN_COMPS.items()})

    # History per user: list of (comp_key, result)
    history = defaultdict(list)
    for t in TEAMS.values():
        for m in t[5]:
            history[m].append((t[1], t[3]))
    for u, extra in EXTRA_HISTORY.items():
        history[u].extend(extra)
    for u, h in history.items():
        comps = [c for c, _ in h]
        assert len(comps) == len(set(comps)), f"{u} has two teams in one competition"

    # Medal totals (UserAchievements-like); 0 when compTier is None
    medal_totals = {}
    for u, row in USERS.items():
        res = [r for _, r in history.get(u, [])]
        has_row = row[4] is not None
        medal_totals[u] = tuple(res.count(m) if has_row else 0 for m in ("gold", "silver", "bronze"))

    counts = {}
    counts["users"] = write("users.csv",
        ["userId", "username", "displayName", "tier", "country", "registerDate",
         "compTier", "golds", "silvers", "bronzes", "source"],
        [[r[0], r[1], r[2], r[3], r[5], r[6], r[4] or "", *medal_totals[u], r[7]]
         for u, r in USERS.items()])
    counts["skills"] = write("skills.csv", ["name", "category", "tagId"], SKILLS)
    counts["interests"] = write("interests.csv", ["name", "category", "tagId"], INTERESTS)
    counts["competitions"] = write("competitions.csv",
        ["competitionId", "slug", "title", "segment", "year", "maxTeamSize", "totalTeams"],
        [list(c[:7]) for c in COMPS.values()])

    teams_rows, member_rows = [], []
    for t in TEAMS.values():
        tid, ck, name, medal, rank, members = t
        total = COMPS[ck][6]
        assert len(members) >= 2 and len(members) <= COMPS[ck][5]
        teams_rows.append([tid, COMPS[ck][0], name, medal, rank, round(rank / total, 4), len(members)])
        member_rows += [[uid[m], tid] for m in members]
    counts["teams"] = write("teams.csv",
        ["teamId", "competitionId", "teamName", "medal", "privateRank", "rankPct", "teamSize"], teams_rows)
    counts["member_of"] = write("member_of.csv", ["userId", "teamId"], member_rows)

    counts["competition_skill"] = write("competition_skill.csv", ["competitionId", "skill"],
        [[c[0], tag] for c in COMPS.values() for tag in c[7] if tag in SKILL_NAMES])
    counts["competition_interest"] = write("competition_interest.csv", ["competitionId", "interest"],
        [[c[0], tag] for c in COMPS.values() for tag in c[7] if tag in INTEREST_NAMES])

    # Section 4: pairs from graph teams, weights from full history
    skill_rows, interest_rows = [], []
    for u in USERS:
        if USERS[u][7] == "app":
            skill_rows += [[uid[u], s, 0.5, 0, 0, "self"] for s in APP_SKILLS[u]]
            interest_rows += [[uid[u], i, 0.5, 0, "self"] for i in APP_INTERESTS[u]]
            continue
        graph_tags = sorted({tag for t in TEAMS.values() if u in t[5] for tag in COMPS[t[1]][7]})
        for tag in graph_tags:
            hist = [(c, r) for c, r in history[u] if tag in comp_tags[c]]
            n = len(hist)
            if tag in SKILL_NAMES:
                pts = sum(POINTS[r] for _, r in hist)
                medals = sum(r in ("gold", "silver", "bronze") for _, r in hist)
                skill_rows.append([uid[u], tag, round(1 - math.exp(-pts / 3), 4), n, medals, "kaggle"])
            elif tag in INTEREST_NAMES:
                interest_rows.append([uid[u], tag, round(1 - math.exp(-n / 2), 4), n, "kaggle"])
    counts["user_skill"] = write("user_skill.csv",
        ["userId", "skill", "weight", "competitions", "medals", "source"], skill_rows)
    counts["user_interest"] = write("user_interest.csv",
        ["userId", "interest", "weight", "competitions", "source"], interest_rows)

    counts["follows"] = write("follows.csv", ["followerId", "followeeId", "since"],
        [[uid[a], uid[b], d] for a, b, d in FOLLOWS])

    # Derived WORKED_WITH (not a CSV; computed by the loader) - for the README
    ww = defaultdict(int)
    for t in TEAMS.values():
        for a, b in combinations(sorted(t[5], key=lambda m: uid[m]), 2):
            ww[(a, b)] += 1

    nodes = sum(counts[k] for k in ("users", "skills", "interests", "competitions", "teams"))
    rels = (counts["member_of"] + counts["teams"] + counts["competition_skill"]
            + counts["competition_interest"] + counts["user_skill"] + counts["user_interest"]
            + counts["follows"] + len(ww))
    print("Wrote", OUT)
    for k, v in counts.items():
        print(f"  {k:22s} {v}")
    print(f"  {'PARTICIPATED_IN':22s} {counts['teams']}")
    print(f"  {'WORKED_WITH (derived)':22s} {len(ww)}")
    print(f"  NODES {nodes}   RELATIONSHIPS {rels}")
    print("\nWORKED_WITH pairs:")
    for (a, b), n in sorted(ww.items(), key=lambda x: (uid[x[0][0]], uid[x[0][1]])):
        print(f"  {USERS[a][1]} - {USERS[b][1]}  times={n}")
    no_skill = [USERS[u][1] for u in USERS if not any(r[0] == uid[u] for r in skill_rows)]
    no_int = [USERS[u][1] for u in USERS if not any(r[0] == uid[u] for r in interest_rows)]
    print("\nNo HAS_SKILL:", ", ".join(no_skill))
    print("No INTERESTED_IN:", ", ".join(no_int))


if __name__ == "__main__":
    main()
