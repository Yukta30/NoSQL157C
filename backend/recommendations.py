"""Explainable "people you may want to follow" recommendations.

Pure graph signals, no ML. Cypher gathers the raw evidence per candidate;
Python turns it into a score plus human-readable reasons, so the weights below
can be tuned without touching the query.

Signals (all computed at query time, see docs/csv_contract.md section 4):
  shared skills     sum over shared skills of min(myWeight, theirWeight) * rarity
  shared interests  same, for interests
  mutual network    people connected (FOLLOWS or WORKED_WITH) to both of you
  worked together   you were on a team together before (WORKED_WITH)

rarity = ln(1 + N/holders) / ln(1 + N), in (0, 1]. A skill only one user has
counts 1.0; a skill everyone has counts ~0.2. This keeps very common tags
(e.g. "tabular") from dominating.

Users the current user already follows are never recommended.
"""

import math

from backend.db import db

# People's names can contain commas ("Carol Wu, PhD"), so lists of people
# use a separator that can't be confused with one.
PEOPLE_SEP = " · "

WEIGHTS = {
    "skills": 3.0,
    "interests": 1.5,
    "mutual": 1.0,         # per mutual connection
    "worked_with": 2.0,    # flat bonus if you've been teammates before
}

# Candidate ranking, in one pass: every person reachable through a shared
# skill/interest or two hops in the social graph gets the same score _score()
# computes, summed per signal. Only the top few then get the detailed evidence
# query, so this stays fast on the full Meta Kaggle graph (30k users, where
# common skills like "tabular" have thousands of holders).
_RANK_CANDIDATES = """
MATCH (me:User {userId: $userId})
WITH me, COUNT { (:User) } AS totalUsers
CALL (me, totalUsers) {
  MATCH (me)-[r1:HAS_SKILL]->(s:Skill)
  WITH me, totalUsers, r1, s, COUNT { (s)<-[:HAS_SKILL]-() } AS holders
  MATCH (s)<-[r2:HAS_SKILL]-(c:User)
  WHERE c <> me
  RETURN c, $wSkills * CASE WHEN r1.weight < r2.weight THEN r1.weight ELSE r2.weight END
            * log(1.0 + toFloat(totalUsers) / holders) / log(1.0 + totalUsers) AS points
  UNION ALL
  MATCH (me)-[r1:INTERESTED_IN]->(i:Interest)
  WITH me, totalUsers, r1, i, COUNT { (i)<-[:INTERESTED_IN]-() } AS holders
  MATCH (i)<-[r2:INTERESTED_IN]-(c:User)
  WHERE c <> me
  RETURN c, $wInterests * CASE WHEN r1.weight < r2.weight THEN r1.weight ELSE r2.weight END
            * log(1.0 + toFloat(totalUsers) / holders) / log(1.0 + totalUsers) AS points
  UNION ALL
  MATCH (me)-[:FOLLOWS|WORKED_WITH]-(m:User)-[:FOLLOWS|WORKED_WITH]-(c:User)
  WHERE m <> me AND c <> me AND c <> m
  WITH DISTINCT c, m
  RETURN c, $wMutual AS points
  UNION ALL
  MATCH (me)-[:WORKED_WITH]-(c:User)
  RETURN c, $wWorked AS points
}
WITH me, c, sum(points) AS score
WHERE score > 0 AND NOT (me)-[:FOLLOWS]->(c)
RETURN c.userId AS userId
ORDER BY score DESC, COUNT { (c)<-[:FOLLOWS]-() } DESC, c.username
LIMIT $topK
"""

_CANDIDATES_TOP = """
UNWIND $candidateIds AS candidateId
MATCH (c:User {userId: candidateId})
WITH me, totalUsers, c
"""

_CANDIDATE_ONE = """
MATCH (c:User {userId: $candidateId})
WITH me, totalUsers, c
WHERE c <> me
"""

_EVIDENCE = """
OPTIONAL MATCH (me)-[w:WORKED_WITH]-(c)
RETURN c.userId AS userId, c.username AS username, c.displayName AS displayName,
       c.tier AS tier, c.source AS source, totalUsers,
       COUNT { (c)<-[:FOLLOWS]-() } AS followers,
       coalesce(w.times, 0) AS workedTogetherTimes,
       COLLECT {
         MATCH (me)-[r1:HAS_SKILL]->(s:Skill)<-[r2:HAS_SKILL]-(c)
         RETURN {name: s.name, mine: r1.weight, theirs: r2.weight,
                 holders: COUNT { (s)<-[:HAS_SKILL]-() }}
       } AS sharedSkills,
       COLLECT {
         MATCH (me)-[r1:INTERESTED_IN]->(i:Interest)<-[r2:INTERESTED_IN]-(c)
         RETURN {name: i.name, mine: r1.weight, theirs: r2.weight,
                 holders: COUNT { (i)<-[:INTERESTED_IN]-() }}
       } AS sharedInterests,
       COLLECT {
         MATCH (me)-[:FOLLOWS|WORKED_WITH]-(m:User)-[:FOLLOWS|WORKED_WITH]-(c)
         WHERE m <> me AND m <> c
         WITH DISTINCT m
         RETURN coalesce(m.displayName, m.username)
       } AS mutualConnections
"""


def _query(candidate_clause):
    return (
        "MATCH (me:User {userId: $userId})\n"
        "WITH me, COUNT { (:User) } AS totalUsers\n"
        + candidate_clause
        + _EVIDENCE
    )


def _rarity(holders, total_users):
    if total_users <= 1 or not holders:
        return 1.0
    return math.log(1 + total_users / holders) / math.log(1 + total_users)


