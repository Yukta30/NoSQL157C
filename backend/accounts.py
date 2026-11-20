"""App accounts: registration, password login, and profile editing.

Registered users follow docs/csv_contract.md ("App-registered users"):
  userId     "u" + UUID4 hex
  source     "app"
  skills / interests the user picks from the vocabulary, written as
  HAS_SKILL / INTERESTED_IN with weight 0.5, competitions 0, source "self".

Passwords are never stored. Each user gets a random salt and a scrypt hash
(Python standard library), kept in the User's `passwordHash` property, which
users.USER_FIELDS deliberately doesn't return. Users imported from Meta Kaggle
have no password; the app lets people explore as them without logging in.
"""

import hashlib
import hmac
import re
import secrets
import uuid

from neo4j.exceptions import ConstraintError

from backend import users
from backend.db import db

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,30}$")
MIN_PASSWORD_LENGTH = 8
SELF_WEIGHT = 0.5

# scrypt cost settings; stored with each hash so they can change later.
_N, _R, _P = 2**14, 8, 1


# ---------- passwords ----------

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                               n=int(n), r=int(r), p=int(p))
    except (AttributeError, ValueError):
        return False
    return hmac.compare_digest(check.hex(), digest)


# ---------- validation ----------

def normalize_username(username):
    return (username or "").strip().lower()


def _clean_tags(names):
    seen, out = set(), []
    for name in names or []:
        name = (name or "").strip().lower()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _check_vocabulary(skills, interests):
    known_skills = {s["name"] for s in users.list_skills()}
    known_interests = {i["name"] for i in users.list_interests()}
    unknown = [s for s in skills if s not in known_skills] + [i for i in interests if i not in known_interests]
    if unknown:
        raise ValueError("Not in the skill/interest list: " + ", ".join(unknown))


def _check_profile(display_name, skills, interests):
    if not (display_name or "").strip():
        raise ValueError("Display name can't be empty.")
    if len(display_name.strip()) > 60:
        raise ValueError("Display name must be 60 characters or fewer.")
    _check_vocabulary(skills, interests)


# ---------- registration / login ----------

_SET_TAGS = """
WITH u
CALL (u) {
  OPTIONAL MATCH (u)-[old:HAS_SKILL|INTERESTED_IN {source: 'self'}]->()
  DELETE old
}
CALL (u) {
  UNWIND $skills AS name
  MATCH (s:Skill {name: name})
  MERGE (u)-[r:HAS_SKILL]->(s)
  ON CREATE SET r.weight = $weight, r.competitions = 0, r.medals = 0, r.source = 'self'
}
CALL (u) {
  UNWIND $interests AS name
  MATCH (i:Interest {name: name})
  MERGE (u)-[r:INTERESTED_IN]->(i)
  ON CREATE SET r.weight = $weight, r.competitions = 0, r.source = 'self'
}
RETURN u.userId AS userId
"""


def register_user(username, display_name, password, skills=(), interests=(), country=None):
    """Create an app account and return the new user (users.get_user shape).

    Raises ValueError with a message for the UI when something is invalid
    (bad or taken username, short password, unknown skill, ...).
    """
    username = normalize_username(username)
    if not USERNAME_RE.match(username):
        raise ValueError("Username must be 3-30 characters: lowercase letters, numbers, '.', '_' or '-'.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    skills, interests = _clean_tags(skills), _clean_tags(interests)
    _check_profile(display_name, skills, interests)
    if users.get_user_by_username(username):
        raise ValueError(f"The username @{username} is already taken.")

    user_id = "u" + uuid.uuid4().hex
    try:
        db.execute_query(
            """
            CREATE (u:User {userId: $userId, username: $username, displayName: $displayName,
                            country: $country, registerDate: date(), golds: 0, silvers: 0,
                            bronzes: 0, source: 'app', passwordHash: $passwordHash})
            """ + _SET_TAGS,
            {"userId": user_id, "username": username, "displayName": display_name.strip(),
             "country": (country or "").strip() or None, "passwordHash": hash_password(password),
             "skills": skills, "interests": interests, "weight": SELF_WEIGHT},
            write=True,
        )
    except ConstraintError:  # someone took the username in the meantime
        raise ValueError(f"The username @{username} is already taken.") from None
    return users.get_user(user_id)


def authenticate(username, password):
    """The user if the username/password match an app account, else None."""
    rows = db.execute_query(
        "MATCH (u:User {username: $username}) RETURN u.userId AS userId, u.passwordHash AS passwordHash",
        {"username": normalize_username(username)},
    )
    if not rows or not rows[0]["passwordHash"]:
        # Same work as a real check, so timing doesn't reveal which usernames exist.
        verify_password(password or "", hash_password("not-a-real-password"))
        return None
    if not verify_password(password or "", rows[0]["passwordHash"]):
        return None
    return users.get_user(rows[0]["userId"])


def can_edit_profile(user):
    """Only app accounts are editable; Kaggle profiles come from the dataset."""
    return bool(user) and user.get("source") == "app"


def update_profile(user_id, display_name, country=None, skills=(), interests=()):
    """Replace an app user's display name, country and self-declared skills/interests."""
    user = users.get_user(user_id)
    if not can_edit_profile(user):
        raise ValueError("Only accounts created in the app can be edited.")
    skills, interests = _clean_tags(skills), _clean_tags(interests)
    _check_profile(display_name, skills, interests)
    db.execute_query(
        """
        MATCH (u:User {userId: $userId})
        SET u.displayName = $displayName, u.country = $country
        """ + _SET_TAGS,
        {"userId": user_id, "displayName": display_name.strip(),
         "country": (country or "").strip() or None,
         "skills": skills, "interests": interests, "weight": SELF_WEIGHT},
        write=True,
    )
    return users.get_user(user_id)
