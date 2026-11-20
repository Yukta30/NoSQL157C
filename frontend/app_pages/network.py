"""Ego network: the person in the middle and everyone one hop away through a
FOLLOWS or WORKED_WITH relationship, drawn as a dark, interactive graph
(st.echarts_chart). Nodes are colored by how they relate to the center."""

from html import escape

import streamlit as st

from frontend import components, data
from frontend.session import display_name, get_me

# Dark wine canvas with warm, muted accents (matches the burgundy/beige theme).
CANVAS = "#1E0B10"
TEXT = "#F5EBDD"
MUTED = "#B9A595"
CENTER_COLOR = "#E8C9A0"   # beige-gold: the person in the middle
WORKED_COLOR = "#D9774B"   # terracotta
FOLLOW_EDGE = "#6E4A52"

# (name shown in the legend, color), most specific relationship first.
CATEGORIES = {
    "center": ("In the middle", CENTER_COLOR),
    "teammate": ("Teammates", WORKED_COLOR),
    "mutual": ("Follow each other", "#C98BB0"),
    "following": ("Followed", "#9FB4C7"),
    "follower": ("Followers", "#A3B88C"),
    "other": ("Others", "#8A7B6E"),
}
ORDER = list(CATEGORIES)


def relationships(center_id, edges):
    """Each neighbor's relationship to the center, from the center's own edges."""
    follows, followed_by, teammates = set(), set(), set()
    for e in edges:
        a, b = e["source"], e["target"]
        if e["type"] == "WORKED_WITH" and center_id in (a, b):
            teammates.add(b if a == center_id else a)
        elif e["type"] == "FOLLOWS":
            if a == center_id:
                follows.add(b)
            elif b == center_id:
                followed_by.add(a)

    def kind(uid):
        if uid == center_id:
            return "center"
        if uid in teammates:
            return "teammate"
        if uid in follows and uid in followed_by:
            return "mutual"
        if uid in follows:
            return "following"
        if uid in followed_by:
            return "follower"
        return "other"

    counts = {"follows": len(follows), "followers": len(followed_by), "teammates": len(teammates),
              "mutual": len(follows & followed_by)}
    return kind, counts


def chart_spec(network, center_id, kind, center_label):
    crowded = len(network["nodes"]) > 25
    degree = {n["userId"]: 0 for n in network["nodes"]}
    for e in network["edges"]:
        for uid in (e["source"], e["target"]):
            if uid in degree:
                degree[uid] += 1

    nodes = []
    for n in network["nodes"]:
        k = kind(n["userId"])
        color = CATEGORIES[k][1]
        is_center = k == "center"
        nodes.append({
            "id": n["userId"],
            "name": center_label if is_center else display_name(n),
            "category": ORDER.index(k),
            "symbolSize": 58 if is_center else (14 if crowded else 22) + (2 if crowded else 4)
                          * min(degree[n["userId"]], 6),
            "itemStyle": {"color": color, "shadowColor": color, "shadowBlur": 30 if is_center else 16,
                          "borderColor": "rgba(245,235,221,0.85)", "borderWidth": 3 if is_center else 1.5},
            "label": {"fontWeight": "bold" if is_center else "normal", "fontSize": 14 if is_center else 12,
                      "show": is_center or not crowded},
            "tooltip": {"formatter": f"{display_name(n)}<br/>@{n['username']}<br/>{CATEGORIES[k][0]}"},
        })

    links, seen = [], set()
    follow_pairs = {(e["source"], e["target"]) for e in network["edges"] if e["type"] == "FOLLOWS"}
    for e in network["edges"]:
        a, b = e["source"], e["target"]
        if e["type"] == "WORKED_WITH":
            times = e.get("times") or 1
            links.append({
                "source": a, "target": b,
                "lineStyle": {"color": WORKED_COLOR, "width": 2 + 1.5 * times, "opacity": 0.9,
                              "curveness": 0, "shadowColor": WORKED_COLOR, "shadowBlur": 8},
                "symbol": ["none", "none"],
                "tooltip": {"formatter": f"Worked together on {times} team{'s' if times != 1 else ''}"},
            })
        elif frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            mutual = (b, a) in follow_pairs
            links.append({
                "source": a, "target": b,
                "lineStyle": {"color": FOLLOW_EDGE, "width": 1.5, "type": "dashed", "curveness": 0.2,
                              "opacity": 0.8},
                "symbol": ["arrow", "arrow"] if mutual else ["none", "arrow"],
                "tooltip": {"formatter": "Follow each other" if mutual else "Follows"},
            })

    used = sorted({node["category"] for node in nodes})
    return {
        "backgroundColor": CANVAS,
        "tooltip": {"trigger": "item", "backgroundColor": "#2A1218", "borderColor": "#4A2730",
                    "textStyle": {"color": TEXT}},
        "legend": {"data": [CATEGORIES[ORDER[i]][0] for i in used], "top": 16, "left": "center",
                   "icon": "circle", "itemGap": 18, "textStyle": {"color": TEXT, "fontSize": 12},
                   "inactiveColor": "#4A2F35"},
        "animationDuration": 800,
        "series": [{
            "type": "graph",
            "layout": "force",
            "data": nodes,
            "links": links,
            "categories": [{"name": CATEGORIES[k][0], "itemStyle": {"color": CATEGORIES[k][1]}}
                           for k in ORDER],
            "roam": True,
            "draggable": True,
            "selectedMode": "single",
            "select": {"itemStyle": {"borderColor": "#F5EBDD", "borderWidth": 4}},
            "cursor": "pointer",
            "top": 80,
            "force": ({"repulsion": 260, "edgeLength": [70, 220], "gravity": 0.12, "friction": 0.2}
                      if crowded else {"repulsion": 420, "edgeLength": [90, 170], "gravity": 0.08,
                                       "friction": 0.2}),
            "edgeSymbolSize": [4, 9],
            "label": {"show": True, "position": "bottom", "distance": 6, "color": TEXT},
            "emphasis": {"focus": "adjacency", "lineStyle": {"width": 4},
                         "label": {"show": True, "fontWeight": "bold"}},
            "blur": {"itemStyle": {"opacity": 0.15}, "lineStyle": {"opacity": 0.05},
                     "label": {"opacity": 0.2}},
        }],
    }


