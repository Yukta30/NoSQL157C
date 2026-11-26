"""User lookups: search, profiles, skills, interests, team history.

Every function returns plain dicts/lists (no Neo4j objects), so the frontend
never needs to know Cypher. Property names follow docs/csv_contract.md.
"""

import re

from backend.db import db

USER_FIELDS = """
    userId: u.userId,
    username: u.username,
    displayName: u.displayName,
    tier: u.tier,
    compTier: u.compTier,
    country: u.country,
    registerDate: u.registerDate,
    golds: coalesce(u.golds, 0),
    silvers: coalesce(u.silvers, 0),
    bronzes: coalesce(u.bronzes, 0),
    source: u.source,
    email: u.email,
    bio: u.bio
"""

# Characters with special meaning in Lucene query syntax (used by fulltext indexes).
_LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def _fulltext_query(search_term):
    """Turn free text like 'alice ch' into a Lucene prefix query 'alice* AND ch*'."""
    words = [_LUCENE_SPECIAL.sub(r"\\\1", w) for w in search_term.lower().split()]
    return " AND ".join(f"{w}*" for w in words if w)


def search_users(search_term, limit=20):
    """UC-11: search users by username or display name (prefix match per word).

    Uses the `user_search` fulltext index from database/schema.cypher.
    """
    if not search_term or not search_term.strip():
        return []

    query = _fulltext_query(search_term)
    if not query:
        return []

    return db.execute_query(
        """
        CALL db.index.fulltext.queryNodes('user_search', $query)
        YIELD node AS u, score
        RETURN u.userId AS userId, u.username AS username,
               u.displayName AS displayName, u.tier AS tier,
               u.source AS source, score
        ORDER BY score DESC, u.username
        LIMIT $limit
        """,
        {"query": query, "limit": limit},
    )


def user_exists(user_id):
    rows = db.execute_query(
        "MATCH (u:User {userId: $userId}) RETURN count(u) > 0 AS exists",
        {"userId": user_id},
    )
    return rows[0]["exists"]


def get_user(user_id):
    """Basic user properties, or None if the user doesn't exist."""
    rows = db.execute_query(
        f"MATCH (u:User {{userId: $userId}}) RETURN {{ {USER_FIELDS} }} AS user",
        {"userId": user_id},
    )
    return rows[0]["user"] if rows else None


def get_user_by_username(username):
    rows = db.execute_query(
        f"MATCH (u:User {{username: $username}}) RETURN {{ {USER_FIELDS} }} AS user",
        {"username": username},
    )
    return rows[0]["user"] if rows else None


def get_user_skills(user_id):
    """Skills strongest first. Weight saturates for top users, so medals and
    competitions break ties (csv_contract.md section 4)."""
    return db.execute_query(
        """
        MATCH (:User {userId: $userId})-[r:HAS_SKILL]->(s:Skill)
        RETURN s.name AS skill, s.category AS category,
               r.weight AS weight, r.competitions AS competitions,
               r.medals AS medals, r.source AS source
        ORDER BY r.weight DESC, r.medals DESC, r.competitions DESC, s.name
        """,
        {"userId": user_id},
    )


def get_user_interests(user_id):
    return db.execute_query(
        """
        MATCH (:User {userId: $userId})-[r:INTERESTED_IN]->(i:Interest)
        RETURN i.name AS interest, i.category AS category,
               r.weight AS weight, r.competitions AS competitions,
               r.source AS source
        ORDER BY r.weight DESC, r.competitions DESC, i.name
        """,
        {"userId": user_id},
    )


def get_user_teams(user_id):
    """Competition/team history, newest first, with teammates."""
    return db.execute_query(
        """
        MATCH (u:User {userId: $userId})-[:MEMBER_OF]->(t:Team)-[:PARTICIPATED_IN]->(c:Competition)
        OPTIONAL MATCH (mate:User)-[:MEMBER_OF]->(t)
        WHERE mate <> u
        WITH t, c, mate ORDER BY mate.username
        RETURN t.teamId AS teamId, t.teamName AS teamName, t.medal AS medal,
               t.privateRank AS privateRank, t.rankPct AS rankPct, t.teamSize AS teamSize,
               c.competitionId AS competitionId, c.title AS competition,
               c.slug AS competitionSlug, c.year AS year,
               [m IN collect(mate) | {userId: m.userId, username: m.username,
                                      displayName: m.displayName}] AS teammates
        ORDER BY year DESC, privateRank
        """,
        {"userId": user_id},
    )


def get_social_counts(user_id):
    rows = db.execute_query(
        """
        MATCH (u:User {userId: $userId})
        RETURN COUNT { (u)<-[:FOLLOWS]-() } AS followers,
               COUNT { (u)-[:FOLLOWS]->() } AS following,
               COUNT { (u)-[:WORKED_WITH]-() } AS collaborators
        """,
        {"userId": user_id},
    )
    return rows[0] if rows else {"followers": 0, "following": 0, "collaborators": 0}


def get_user_profile(user_id):
    """Everything the profile page needs, or None if the user doesn't exist.

    App-registered users have no teams and may have no skills/interests;
    those come back as empty lists.
    """
    user = get_user(user_id)
    if user is None:
        return None

    return {
        **user,
        "skills": get_user_skills(user_id),
        "interests": get_user_interests(user_id),
        "teams": get_user_teams(user_id),
        **get_social_counts(user_id),
    }


def list_skills():
    """Full skill vocabulary (for pickers and the team builder)."""
    return db.execute_query(
        "MATCH (s:Skill) RETURN s.name AS name, s.category AS category ORDER BY s.category, s.name"
    )


def list_interests():
    return db.execute_query(
        "MATCH (i:Interest) RETURN i.name AS name, i.category AS category ORDER BY i.name"
    )


def get_graph_stats():
    """Headline numbers for the login screen (count-store lookups, so cheap)."""
    rows = db.execute_query(
        """
        RETURN COUNT { (:User) } AS users,
               COUNT { (:Team) } AS teams,
               COUNT { (:Competition) } AS competitions,
               COUNT { ()-[:FOLLOWS]->() } AS follows
        """
    )
    return rows[0]


def count_users():
    return db.execute_query("RETURN COUNT { (:User) } AS n")[0]["n"]


def list_all_users(skip=0, limit=25):
    """UC-10: every user (including you and people you follow), by username, one page at a time."""
    return db.execute_query(
        """
        MATCH (u:User)
        WITH u ORDER BY toLower(u.username)
        SKIP $skip LIMIT $limit
        RETURN u.userId AS userId, u.username AS username, u.displayName AS displayName,
               u.tier AS tier, u.source AS source, COUNT { (u)<-[:FOLLOWS]-() } AS followers
        """,
        {"skip": int(skip), "limit": int(limit)},
    )


def user_page_of(username, page_size=25):
    """Which page of list_all_users() a username is on (0-based), or None."""
    rows = db.execute_query(
        """
        MATCH (me:User {username: $username})
        RETURN COUNT { MATCH (u:User) WHERE toLower(u.username) < toLower(me.username) } AS before
        """,
        {"username": username},
    )
    return rows[0]["before"] // page_size if rows else None
