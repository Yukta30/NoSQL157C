import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from frontend import components, data
from frontend.session import display_name, get_me

# Mid-tone colours that read on both light and dark backgrounds.
FOLLOW_COLOR = "#8B949E"
WORKED_COLOR = "#E0823D"
CENTER_COLOR = "#2E9E6B"
NODE_COLOR = "#4C8BF5"
ME_COLOR = "#9B59B6"


def build_nodes(people, center_id, me, text_color):
    nodes = []
    for p in people:
        is_center = p["userId"] == center_id
        color = CENTER_COLOR if is_center else (ME_COLOR if p["userId"] == me else NODE_COLOR)
        nodes.append(Node(
            id=p["userId"], label=display_name(p), title=f"@{p['username']}",
            size=34 if is_center else 22, color=color, font={"color": text_color, "size": 18},
        ))
    return nodes


def build_edges(links):
    """WORKED_WITH as solid lines; FOLLOWS as curved dashed arrows, with
    A->B plus B->A collapsed into one double-headed edge. The curve keeps a
    follow from hiding under a WORKED_WITH line between the same pair."""
    follow_pairs = {(e["source"], e["target"]) for e in links if e["type"] == "FOLLOWS"}
    edges, seen = [], set()
    for e in links:
        a, b = e["source"], e["target"]
        if e["type"] == "WORKED_WITH":
            times = e.get("times") or 1
            edges.append(Edge(source=a, target=b, color=WORKED_COLOR, width=1 + times,
                              title=f"Worked together on {times} team(s)",
                              arrows={"to": {"enabled": False}}))
        elif frozenset((a, b)) not in seen:
            seen.add(frozenset((a, b)))
            mutual = (b, a) in follow_pairs
            edges.append(Edge(source=a, target=b, color=FOLLOW_COLOR, dashes=True, width=2,
                              smooth={"enabled": True, "type": "curvedCW", "roundness": 0.25},
                              title="Follow each other" if mutual else "Follows",
                              arrows="to, from" if mutual else "to"))
    return edges


def _swatch(css):
    return f"<span style='display:inline-block;margin-right:8px;vertical-align:middle;{css}'></span>"


def dot(color):
    return _swatch(f"width:12px;height:12px;border-radius:50%;background:{color}")


def line(color, style):
    return _swatch(f"width:24px;border-top:3px {style} {color}")


def legend_html(center_name, show_me):
    rows = [(dot(CENTER_COLOR), center_name)]
    if show_me:
        rows.append((dot(ME_COLOR), "You"))
    rows += [
        (dot(NODE_COLOR), "Others"),
        (line(WORKED_COLOR, "solid"), "Worked together (thicker = more teams)"),
        (line(FOLLOW_COLOR, "dashed"), "Follows (arrow points to who's followed)"),
    ]
    return "<div style='line-height:2'>" + "<br>".join(s + label for s, label in rows) + "</div>"


def graph_config():
    config = Config(height=560, directed=False, physics=True)
    # Config formats width as f"{width}px", which breaks percentages.
    config.width = "100%"
    config.physics["barnesHut"] = {"springLength": 180, "gravitationalConstant": -6000,
                                   "avoidOverlap": 0.3}
    return config


# ---------- page ----------
me = get_me()
user_id = st.query_params.get("user") or me

st.title("Network")
if not user_id:
    components.empty_state("Pick a user in the sidebar to see your network, or open someone's profile.",
                           icon=":material/hub:")
    st.stop()

center = data.get_user(user_id)
if center is None:
    st.error(f"No user with ID `{user_id}`.")
    st.stop()

is_me = user_id == me
if me and not is_me:
    st.page_link(components.NETWORK, label="Your network", icon=":material/arrow_back:",
                 query_params={"user": me})
st.caption(f"{'Your' if is_me else display_name(center) + '’s'} follows and teammates, one hop out.")

network = data.ego_network(user_id)
if len(network["nodes"]) <= 1:
    components.empty_state(
        ("You aren't" if is_me else f"{display_name(center)} isn't")
        + " connected to anyone yet. Follow people from Discover or Recommendations to grow the network.",
        icon=":material/hub:",
    )
    st.page_link(components.DISCOVER, label="Go to Discover", icon=":material/search:")
    st.stop()

text_color = "#E8EAED" if st.context.theme.type == "dark" else "#1F2328"
nodes = build_nodes(network["nodes"], user_id, me, text_color)
edges = build_edges(network["edges"])

graph_col, side = st.columns([3, 1])
with side:
    st.markdown("**Legend**")
    st.html(legend_html(display_name(center), show_me=bool(me) and not is_me))
    st.caption(f"{len(nodes)} people · {len(edges)} links. Drag to rearrange, scroll to zoom, "
               "click someone to open them.")

with graph_col:
    selected = agraph(nodes=nodes, edges=edges, config=graph_config())

if selected and selected != user_id:
    picked = next((n for n in network["nodes"] if n["userId"] == selected), None)
    if picked:
        with side:
            st.markdown(f"**Selected:** {display_name(picked)}")
            components.user_link(picked)
            st.page_link(components.NETWORK, label="Center the graph here", icon=":material/hub:",
                         query_params={"user": selected})
