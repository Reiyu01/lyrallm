import os
import threading
from typing import Optional

from neo4j import GraphDatabase, basic_auth, Driver


_driver_lock = threading.Lock()
_driver: Optional[Driver] = None


def get_neo4j_driver() -> Driver:
    """
    Return a singleton Neo4j driver based on environment variables.

    Required environment variables:
        NEO4J_URI
        NEO4J_USERNAME
        NEO4J_PASSWORD
    """
    global _driver

    if _driver is not None:
        return _driver

    with _driver_lock:
        if _driver is not None:
            return _driver

        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")

        missing = [name for name, value in {
            "NEO4J_URI": uri,
            "NEO4J_USERNAME": username,
            "NEO4J_PASSWORD": password,
        }.items() if not value]

        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"Missing required Neo4j environment variables: {names}")

        _driver = GraphDatabase.driver(
            uri,
            auth=basic_auth(username, password),
        )
        return _driver


def close_neo4j_driver() -> None:
    """Close the shared Neo4j driver if it has been initialised."""
    global _driver
    with _driver_lock:
        if _driver is not None:
            try:
                _driver.close()
            finally:
                _driver = None
