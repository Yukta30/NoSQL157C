"""Teamatcha frontend. Run from the project root:

    streamlit run frontend/app.py
"""

import sys
from pathlib import Path

# Streamlit puts frontend/ on sys.path; the backend lives one level up.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Teamatcha", page_icon="🍵", layout="wide")

from frontend import startup  # noqa: E402

startup.require_backend()

from frontend import components, session  # noqa: E402

pages = [
    st.Page("pages/discover.py", title="Discover", icon=":material/search:", default=True),
    st.Page("pages/profile.py", title="Profile", icon=":material/person:"),
    st.Page("pages/network.py", title="Network", icon=":material/hub:"),
]

nav = st.navigation(pages)
session.render_sidebar()
components.show_flash()
nav.run()
