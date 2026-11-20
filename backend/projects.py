"""Projects and team invites: the app's own teams.

A user creates a Project that needs some skills, invites people (the team
builder suggests who), and invitees accept or decline from their inbox.
Accepted members join the project, which is the app-made team.

Graph model (separate relationship types, so the imported Kaggle teams and
their WORKED_WITH derivation are untouched):

  (:Project {projectId, title, description, teamSize, status, createdAt})
      projectId "p" + UUID4 hex; status "open" | "full" | "closed"
  (User)-[:OWNS]->(Project)
  (User)-[:JOINED {role: "owner" | "member", since}]->(Project)
  (User)-[:INVITED {status: "pending" | "accepted" | "declined",
                    invitedBy, message, at, respondedAt}]->(Project)
  (Project)-[:NEEDS]->(Skill)

Every function raises ValueError with a message the UI can show when an
action isn't allowed (not the owner, project full, already invited, ...).
"""

import uuid

from backend import team_builder, users
from backend.db import db

MAX_TEAM_SIZE = 8
MAX_TITLE = 80
MAX_TEXT = 500

_PROJECT_FIELDS = """
    projectId: p.projectId, title: p.title, description: p.description,
    teamSize: p.teamSize, status: p.status, createdAt: p.createdAt
"""
_PERSON = "{userId: {v}.userId, username: {v}.username, displayName: {v}.displayName, tier: {v}.tier}"


def _person(var):
    return _PERSON.replace("{v}", var)


# ---------- reads ----------

def get_project(project_id):
    """Everything the project page needs, or None if it doesn't exist."""
    rows = db.execute_query(
        f"""
        MATCH (p:Project {{projectId: $projectId}})
        MATCH (owner:User)-[:OWNS]->(p)
        RETURN {{ {_PROJECT_FIELDS} }} AS project,
               {_person('owner')} AS owner,
               COLLECT {{ MATCH (p)-[:NEEDS]->(s:Skill) RETURN s.name ORDER BY s.name }} AS skills,
               COLLECT {{
                 MATCH (m:User)-[j:JOINED]->(p)
                 RETURN {{user: {_person('m')}, role: j.role, since: j.since}}
                 ORDER BY j.role DESC, j.since
               }} AS members,
               COLLECT {{
                 MATCH (u:User)-[i:INVITED]->(p)
                 RETURN {{user: {_person('u')}, status: i.status, message: i.message,
                         at: i.at, respondedAt: i.respondedAt}}
                 ORDER BY i.at DESC
               }} AS invites
        """,
        {"projectId": project_id},
    )
    if not rows:
        return None
    r = rows[0]
    project = {**r["project"], "owner": r["owner"], "skills": r["skills"],
               "members": r["members"], "invites": r["invites"]}
    project["openSpots"] = max(project["teamSize"] - len(project["members"]), 0)
    project["coverage"] = _coverage(project)
    return project


def _coverage(project):
    """Best member strength per needed skill (same idea as the team builder)."""
    if not project["skills"] or not project["members"]:
        return [{"skill": s, "weight": 0.0, "coveredBy": None} for s in project["skills"]]
    rows = db.execute_query(
        """
        UNWIND $skills AS skill
        OPTIONAL MATCH (u:User)-[r:HAS_SKILL]->(:Skill {name: skill})
        WHERE u.userId IN $memberIds
        WITH skill, u, r ORDER BY r.weight DESC
        WITH skill, collect({name: coalesce(u.displayName, u.username), weight: r.weight})[0] AS best
        RETURN skill, coalesce(best.weight, 0.0) AS weight,
               CASE WHEN best.weight IS NULL THEN null ELSE best.name END AS coveredBy
        """,
        {"skills": project["skills"], "memberIds": [m["user"]["userId"] for m in project["members"]]},
    )
    order = {s: i for i, s in enumerate(project["skills"])}
    return sorted(rows, key=lambda r: order[r["skill"]])


def get_user_projects(user_id):
    """Projects the user owns or joined, newest first, with a few counts."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $userId}})-[j:JOINED]->(p:Project)
        MATCH (owner:User)-[:OWNS]->(p)
        RETURN {{ {_PROJECT_FIELDS} }} AS project, j.role AS role, {_person('owner')} AS owner,
               COLLECT {{ MATCH (p)-[:NEEDS]->(s:Skill) RETURN s.name ORDER BY s.name }} AS skills,
               COUNT {{ (:User)-[:JOINED]->(p) }} AS memberCount,
               COUNT {{ (:User)-[:INVITED {{status: 'pending'}}]->(p) }} AS pendingInvites
        ORDER BY p.createdAt DESC
        """,
        {"userId": user_id},
    )


