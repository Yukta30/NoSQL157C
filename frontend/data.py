"""Cached wrappers around the backend.

Pages call these instead of the backend directly, so Streamlit reruns don't
re-query Neo4j. Writes (follow/unfollow) clear the cache because they change
counts, connection status, recommendations and the network.
"""

import streamlit as st

from backend import accounts, projects, recommendations, social, team_builder, users

_cached = st.cache_data(ttl=300, show_spinner=False)


# ---------- users ----------

@_cached
def search_users(term, limit=20):
    return users.search_users(term, limit=limit)


@_cached
def get_user(user_id):
    return users.get_user(user_id)


@_cached
def get_user_by_username(username):
    return users.get_user_by_username(username)


@_cached
def get_user_profile(user_id):
    return users.get_user_profile(user_id)


@_cached
def list_skills():
    return users.list_skills()


@_cached
def graph_stats():
    return users.get_graph_stats()


@_cached
def list_interests():
    return users.list_interests()


# ---------- accounts (writes clear the cache: new users show up in search) ----------

def register_user(**fields):
    user = accounts.register_user(**fields)
    st.cache_data.clear()
    return user


def authenticate(username, password):
    return accounts.authenticate(username, password)


def update_profile(user_id, **fields):
    user = accounts.update_profile(user_id, **fields)
    st.cache_data.clear()
    return user


# ---------- social ----------

@_cached
def connection_status(me, other):
    return social.get_connection_status(me, other)


@_cached
def followers(user_id):
    return social.get_followers(user_id)


@_cached
def following(user_id):
    return social.get_following(user_id)


@_cached
def collaborators(user_id):
    return social.get_collaborators(user_id)


@_cached
def mutual_follows(user_id):
    return social.get_mutual_follows(user_id)


@_cached
def ego_network(user_id, max_nodes=50):
    return social.get_ego_network(user_id, max_nodes=max_nodes)


@_cached
def following_ids(user_id):
    """Ids this user follows, for drawing many Follow buttons without a query each."""
    return {row["user"]["userId"] for row in social.get_following(user_id)}


@_cached
def two_hop_recommendations(user_id, limit=25):
    return social.get_two_hop_recommendations(user_id, limit=limit)


@_cached
def mutual_following(user_a, user_b):
    return social.get_mutual_following(user_a, user_b)


@_cached
def popular_users(limit=25):
    return social.get_popular_users(limit=limit)


@_cached
def degrees_of_separation(from_username, to_username, max_hops=4):
    return social.degrees_of_separation(from_username, to_username, max_hops=max_hops)


@_cached
def count_users():
    return users.count_users()


@_cached
def all_users(skip, limit):
    return users.list_all_users(skip, limit)


@_cached
def user_page_of(username, page_size):
    return users.user_page_of(username, page_size)


def follow(me, other):
    created = social.follow_user(me, other)
    st.cache_data.clear()
    return created


def unfollow(me, other):
    deleted = social.unfollow_user(me, other)
    st.cache_data.clear()
    return deleted


# ---------- recommendations & team builder ----------

@_cached
def recommend_users(me, limit=10):
    return recommendations.recommend_users(me, limit=limit)


@_cached
def explain_recommendation(me, other):
    return recommendations.explain_recommendation(me, other)


@_cached
def build_team(skills, team_size, me, include_me, pinned=()):
    """pinned: people the user added by hand; they're kept and the rest is built around them."""
    return team_builder.build_team(
        list(skills), team_size=team_size, current_user_id=me, include_me=include_me,
        member_ids=list(pinned),
    )


@_cached
def rank_candidates(skills, limit=10, exclude=()):
    return team_builder.rank_candidates(list(skills), limit=limit, exclude_user_ids=list(exclude))



# ---------- projects & invites (every write clears the cache) ----------

@_cached
def get_project(project_id):
    return projects.get_project(project_id)


@_cached
def user_projects(user_id):
    return projects.get_user_projects(user_id)


@_cached
def inbox(user_id):
    return projects.get_inbox(user_id)


@_cached
def pending_invite_count(user_id):
    return projects.pending_invite_count(user_id)


@_cached
def invitable_projects(owner_id, invitee_id):
    return projects.get_invitable_projects(owner_id, invitee_id)


@_cached
def suggest_members(project_id):
    return projects.suggest_members(project_id)


def _write(fn, *args, **kwargs):
    result = fn(*args, **kwargs)
    st.cache_data.clear()
    return result


def create_project(*args, **kwargs):
    return _write(projects.create_project, *args, **kwargs)


def invite(*args, **kwargs):
    return _write(projects.invite, *args, **kwargs)


def respond_invite(*args, **kwargs):
    return _write(projects.respond, *args, **kwargs)


def cancel_invite(*args, **kwargs):
    return _write(projects.cancel_invite, *args, **kwargs)


def leave_project(*args, **kwargs):
    return _write(projects.leave, *args, **kwargs)


def set_project_status(*args, **kwargs):
    return _write(projects.set_status, *args, **kwargs)


def delete_project(*args, **kwargs):
    return _write(projects.delete_project, *args, **kwargs)
