import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from frontend import components, data
from frontend.session import display_name, get_me

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

dark = st.context.theme.type == "dark"
TEXT = "#E8EAED" if dark else "#1F2328"
FOLLOW_COLOR = "#8B949E"
WORKED_COLOR = "#E0823D"
CENTER_COLOR = "#2E9E6B"
NODE_COLOR = "#4C8BF5"
ME_COLOR = "#9B59B6"

nodes = []
for n in network["nodes"]:
    is_center = n["userId"] == user_id
    color = CENTER_COLOR if is_center else (ME_COLOR if n["userId"] == me else NODE_COLOR)
    nodes.append(Node(
        id=n["userId"], label=display_name(n), title=f"@{n['username']}",
        size=34 if is_center else 22, color=color, font={"color": TEXT, "size": 18},
    ))

# Collapse A->B plus B->A follows into one double-headed edge.
follow_pairs = {(e["source"], e["target"]) for e in network["edges"] if e["type"] == "FOLLOWS"}
edges, seen = [], set()
for e in network["edges"]:
    a, b = e["source"], e["target"]
    if e["type"] == "WORKED_WITH":
        times = e.get("times") or 1
        edges.append(Edge(source=a, target=b, color=WORKED_COLOR, width=1 + times,
                          title=f"Worked together on {times} team(s)", arrows={"to": {"enabled": False}}))
    elif frozenset((a, b)) not in seen:
        seen.add(frozenset((a, b)))
        mutual = (b, a) in follow_pairs
        # Curved so it doesn't hide a straight WORKED_WITH edge between the same pair.
        edges.append(Edge(source=a, target=b, color=FOLLOW_COLOR, dashes=True, width=2,
                          smooth={"enabled": True, "type": "curvedCW", "roundness": 0.25},
                          title="Follow each other" if mutual else "Follows",
                          arrows="to, from" if mutual else "to"))

graph_col, side = st.columns([3, 1])
with side:
    st.markdown("**Legend**")
    def dot(color):
        return (f"<span style='display:inline-block;width:12px;height:12px;border-radius:50%;"
                f"background:{color};margin-right:8px;vertical-align:middle'></span>")

    def line(color, style):
        return (f"<span style='display:inline-block;width:24px;border-top:3px {style} {color};"
                f"margin-right:8px;vertical-align:middle'></span>")

    legend = [(dot(CENTER_COLOR), display_name(center))]
    if me and not is_me:
        legend.append((dot(ME_COLOR), "You"))
    legend += [
        (dot(NODE_COLOR), "Others"),
        (line(WORKED_COLOR, "solid"), "Worked together (thicker = more teams)"),
        (line(FOLLOW_COLOR, "dashed"), "Follows (arrow points to who's followed)"),
    ]
    st.html("<div style='line-height:2'>"
            + "<br>".join(f"{swatch}{label}" for swatch, label in legend) + "</div>")
    st.caption(f"{len(nodes)} people · {len(edges)} links. Drag to rearrange, scroll to zoom, "
               "click someone to open them.")

with graph_col:
    config = Config(height=560, directed=False, physics=True)
    config.width = "100%"  # Config appends "px" to whatever it's given
    config.physics["barnesHut"] = {"springLength": 180, "gravitationalConstant": -6000, "avoidOverlap": 0.3}
    selected = agraph(nodes=nodes, edges=edges, config=config)

if selected and selected != user_id:
    picked = next((n for n in network["nodes"] if n["userId"] == selected), None)
    if picked:
        with side:
            st.markdown(f"**Selected:** {display_name(picked)}")
            components.user_link(picked)
            st.page_link(components.NETWORK, label="Center the graph here", icon=":material/hub:",
                         query_params={"user": selected})