def get_inbox(user_id):
    """Pending invites for this user, newest first."""
    return db.execute_query(
        f"""
        MATCH (:User {{userId: $userId}})-[i:INVITED {{status: 'pending'}}]->(p:Project)
        MATCH (owner:User)-[:OWNS]->(p)
        OPTIONAL MATCH (inviter:User {{userId: i.invitedBy}})
        RETURN {{ {_PROJECT_FIELDS} }} AS project, {_person('owner')} AS owner,
               {_person('inviter')} AS inviter, i.message AS message, i.at AS at,
               COLLECT {{ MATCH (p)-[:NEEDS]->(s:Skill) RETURN s.name ORDER BY s.name }} AS skills,
               COUNT {{ (:User)-[:JOINED]->(p) }} AS memberCount
        ORDER BY i.at DESC
        """,
        {"userId": user_id},
    )


def pending_invite_count(user_id):
    rows = db.execute_query(
        "RETURN COUNT { (:User {userId: $userId})-[:INVITED {status: 'pending'}]->(:Project) } AS n",
        {"userId": user_id},
    )
    return rows[0]["n"]


def get_invitable_projects(owner_id, invitee_id):
    """The owner's open projects that this person isn't in or invited to (for an Invite button)."""
    return db.execute_query(
        """
        MATCH (:User {userId: $ownerId})-[:OWNS]->(p:Project {status: 'open'})
        WHERE NOT EXISTS { (:User {userId: $inviteeId})-[:JOINED]->(p) }
          AND NOT EXISTS { (:User {userId: $inviteeId})-[:INVITED {status: 'pending'}]->(p) }
        RETURN p.projectId AS projectId, p.title AS title
        ORDER BY p.createdAt DESC
        """,
        {"ownerId": owner_id, "inviteeId": invitee_id},
    )


def suggest_members(project_id, limit=None):
    """Team-builder picks that would complete the project's team.

    Current members count toward coverage; people already invited (pending)
    or who declined are skipped. Returns build_team()'s result.
    """
    project = _require_project(project_id)
    member_ids = [m["user"]["userId"] for m in project["members"]]
    skip = [i["user"]["userId"] for i in project["invites"] if i["status"] in ("pending", "declined")]
    if not project["skills"]:
        raise ValueError("Add at least one needed skill to get suggestions.")
    owner_id = project["owner"]["userId"]
    return team_builder.build_team(
        project["skills"], team_size=project["teamSize"], current_user_id=owner_id,
        member_ids=[m for m in member_ids if m != owner_id], exclude_user_ids=skip,
    )


# ---------- writes ----------

def _clean_skills(skills):
    names = []
    for s in skills or []:
        s = (s or "").strip().lower()
        if s and s not in names:
            names.append(s)
    known = {s["name"] for s in users.list_skills()}
    unknown = [s for s in names if s not in known]
    if unknown:
        raise ValueError("Not in the skill list: " + ", ".join(unknown))
    return names


