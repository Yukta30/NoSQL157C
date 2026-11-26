"""Social graph: following, followers, connection status.

(User)-[:FOLLOWS {since: date}]->(User) is directed.
(User)-[:WORKED_WITH {times}]-(User) is undirected (derived from shared teams).
"""

from backend.db import db

_USER_SUMMARY = "userId: {v}.userId, username: {v}.username, displayName: {v}.displayName, tier: {v}.tier"


def _summary(var):
    return "{" + _USER_SUMMARY.format(v=var) + "}"


def follow_user(current_user_id, target_user_id):
    """UC-5: make the current user follow the target.

    Creates (current)-[:FOLLOWS {since: today}]->(target) and returns True.
    Raises ValueError (with a message for the UI) for self-follows, unknown
    users, or when the follow already exists; no relationship is created then.
    """
    if current_user_id == target_user_id:
        raise ValueError("You can't follow yourself.")

    rows = db.execute_query(
        """
        MATCH (a:User {userId: $currentId}), (b:User {userId: $targetId})
        OPTIONAL MATCH (a)-[existing:FOLLOWS]->(b)
        WITH a, b, existing IS NOT NULL AS alreadyFollowing
        CALL (a, b, alreadyFollowing) {
          WITH a, b WHERE NOT alreadyFollowing
          CREATE (a)-[:FOLLOWS {since: date()}]->(b)
        }
        RETURN alreadyFollowing, coalesce(b.displayName, b.username) AS name
        """,
        {"currentId": current_user_id, "targetId": target_user_id},
        write=True,
    )
    if not rows:
        raise ValueError(f"Unknown user: {current_user_id} or {target_user_id}")
    if rows[0]["alreadyFollowing"]:
        raise ValueError(f"You already follow {rows[0]['name']}.")
    return True


def unfollow_user(current_user_id, target_user_id):
    """UC-6: remove the follow. Returns True if one was deleted, False if none existed."""
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
    """UC-7 (Following): users this user follows, most recent first."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $userId}})-[f:FOLLOWS]->(other:User)
        RETURN {_summary('other')} AS user, f.since AS since
        ORDER BY f.since DESC, other.username
        """,
        {"userId": user_id},
    )


def get_followers(user_id):
    """UC-7 (Followers): users following this user, most recent first."""
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


def get_mutual_following(user_a, user_b):
    """UC-8: users followed by both A and B, found with one graph pattern."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $a}})-[:FOLLOWS]->(m:User)<-[:FOLLOWS]-(:User {{userId: $b}})
        RETURN {_summary('m')} AS user, COUNT {{ (m)<-[:FOLLOWS]-() }} AS followers
        ORDER BY followers DESC, m.username
        """,
        {"a": user_a, "b": user_b},
    )


def get_two_hop_recommendations(user_id, limit=25):
    """UC-9: people reached by exactly two FOLLOWS hops (me -> A -> B).

    Excludes me and people I already follow; each person appears once, with
    how many of the people I follow lead to them (and a few of their names).
    """
    return db.execute_query(
        f"""
        MATCH (me:User {{userId: $userId}})-[:FOLLOWS]->(a:User)-[:FOLLOWS]->(b:User)
        WHERE b <> me AND NOT (me)-[:FOLLOWS]->(b)
        WITH b, collect(DISTINCT coalesce(a.displayName, a.username)) AS via
        RETURN {_summary('b')} AS user, size(via) AS viaCount, via[..3] AS viaNames,
               COUNT {{ (b)<-[:FOLLOWS]-() }} AS followers
        ORDER BY viaCount DESC, followers DESC, b.username
        LIMIT $limit
        """,
        {"userId": user_id, "limit": limit},
    )


def get_popular_users(limit=25):
    """UC-12: the most-followed users, most followers first."""
    return db.execute_query(
        f"""
        MATCH (u:User)
        WITH u, COUNT {{ (u)<-[:FOLLOWS]-() }} AS followers
        ORDER BY followers DESC, u.username
        LIMIT $limit
        RETURN {_summary('u')} AS user, followers
        """,
        {"limit": limit},
    )


def degrees_of_separation(from_username, to_username, max_hops=4):
    """UC-13: shortest directed FOLLOWS path from one user to another.

    Returns {"from", "to", "found", "degrees", "path"} where path is the list
    of users along the way. Raises ValueError for unknown usernames.
    """
    max_hops = int(max_hops)
    rows = db.execute_query(
        f"""
        OPTIONAL MATCH (a:User {{username: $from}})
        OPTIONAL MATCH (b:User {{username: $to}})
        RETURN a IS NOT NULL AS fromExists, b IS NOT NULL AS toExists
        """,
        {"from": from_username, "to": to_username},
    )
    missing = [u for u, ok in ((from_username, rows[0]["fromExists"]), (to_username, rows[0]["toExists"]))
               if not ok]
    if missing:
        raise ValueError("No user with username " + " or ".join(f"@{u}" for u in missing) + ".")
    result = {"from": from_username, "to": to_username, "maxHops": max_hops}
    if from_username == to_username:
        return {**result, "found": True, "degrees": 0, "path": [_one_user(from_username)]}

    rows = db.execute_query(
        f"""
        MATCH (a:User {{username: $from}}), (b:User {{username: $to}})
        MATCH p = shortestPath((a)-[:FOLLOWS*..{max_hops}]->(b))
        RETURN [n IN nodes(p) | {_summary('n')}] AS path, length(p) AS degrees
        """,
        {"from": from_username, "to": to_username},
    )
    if not rows:
        return {**result, "found": False, "degrees": None, "path": []}
    return {**result, "found": True, "degrees": rows[0]["degrees"], "path": rows[0]["path"]}


def _one_user(username):
    rows = db.execute_query(f"MATCH (u:User {{username: $u}}) RETURN {_summary('u')} AS user", {"u": username})
    return rows[0]["user"]
