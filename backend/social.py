"""Social graph: following, followers, connection status.

(User)-[:FOLLOWS {since: date}]->(User) is directed.
(User)-[:WORKED_WITH {times}]-(User) is undirected (derived from shared teams).
"""

from backend.db import db

_USER_SUMMARY = "userId: {v}.userId, username: {v}.username, displayName: {v}.displayName, tier: {v}.tier"


def _summary(var):
    return "{" + _USER_SUMMARY.format(v=var) + "}"


def follow_user(current_user_id, target_user_id):
    """Make current user follow target. Idempotent.

    Returns True if a new follow was created, False if it already existed.
    Raises ValueError for self-follows or unknown users.
    """
    if current_user_id == target_user_id:
        raise ValueError("Users cannot follow themselves.")

    rows = db.execute_query(
        """
        MATCH (a:User {userId: $currentId}), (b:User {userId: $targetId})
        OPTIONAL MATCH (a)-[existing:FOLLOWS]->(b)
        WITH a, b, existing IS NOT NULL AS alreadyFollowing
        MERGE (a)-[f:FOLLOWS]->(b)
        ON CREATE SET f.since = date()
        RETURN NOT alreadyFollowing AS created
        """,
        {"currentId": current_user_id, "targetId": target_user_id},
        write=True,
    )
    if not rows:
        raise ValueError(f"Unknown user: {current_user_id} or {target_user_id}")
    return rows[0]["created"]


def unfollow_user(current_user_id, target_user_id):
    """Remove the follow. Returns True if one was deleted, False if none existed."""
    rows = db.execute_query(
        """
        MATCH (:User {userId: $currentId})-[f:FOLLOWS]->(:User {userId: $targetId})
        DELETE f
        RETURN count(*) AS deleted
        """,
        {"currentId": current_user_id, "targetId": target_user_id},
        write=True,
    )
    return bool(rows and rows[0]["deleted"])


def is_following(current_user_id, target_user_id):
    rows = db.execute_query(
        """
        RETURN EXISTS {
          (:User {userId: $currentId})-[:FOLLOWS]->(:User {userId: $targetId})
        } AS following
        """,
        {"currentId": current_user_id, "targetId": target_user_id},
    )
    return rows[0]["following"]


def get_following(user_id):
    """Users this user follows, most recent first."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $userId}})-[f:FOLLOWS]->(other:User)
        RETURN {_summary('other')} AS user, f.since AS since
        ORDER BY f.since DESC, other.username
        """,
        {"userId": user_id},
    )


def get_followers(user_id):
    """Users following this user, most recent first."""
    return db.execute_query(
        f"""
        MATCH (other:User)-[f:FOLLOWS]->(:User {{userId: $userId}})
        RETURN {_summary('other')} AS user, f.since AS since
        ORDER BY f.since DESC, other.username
        """,
        {"userId": user_id},
    )


def get_collaborators(user_id):
    """People this user has shared a team with, most shared teams first."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $userId}})-[w:WORKED_WITH]-(other:User)
        RETURN {_summary('other')} AS user, w.times AS times
        ORDER BY w.times DESC, other.username
        """,
        {"userId": user_id},
    )


def get_mutual_follows(user_id):
    """Users who follow this user and are followed back."""
    return db.execute_query(
        f"""
        MATCH (u:User {{userId: $userId}})-[:FOLLOWS]->(other:User)-[:FOLLOWS]->(u)
        RETURN {_summary('other')} AS user
        ORDER BY other.username
        """,
        {"userId": user_id},
    )


def get_connection_status(current_user_id, target_user_id):
    """How two users are connected, for a profile page header/buttons.

    Returns None if either user doesn't exist.
    """
    rows = db.execute_query(
        """
        MATCH (a:User {userId: $currentId}), (b:User {userId: $targetId})
        OPTIONAL MATCH (a)-[w:WORKED_WITH]-(b)
        RETURN EXISTS { (a)-[:FOLLOWS]->(b) } AS following,
               EXISTS { (b)-[:FOLLOWS]->(a) } AS followedBy,
               coalesce(w.times, 0) AS workedTogetherTimes,
               COUNT { (a)-[:FOLLOWS]->(m:User)<-[:FOLLOWS]-(b) } AS mutualFollowing
        """,
        {"currentId": current_user_id, "targetId": target_user_id},
    )
    if not rows:
        return None
    status = rows[0]
    status["mutual"] = status["following"] and status["followedBy"]
    status["workedTogether"] = status["workedTogetherTimes"] > 0
    return status


def get_ego_network(user_id, max_nodes=50):
    """Nodes and edges around a user (FOLLOWS + WORKED_WITH, 1 hop) for the
    network visualization page. Returns {"nodes": [...], "edges": [...]}.
    With more than max_nodes neighbours, the strongest ties are kept
    (teammates, then mutual follows, then one-way follows).
    """
    rows = db.execute_query(
        """
        MATCH (u:User {userId: $userId})
        OPTIONAL MATCH (u)-[r:FOLLOWS|WORKED_WITH]-(n:User)
        // Over max_nodes neighbours, keep teammates first, then mutual follows.
        WITH u, n, count(r) + 2 * count(CASE type(r) WHEN 'WORKED_WITH' THEN 1 END) AS strength
        ORDER BY strength DESC, n.username
        WITH u, collect(n)[..$maxNodes] AS neighbours
        WITH [u] + neighbours AS people
        UNWIND people AS p
        OPTIONAL MATCH (p)-[r:FOLLOWS|WORKED_WITH]->(q:User)
        WHERE q IN people
        RETURN collect(DISTINCT {userId: p.userId, username: p.username,
                                 displayName: p.displayName}) AS nodes,
               collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE
                   {source: p.userId, target: q.userId, type: type(r),
                    times: r.times} END) AS edges
        """,
        {"userId": user_id, "maxNodes": max_nodes},
    )
    if not rows or not rows[0]["nodes"]:
        return {"nodes": [], "edges": []}
    return rows[0]
