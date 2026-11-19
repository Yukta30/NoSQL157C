"""Build My Team: choose a set of people who together cover a project's skills.

This is different from user recommendations. Recommendations ask "who is
similar/connected to me?"; the team builder asks "which combination of people
best covers what this project needs?".

Algorithm (greedy weighted set cover):
  1. Cypher pulls every user holding at least one required skill, with their
     HAS_SKILL weights, plus FOLLOWS/WORKED_WITH links among those candidates.
  2. The team's coverage of a skill = the best weight any member has in it.
  3. Repeatedly add the candidate with the largest marginal gain:
         coverage gain  = sum over skills of max(0, theirWeight - teamBest)
       + chemistry bonus (worked with / follows someone already on the team)
     Only candidates who improve coverage by at least MIN_GAIN are eligible,
     so chemistry can break ties but never adds someone who brings no needed
     (or only a negligibly better) skill.
  4. Stop at team_size, or earlier if nobody can improve coverage further.

Greedy set cover is a standard approximation (the exact problem is NP-hard)
and every pick can be explained by the gain that caused it.
"""

from backend.db import db

WORKED_WITH_BONUS = 0.25  # per current team member they've been teammates with
FOLLOWS_BONUS = 0.10      # per current team member they follow / are followed by
MIN_GAIN = 0.05           # ignore candidates who'd barely improve coverage
_EPS = 1e-9


def normalize_skills(required_skills):
    """Lowercase, strip, de-duplicate (keeping order). Skill names are lowercase tags."""
    seen, out = set(), []
    for s in required_skills or []:
        name = (s or "").strip().lower()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _known_skills(skills):
    rows = db.execute_query(
        "MATCH (s:Skill) WHERE s.name IN $skills RETURN s.name AS name", {"skills": skills}
    )
    return {r["name"] for r in rows}


def _fetch_candidates(skills, exclude, include_ids, pool_size):
    """Users with >=1 required skill, plus anyone in include_ids (e.g. you)."""
    return db.execute_query(
        """
        MATCH (u:User)
        WHERE (u.userId IN $includeIds OR EXISTS {
                 (u)-[:HAS_SKILL]->(s:Skill) WHERE s.name IN $skills })
          AND NOT u.userId IN $exclude
        WITH u, COLLECT {
               MATCH (u)-[r:HAS_SKILL]->(s:Skill) WHERE s.name IN $skills
               RETURN {skill: s.name, weight: r.weight, medals: r.medals,
                       competitions: r.competitions, source: r.source}
             } AS skills
        WITH u, skills, reduce(t = 0.0, x IN skills | t + x.weight) AS totalWeight
        RETURN u.userId AS userId, u.username AS username,
               u.displayName AS displayName, u.tier AS tier, u.source AS source,
               skills, totalWeight
        ORDER BY (u.userId IN $includeIds) DESC, totalWeight DESC, u.username
        LIMIT $poolSize
        """,
        {"skills": skills, "exclude": list(exclude), "includeIds": list(include_ids),
         "poolSize": pool_size},
    )


def _fetch_links(user_ids):
    """FOLLOWS and WORKED_WITH links among the given users."""
    rows = db.execute_query(
        """
        MATCH (a:User)-[r:FOLLOWS|WORKED_WITH]-(b:User)
        WHERE a.userId IN $ids AND b.userId IN $ids AND a.userId < b.userId
        RETURN a.userId AS a, b.userId AS b, type(r) AS type, r.times AS times
        """,
        {"ids": list(user_ids)},
    )
    worked, follows = {}, set()
    for r in rows:
        pair = frozenset((r["a"], r["b"]))
        if r["type"] == "WORKED_WITH":
            worked[pair] = r["times"] or 1
        else:
            follows.add(pair)
    return worked, follows


def _gain(cand, best, team_ids, worked, follows):
    coverage = sum(max(0.0, w - best[s]) for s, w in cand["weights"].items())
    worked_mates = [m for m in team_ids if frozenset((cand["userId"], m)) in worked]
    follow_mates = [m for m in team_ids if frozenset((cand["userId"], m)) in follows]
    bonus = WORKED_WITH_BONUS * len(worked_mates) + FOLLOWS_BONUS * len(follow_mates)
    return coverage, bonus, worked_mates, follow_mates