def stat_tiles(stats):
    """Glowing stat chips for the dark panel (st.html is isolated, so styles are inline)."""
    tiles = "".join(
        f"<div style='flex:1 1 110px;background:#2A1218;border:1px solid #42232B;border-radius:16px;"
        f"padding:12px 14px'>"
        f"<div style='display:flex;align-items:center;gap:6px;color:{MUTED};font-size:12px;"
        f"font-weight:600;letter-spacing:.04em;text-transform:uppercase'>"
        f"<span style='width:8px;height:8px;border-radius:50%;background:{color};"
        f"box-shadow:0 0 8px {color}'></span>{escape(label)}</div>"
        f"<div style='color:{TEXT};font-size:26px;font-weight:700;margin-top:4px'>{value}</div></div>"
        for label, value, color in stats
    )
    return f"<div style='display:flex;flex-wrap:wrap;gap:10px'>{tiles}</div>"


def panel_header(title, subtitle):
    return (f"<div style='color:{TEXT};font-size:22px;font-weight:700'>{escape(title)}</div>"
            f"<div style='color:{MUTED};font-size:14px;margin-top:2px'>{escape(subtitle)}</div>")


def selected_ids(state):
    """User ids picked in the chart (one at most, selectedMode is single)."""
    try:
        groups = state["selection"]["selected"]
    except (KeyError, TypeError):
        return []
    ids = []
    for group in groups or []:
        ids += group.get("data_indices", []) if isinstance(group, dict) else []
    return ids


# ---------- page ----------
me = get_me()
user_id = st.query_params.get("user") or me

components.page_header("Network", "Connections")
if not user_id:
    components.empty_state("Log in to see your network, or open someone's profile.", icon=":material/hub:")
    st.stop()

center = data.get_user(user_id)
if center is None:
    st.error(f"No user with ID `{user_id}`.")
    st.stop()

is_me = user_id == me
name = display_name(center)
if me and not is_me:
    st.page_link(components.NETWORK, label="Your network", icon=":material/chevron_left:",
                 query_params={"user": me})
st.markdown(":gray[Everyone one step away through a follow or a shared team. Hover to see names and "
            "highlight someone's links, drag to rearrange, scroll to zoom, tap the legend to filter, click a "
            "person to open them.]")

network = data.ego_network(user_id)
if len(network["nodes"]) <= 1:
    components.empty_state(
        ("You aren't" if is_me else f"{name} isn't")
        + " connected to anyone yet. Follow people from Home or For you to grow the network.",
        icon=":material/hub:",
    )
    st.page_link(components.HOME, label="Find people on Home", icon=":material/search:")
    st.stop()

kind, _ = relationships(user_id, network["edges"])
profile = data.get_user_profile(user_id)
shown = len(network["nodes"]) - 1
total = len({row["user"]["userId"] for row in data.followers(user_id)}
            | {row["user"]["userId"] for row in data.following(user_id)}
            | {row["user"]["userId"] for row in data.collaborators(user_id)})
with st.container(key="network_panel", gap="medium"):
    st.html(panel_header("Your network" if is_me else f"{name}’s network",
                         f"{shown} people · {len(network['edges'])} links"
                         + (f" · showing the closest {shown} of {total:,}" if total > shown else "")))
    st.html(stat_tiles([
        ("Teammates", f"{profile['collaborators']:,}", WORKED_COLOR),
        ("Following", f"{profile['following']:,}", CATEGORIES["following"][1]),
        ("Followers", f"{profile['followers']:,}", CATEGORIES["follower"][1]),
        ("Mutual", f"{len(data.mutual_follows(user_id)):,}", CATEGORIES["mutual"][1]),
    ]))
    state = st.echarts_chart(
        chart_spec(network, user_id, kind, "You" if is_me else name),
        height=600 if len(network["nodes"]) > 25 else 520, theme=None, key=f"network_chart_{user_id}", on_select="rerun",
        alt=f"Network graph of {name} and the {len(network['nodes']) - 1} people connected to them",
    )

picked_idx = selected_ids(state)
if picked_idx and 0 <= picked_idx[0] < len(network["nodes"]):
    picked = network["nodes"][picked_idx[0]]
    if picked["userId"] != user_id:
        components.section("Selected")
        with components.card("network_selected"):
            pic, body, go = st.columns([0.9, 5, 2.5], vertical_alignment="center")
            with pic:
                components.avatar(picked)
            with body:
                components.user_link(picked)
                st.markdown(f":gray[{CATEGORIES[kind(picked['userId'])][0]}]")
            with go:
                st.page_link(components.NETWORK, label="Center here", icon=":material/hub:",
                             query_params={"user": picked["userId"]})