def create_project(owner_id, title, description="", skills=(), team_size=4):
    """Create a project owned (and joined) by owner_id. Returns get_project()."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Give the project a title.")
    if len(title) > MAX_TITLE:
        raise ValueError(f"Title must be {MAX_TITLE} characters or fewer.")
    description = (description or "").strip()[:MAX_TEXT]
    if not 2 <= int(team_size) <= MAX_TEAM_SIZE:
        raise ValueError(f"Team size must be between 2 and {MAX_TEAM_SIZE}.")
    skills = _clean_skills(skills)
    if not users.user_exists(owner_id):
        raise ValueError(f"Unknown user: {owner_id}")

    project_id = "p" + uuid.uuid4().hex
    db.execute_query(
        """
        MATCH (owner:User {userId: $ownerId})
        CREATE (p:Project {projectId: $projectId, title: $title, description: $description,
                           teamSize: $teamSize, status: 'open', createdAt: datetime()})
        CREATE (owner)-[:OWNS]->(p)
        CREATE (owner)-[:JOINED {role: 'owner', since: datetime()}]->(p)
        WITH p
        UNWIND $skills AS name
        MATCH (s:Skill {name: name})
        CREATE (p)-[:NEEDS]->(s)
        """,
        {"ownerId": owner_id, "projectId": project_id, "title": title, "description": description,
         "teamSize": int(team_size), "skills": skills},
        write=True,
    )
    return get_project(project_id)


def _require_project(project_id):
    project = get_project(project_id)
    if project is None:
        raise ValueError("That project doesn't exist any more.")
    return project


def _require_owner(project, user_id):
    if project["owner"]["userId"] != user_id:
        raise ValueError("Only the project owner can do that.")


def invite(project_id, inviter_id, invitee_id, message=""):
    """Owner invites someone. Re-inviting after a decline is allowed."""
    project = _require_project(project_id)
    _require_owner(project, inviter_id)
    if invitee_id == inviter_id:
        raise ValueError("You're already on this project.")
    if project["status"] != "open":
        raise ValueError("This project isn't taking new members.")
    if any(m["user"]["userId"] == invitee_id for m in project["members"]):
        raise ValueError("They're already on this project.")
    if any(i["user"]["userId"] == invitee_id and i["status"] == "pending" for i in project["invites"]):
        raise ValueError("They already have a pending invite.")
    if not users.user_exists(invitee_id):
        raise ValueError(f"Unknown user: {invitee_id}")
    db.execute_query(
        """
        MATCH (u:User {userId: $inviteeId}), (p:Project {projectId: $projectId})
        MERGE (u)-[i:INVITED]->(p)
        SET i.status = 'pending', i.invitedBy = $inviterId, i.message = $message,
            i.at = datetime(), i.respondedAt = null
        """,
        {"inviteeId": invitee_id, "projectId": project_id, "inviterId": inviter_id,
         "message": (message or "").strip()[:MAX_TEXT] or None},
        write=True,
    )


def respond(project_id, user_id, accept):
    """Invitee accepts or declines. Accepting joins the project (if there's room)."""
    project = _require_project(project_id)
    pending = [i for i in project["invites"] if i["user"]["userId"] == user_id and i["status"] == "pending"]
    if not pending:
        raise ValueError("There's no pending invite for you on this project.")
    if accept and (project["status"] != "open" or project["openSpots"] <= 0):
        raise ValueError("Sorry, this project's team is already full.")
    db.execute_query(
        """
        MATCH (u:User {userId: $userId})-[i:INVITED {status: 'pending'}]->(p:Project {projectId: $projectId})
        SET i.status = CASE WHEN $accept THEN 'accepted' ELSE 'declined' END,
            i.respondedAt = datetime()
        WITH u, p
        CALL (u, p) {
          WITH u, p WHERE $accept
          MERGE (u)-[j:JOINED]->(p)
          ON CREATE SET j.role = 'member', j.since = datetime()
        }
        WITH p, COUNT { (:User)-[:JOINED]->(p) } AS members
        SET p.status = CASE WHEN p.status = 'open' AND members >= p.teamSize THEN 'full' ELSE p.status END
        """,
        {"userId": user_id, "projectId": project_id, "accept": bool(accept)},
        write=True,
    )


def cancel_invite(project_id, owner_id, invitee_id):
    project = _require_project(project_id)
    _require_owner(project, owner_id)
    db.execute_query(
        """
        MATCH (:User {userId: $inviteeId})-[i:INVITED {status: 'pending'}]->(:Project {projectId: $projectId})
        DELETE i
        """,
        {"inviteeId": invitee_id, "projectId": project_id},
        write=True,
    )


def leave(project_id, user_id):
    """A member leaves (the owner deletes or closes instead). Reopens a full project."""
    project = _require_project(project_id)
    if project["owner"]["userId"] == user_id:
        raise ValueError("Owners can't leave their own project; delete or close it instead.")
    db.execute_query(
        """
        MATCH (:User {userId: $userId})-[j:JOINED]->(p:Project {projectId: $projectId})
        DELETE j
        WITH p
        SET p.status = CASE WHEN p.status = 'full' THEN 'open' ELSE p.status END
        """,
        {"userId": user_id, "projectId": project_id},
        write=True,
    )


def set_status(project_id, owner_id, status):
    """Owner opens or closes the project to new members."""
    if status not in ("open", "closed"):
        raise ValueError("Status must be 'open' or 'closed'.")
    project = _require_project(project_id)
    _require_owner(project, owner_id)
    if status == "open" and project["openSpots"] <= 0:
        status = "full"
    db.execute_query("MATCH (p:Project {projectId: $projectId}) SET p.status = $status",
                     {"projectId": project_id, "status": status}, write=True)


def delete_project(project_id, owner_id):
    project = _require_project(project_id)
    _require_owner(project, owner_id)
    db.execute_query("MATCH (p:Project {projectId: $projectId}) DETACH DELETE p",
                     {"projectId": project_id}, write=True)
