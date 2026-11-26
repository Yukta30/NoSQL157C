"""Startup checks: stop with setup help instead of a stack trace when the
backend can't reach Neo4j."""

import os

import streamlit as st

ENV_HELP = """
Create a `.env` file in the project root (it's gitignored, never commit it):

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your local password>
NEO4J_DATABASE=neo4j
```

Then reload this page. See **Running the frontend** in the README.
"""

AURA_HELP = """
Neo4j AuraDB didn't answer in time. This is usually temporary (Aura sometimes
fails its first routing requests), so wait a few seconds and try again.

If it keeps happening, check that the AuraDB instance is running (free
instances pause after a few days without use) and that `NEO4J_URI` in `.env`
is right.
"""

NEO4J_HELP = """
Start your local Neo4j and reload this page. With Docker:

```
docker start teamatcha-neo4j
```

First time? See **Running the frontend** in the README.
"""


@st.cache_resource(show_spinner="Connecting to Neo4j…")
def _connect():
    # Importing backend.db creates the driver; it raises ValueError when the
    # .env settings are missing. Exceptions aren't cached, so a fixed setup is
    # picked up on the next rerun.
    from backend.db import db

    db.verify_connection()
    return True


def require_backend():
    """Stop the page with a friendly message if the backend can't be used."""
    try:
        from neo4j.exceptions import AuthError, ServiceUnavailable
    except ModuleNotFoundError:
        _fail("Python packages are missing.", "Run `pip install -r requirements.txt` and restart the app.")

    try:
        _connect()
    except ModuleNotFoundError as e:
        _fail(f"Python package `{e.name}` is missing.",
              "Run `pip install -r requirements.txt` and restart the app.")
    except ValueError:
        _fail("Neo4j settings are missing.", ENV_HELP)
    except AuthError:
        _fail("Neo4j rejected the username or password.",
              "Check `NEO4J_USERNAME` and `NEO4J_PASSWORD` in `.env`, then restart the app.")
    except ServiceUnavailable:
        uri = os.environ.get("NEO4J_URI", "")
        if "databases.neo4j.io" in uri:  # AuraDB
            _fail("Can't reach Neo4j AuraDB right now.", AURA_HELP, retry=True)
        _fail("Can't reach Neo4j.", NEO4J_HELP)


def _fail(title, help_md, retry=False):
    st.title("TeaMatcha")
    st.error(f"**{title}**")
    st.markdown(help_md)
    if retry:
        st.button("Try again", icon=":material/refresh:", type="primary")
    st.stop()
