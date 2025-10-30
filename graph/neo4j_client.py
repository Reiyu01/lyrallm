import os
import threading
from typing import Optional

from neo4j import GraphDatabase, basic_auth, Driver

try:
    # Prefer config_manager when available
    from lyrallm.config.config_manager import config_manager
except Exception:
    config_manager = None  # type: ignore


_driver_lock = threading.Lock()
_driver: Optional[Driver] = None


def _resolve_neo4j_config() -> tuple[str, str, str]:
    """Resolve Neo4j connection settings from config.yaml, then env, then sane defaults.

    Returns (uri, username, password).
    """
    uri = username = password = None  # type: ignore[assignment]

    # 1) Try config.yaml if loaded
    if config_manager is not None:
        cfg = config_manager.config or {}
        # allow either graph.neo4j or neo4j top-level namespaces
        graph_cfg = (cfg.get('graph') or {}).get('neo4j', {}) if isinstance(cfg.get('graph'), dict) else {}
        neo4j_cfg = cfg.get('neo4j', {}) if isinstance(cfg.get('neo4j'), dict) else {}
        merged = {**neo4j_cfg, **graph_cfg}
        uri = merged.get('uri') or merged.get('endpoint')
        username = merged.get('username')
        password = merged.get('password')

    # 2) Fallback to env vars
    uri = uri or os.getenv("NEO4J_URI")
    username = username or os.getenv("NEO4J_USERNAME")
    password = password or os.getenv("NEO4J_PASSWORD")

    # 3) Final fallback defaults (bolt on localhost)
    uri = uri or "bolt://127.0.0.1:7687"
    username = username or "neo4j"
    password = password or "neo4j"
    return uri, username, password


def get_neo4j_driver() -> Driver:
    """
    Return a singleton Neo4j driver based on configuration and/or environment.
    """
    global _driver

    if _driver is not None:
        return _driver

    with _driver_lock:
        if _driver is not None:
            return _driver

        uri, username, password = _resolve_neo4j_config()
        _driver = GraphDatabase.driver(uri, auth=basic_auth(username, password))
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
