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

WEIGHTS = {
    "skills": 3.0,
    "interests": 1.5,
    "mutual": 1.0,         # per mutual connection
    "worked_with": 2.0,    # flat bonus if you've been teammates before
}

# Candidate generation: anyone within reach of a shared skill/interest or two
# hops in the social graph. Keeps the per-candidate work off the whole graph.
_CANDIDATES_ALL = """
CALL (me) {
  MATCH (me)-[:HAS_SKILL|INTERESTED_IN]->()<-[:HAS_SKILL|INTERESTED_IN]-(c:User)
  RETURN c
  UNION
  MATCH (me)-[:FOLLOWS|WORKED_WITH]-(:User)-[:FOLLOWS|WORKED_WITH]-(c:User)
  RETURN c
  UNION
  MATCH (me)-[:WORKED_WITH]-(c:User)
  RETURN c
}
WITH me, totalUsers, c
WHERE c <> me AND NOT (me)-[:FOLLOWS]->(c)
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
       coalesce(w.times, 0) AS workedTogetherTimes,
       COLLECT {
         MATCH (me)-[r1:HAS_SKILL]->(s:Skill)<-[r2:HAS_SKILL]-(c)
         RETURN {name: s.name, mine: r1.weight, theirs: r2.weight,
                 holders: COUNT { (s)<-[:HAS_SKILL]-(:User) }}
       } AS sharedSkills,
       COLLECT {
         MATCH (me)-[r1:INTERESTED_IN]->(i:Interest)<-[r2:INTERESTED_IN]-(c)
         RETURN {name: i.name, mine: r1.weight, theirs: r2.weight,
                 holders: COUNT { (i)<-[:INTERESTED_IN]-(:User) }}
       } AS sharedInterests,
       COLLECT {
         MATCH (me)-[:FOLLOWS|WORKED_WITH]-(m:User)-[:FOLLOWS|WORKED_WITH]-(c)
         WHERE m <> me AND m <> c
         RETURN DISTINCT m.displayName
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


def _names(items, limit=4):
    names = [x if isinstance(x, str) else x["name"] for x in items]
    shown = ", ".join(names[:limit])
    return shown + (f" +{len(names) - limit} more" if len(names) > limit else "")


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _score(row):
    total = row["totalUsers"]
    # Strongest shared tags first, so explanations lead with the best evidence.
    for key in ("sharedSkills", "sharedInterests"):
        row[key].sort(key=lambda t: -min(t["mine"], t["theirs"]) * _rarity(t["holders"], total))
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
        reasons.append(f"{_plural(len(row['mutualConnections']), 'mutual connection')}: {_names(row['mutualConnections'], 3)}")

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
    rows = db.execute_query(_query(_CANDIDATES_ALL), {"userId": user_id})
    recs = [_score(r) for r in rows]
    recs = [r for r in recs if r["score"] > 0]
    recs.sort(key=lambda r: (-r["score"], r["username"]))
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