def build_team(required_skills, team_size=3, current_user_id=None, include_me=True,
               exclude_user_ids=None, pool_size=200, min_gain=MIN_GAIN):
    """Recommend a team that covers the required skills.

    required_skills : list of skill names, e.g. ["nlp", "computer vision", "tensorflow"]
    team_size       : max number of members, including you if include_me
    current_user_id : the person building the team. If include_me, they are the
                      first member and their skills count toward coverage; their
                      connections also earn chemistry bonuses.
    exclude_user_ids: people who should not be picked.
    min_gain        : minimum coverage improvement for someone to be added.

    Returns a dict with members (in pick order, with reasons), per-skill
    coverage, missing/unknown skills, coverageScore (0-1) and team links.
    """
    if team_size < 1:
        raise ValueError("team_size must be at least 1.")
    requested = normalize_skills(required_skills)
    if not requested:
        raise ValueError("Give at least one required skill.")

    known = _known_skills(requested)
    unknown = [s for s in requested if s not in known]
    skills = [s for s in requested if s in known]

    exclude = set(exclude_user_ids or [])
    include_ids = {current_user_id} if (current_user_id and include_me) else set()
    if not include_me and current_user_id:
        exclude.add(current_user_id)

    rows = _fetch_candidates(skills, exclude, include_ids, pool_size) if skills else []
    if include_ids and not any(r["userId"] == current_user_id for r in rows):
        raise ValueError(f"Unknown user: {current_user_id}")

    candidates = {}
    for r in rows:
        r["weights"] = {x["skill"]: x["weight"] for x in r["skills"]}
        r["medals"] = sum(x["medals"] or 0 for x in r["skills"])
        candidates[r["userId"]] = r

    link_ids = set(candidates)
    worked, follows = _fetch_links(link_ids) if link_ids else ({}, set())

    best = {s: 0.0 for s in skills}
    best_by = {s: None for s in skills}
    team = []

    def add(cand, coverage, bonus, worked_mates, follow_mates, is_you=False):
        improved = [s for s, w in cand["weights"].items() if w > best[s] + _EPS]
        for s in improved:
            best[s] = cand["weights"][s]
            best_by[s] = cand["userId"]
        name = lambda uid: candidates[uid]["displayName"]
        reasons = []
        if is_you:
            reasons.append("You (team owner)")
        if improved:
            reasons.append("Adds " + ", ".join(f"{s} ({cand['weights'][s]:.2f})" for s in improved))
        if worked_mates:
            reasons.append("Worked with " + ", ".join(name(m) for m in worked_mates))
        if follow_mates:
            reasons.append("Connected to " + ", ".join(name(m) for m in follow_mates))
        team.append({
            "userId": cand["userId"], "username": cand["username"],
            "displayName": cand["displayName"], "tier": cand["tier"],
            "source": cand["source"], "isYou": is_you,
            "skills": [{k: x[k] for k in ("skill", "weight", "medals", "competitions", "source")}
                       for x in sorted(cand["skills"], key=lambda x: -x["weight"])],
            "coverageGain": round(coverage, 4), "chemistryBonus": round(bonus, 4),
            "reasons": reasons,
        })

    if include_ids:
        me = candidates[current_user_id]
        add(me, sum(me["weights"].values()), 0.0, [], [], is_you=True)

    while len(team) < team_size:
        team_ids = [m["userId"] for m in team]
        best_pick, best_key = None, None
        for uid, cand in candidates.items():
            if uid in team_ids:
                continue
            coverage, bonus, wm, fm = _gain(cand, best, team_ids, worked, follows)
            if coverage <= _EPS or coverage < min_gain - _EPS:
                continue
            key = (coverage + bonus, cand["medals"], cand["totalWeight"])
            # Deterministic tie-break on username (alphabetical wins).
            if best_key is None or key > best_key or (key == best_key and cand["username"] < best_pick[0]["username"]):
                best_pick, best_key = (cand, coverage, bonus, wm, fm), key
        if best_pick is None:
            break
        add(*best_pick)

    members = {m["userId"]: m for m in team}
    coverage = [
        {"skill": s, "weight": round(best[s], 4),
         "coveredBy": best_by[s], "coveredByName": members[best_by[s]]["displayName"] if best_by[s] else None}
        for s in skills
    ]
    missing = [s for s in skills if best_by[s] is None]

    team_links = [
        {"a": a, "b": b, "type": "WORKED_WITH", "times": t}
        for pair, t in worked.items() if pair <= members.keys()
        for a, b in [sorted(pair)]
    ] + [
        {"a": a, "b": b, "type": "FOLLOWS", "times": None}
        for pair in follows if pair <= members.keys()
        for a, b in [sorted(pair)]
    ]

    if not skills:
        note = "None of the requested skills exist in the skill vocabulary."
    elif len(team) < team_size and not missing:
        note = f"All required skills are covered with {len(team)} member(s); more people wouldn't add coverage."
    elif missing:
        note = "Nobody in the graph has: " + ", ".join(missing)
    else:
        note = None

    return {
        "requiredSkills": requested,
        "unknownSkills": unknown,
        "teamSize": team_size,
        "members": team,
        "coverage": coverage,
        "missingSkills": missing,
        "coverageScore": round(sum(best.values()) / len(skills), 4) if skills else 0.0,
        "links": sorted(team_links, key=lambda l: (l["type"], l["a"], l["b"])),
        "note": note,
    }


def rank_candidates(required_skills, limit=10, exclude_user_ids=None):
    """Individually best people for these skills (no team optimisation).

    Useful next to build_team in the UI to show why complementary selection
    differs from "just take the top N".
    """
    skills = [s for s in normalize_skills(required_skills)]
    if not skills:
        return []
    rows = _fetch_candidates(skills, set(exclude_user_ids or []), set(), limit)
    return [
        {"userId": r["userId"], "username": r["username"], "displayName": r["displayName"],
         "tier": r["tier"], "totalWeight": round(r["totalWeight"], 4),
         "skillsMatched": len(r["skills"]), "skillsRequired": len(skills),
         "skills": sorted(r["skills"], key=lambda x: -x["weight"])}
        for r in rows
    ]
