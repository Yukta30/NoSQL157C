"""Cached wrappers around the backend.

Pages call these instead of the backend directly, so Streamlit reruns don't
re-query Neo4j. Writes (follow/unfollow) clear the cache because they change
counts, connection status, recommendations and the network.
"""

import streamlit as st

from backend import recommendations, social, team_builder, users

_cached = st.cache_data(ttl=300, show_spinner=False)


# ---------- users ----------

@_cached
def search_users(term, limit=20):
    return users.search_users(term, limit=limit)


@_cached
def get_user(user_id):
    return users.get_user(user_id)


@_cached
def get_user_profile(user_id):
    return users.get_user_profile(user_id)


@_cached
def list_skills():
    return users.list_skills()


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
def ego_network(user_id, max_nodes=50):
    return social.get_ego_network(user_id, max_nodes=max_nodes)


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
def build_team(skills, team_size, me, include_me):
    return team_builder.build_team(
        list(skills), team_size=team_size, current_user_id=me, include_me=include_me
    )


@_cached
def rank_candidates(skills, limit=10):
    return team_builder.rank_candidates(list(skills), limit=limit)
