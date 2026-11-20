import atexit
import os
import time

import neo4j
from dotenv import load_dotenv
from neo4j import GraphDatabase, RoutingControl
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from neo4j.time import Date, DateTime

load_dotenv()

_DRIVER_MAJOR = int(neo4j.__version__.split(".")[0])


def _hide_deprecation_notices():
    """Driver option that hides server notices we expect: deprecations (e.g.
    the fulltext procedure) and "unrecognized" ones (e.g. querying INVITED
    before anyone has sent an invite). Driver 6 renamed the option; driver 5
    marks the new name as a preview feature, so pick by version to stay
    warning-free on both."""
    if _DRIVER_MAJOR >= 6:
        from neo4j import NotificationDisabledClassification as C
        return {"notifications_disabled_classifications": [C.DEPRECATION, C.UNRECOGNIZED]}
    from neo4j import NotificationDisabledCategory as C
    return {"notifications_disabled_categories": [C.DEPRECATION, C.UNRECOGNIZED]}


def _to_python(value):
    """Convert Neo4j temporal types to ISO strings so results are plain
    Python (safe for Streamlit, JSON, and test comparisons)."""
    if isinstance(value, (Date, DateTime)):
        return value.iso_format()
    if isinstance(value, dict):
        return {k: _to_python(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_python(v) for v in value]
    return value


class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.username = os.getenv("NEO4J_USERNAME")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.database = os.getenv("NEO4J_DATABASE")

        if not all([
            self.uri,
            self.username,
            self.password,
            self.database
        ]):
            raise ValueError(
                "Missing Neo4j environment variables. "
                "Set NEO4J_URI, NEO4J_USERNAME, "
                "NEO4J_PASSWORD, and NEO4J_DATABASE."
            )

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
            **_hide_deprecation_notices(),
        )

    def verify_connection(self, attempts=6, delay=1.0):
        """Check the database is reachable.

        Aura sometimes fails the first routing request ("Unable to retrieve
        routing information"). Queries are retried by the driver, but
        verify_connectivity() isn't, so retry here before giving up.
        Wrong credentials (AuthError) are raised immediately.
        """
        for attempt in range(1, attempts + 1):
            try:
                self.driver.verify_connectivity()
                return True
            except (ServiceUnavailable, SessionExpired):
                if attempt == attempts:
                    raise
                time.sleep(delay * attempt)

    def execute_query(self, query, parameters=None, write=False):
        """Run a Cypher query and return a list of plain dicts.

        Pass write=True for queries that create/update/delete data; reads are
        routed to Aura's read servers. The driver retries transient routing
        errors automatically.
        """
        parameters = parameters or {}

        records, summary, keys = self.driver.execute_query(
            query,
            parameters_=parameters,
            database_=self.database,
            routing_=RoutingControl.WRITE if write else RoutingControl.READ,
        )

        return [_to_python(record.data()) for record in records]

    def close(self):
        self.driver.close()


db = Neo4jConnection()
atexit.register(db.close)
