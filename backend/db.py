import os

from dotenv import load_dotenv
from neo4j import GraphDatabase, NotificationDisabledCategory, RoutingControl
from neo4j.time import Date, DateTime

load_dotenv()


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
            # Hide server deprecation notices (e.g. fulltext procedure) from logs.
            notifications_disabled_categories=[
                NotificationDisabledCategory.DEPRECATION
            ],
        )

    def verify_connection(self):
        self.driver.verify_connectivity()
        return True

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