def _overlap_score(shared, total_users):
    return sum(min(t["mine"], t["theirs"]) * _rarity(t["holders"], total_users) for t in shared)


def _names(items, limit=4, sep=", "):
    names = [x if isinstance(x, str) else x["name"] for x in items]
    shown = sep.join(names[:limit])
    return shown + (f" +{len(names) - limit} more" if len(names) > limit else "")


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _score(row):
    total = row["totalUsers"]
    # Strongest shared tags first, so explanations lead with the best evidence.
    for key in ("sharedSkills", "sharedInterests"):
        # Name breaks ties so the order never depends on how Neo4j returns rows.
        row[key].sort(key=lambda t: (-round(min(t["mine"], t["theirs"]) * _rarity(t["holders"], total), 9),
                                     t["name"]))
    row["mutualConnections"].sort()

    breakdown = {
        "skills": WEIGHTS["skills"] * _overlap_score(row["sharedSkills"], total),
        "interests": WEIGHTS["interests"] * _overlap_score(row["sharedInterests"], total),
        "mutual": WEIGHTS["mutual"] * len(row["mutualConnections"]),
        "worked_with": WEIGHTS["worked_with"] if row["workedTogetherTimes"] else 0.0,
    }
    breakdown = {k: round(v, 3) for k, v in breakdown.items()}

    reasons = []
    if row["workedTogetherTimes"]:
        reasons.append(f"Worked together on {_plural(row['workedTogetherTimes'], 'team')}")
    if row["sharedSkills"]:
        reasons.append(f"{_plural(len(row['sharedSkills']), 'shared skill')}: {_names(row['sharedSkills'])}")
    if row["sharedInterests"]:
        reasons.append(f"{_plural(len(row['sharedInterests']), 'shared interest')}: {_names(row['sharedInterests'])}")
    if row["mutualConnections"]:
        reasons.append(f"{_plural(len(row['mutualConnections']), 'mutual connection')}: {_names(row['mutualConnections'], 3, sep=PEOPLE_SEP)}")

    return {
        "userId": row["userId"],
        "username": row["username"],
        "displayName": row["displayName"],
        "tier": row["tier"],
        "source": row["source"],
        "score": round(sum(breakdown.values()), 3),
        "breakdown": breakdown,
        "reasons": reasons,
        "sharedSkills": [s["name"] for s in row["sharedSkills"]],
        "sharedInterests": [i["name"] for i in row["sharedInterests"]],
        "mutualConnections": row["mutualConnections"],
        "workedTogetherTimes": row["workedTogetherTimes"],
        "followers": row["followers"],
    }


def _popular_users(user_id, limit):
    """Cold-start fallback for users with no skills, interests or connections."""
    rows = db.execute_query(
        """
        MATCH (me:User {userId: $userId}), (c:User)
        WHERE c <> me AND NOT (me)-[:FOLLOWS]->(c)
        WITH c, COUNT { (c)<-[:FOLLOWS]-() } AS followers,
             coalesce(c.golds, 0) * 3 + coalesce(c.silvers, 0) * 2 + coalesce(c.bronzes, 0) AS medalPoints
        RETURN c.userId AS userId, c.username AS username, c.displayName AS displayName,
               c.tier AS tier, c.source AS source, followers, medalPoints
        ORDER BY followers DESC, medalPoints DESC, c.username
        LIMIT $limit
        """,
        {"userId": user_id, "limit": limit},
    )
    return [
        {
            **{k: r[k] for k in ("userId", "username", "displayName", "tier", "source")},
            "score": 0.0,
            "breakdown": {k: 0.0 for k in WEIGHTS},
            "reasons": [f"Popular in the community: {_plural(r['followers'], 'follower')}"],
            "sharedSkills": [],
            "sharedInterests": [],
            "mutualConnections": [],
            "workedTogetherTimes": 0,
            "fallback": True,
        }
        for r in rows
    ]


def recommend_users(user_id, limit=10, fallback=True):
    """Ranked, explained recommendations of users to follow.

    Each result has score, breakdown (per signal), and reasons (strings ready
    for the UI). If the user has no graph signal at all and fallback=True,
    returns popular users flagged with "fallback": True.
    """
    params = {"userId": user_id, "wSkills": WEIGHTS["skills"], "wInterests": WEIGHTS["interests"],
              "wMutual": WEIGHTS["mutual"], "wWorked": WEIGHTS["worked_with"]}
    # A few spare candidates absorb float rounding between Cypher and _score().
    top = db.execute_query(_RANK_CANDIDATES, {**params, "topK": max(limit * 3, 30)})
    ids = [r["userId"] for r in top]
    rows = db.execute_query(_query(_CANDIDATES_TOP), {"userId": user_id, "candidateIds": ids}) if ids else []
    recs = [_score(r) for r in rows]
    recs = [r for r in recs if r["score"] > 0]
    # Ties (common for new users, whose self-declared skills all weigh 0.5)
    # go to the better-known person.
    recs.sort(key=lambda r: (-r["score"], -r["followers"], r["username"]))
    for r in recs:
        r["fallback"] = False

    if not recs and fallback:
        return _popular_users(user_id, limit)
    return recs[:limit]


def explain_recommendation(user_id, other_user_id):
    """Score and reasons for one specific pair (e.g. on a profile page).
    Returns None if either user doesn't exist."""
    rows = db.execute_query(
        _query(_CANDIDATE_ONE), {"userId": user_id, "candidateId": other_user_id}
    )
    return _score(rows[0]) if rows else None
