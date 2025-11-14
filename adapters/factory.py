from config.config_manager import config_manager
from typing import Any, List
import logging

logger = logging.getLogger(__name__)


def get_adapter(kind: str = 'analytics') -> Any:
    """Return the primary adapter for a given kind (first in configured list)."""
    adapters = get_adapters(kind)
    if adapters:
        return adapters[0]

    raise ValueError(f"No adapter configured for '{kind}'")


def get_adapters(kind: str = 'analytics') -> List[Any]:
    """Return all adapters for the given kind based on configuration."""
    if kind == 'vector_store':
        from .elasticsearch_adapter import ElasticsearchAdapter
        return [ElasticsearchAdapter()]

    if kind != 'analytics':
        logger.warning("No adapters loaded for kind='%s'", kind)
        return []

    entries = _load_analytics_entries()
    adapters: List[Any] = []

    for entry in entries:
        adapter_type = (entry.get('type') or entry.get('adapter') or entry.get('backend') or '').lower()

        if adapter_type in ('', 'postgres', 'postgresql', None):
            from .postgres_adapter import PostgresAdapter
            dsn = entry.get('dsn') or entry.get('url') or (config_manager.config.get('database', {}) or {}).get('dsn')
            adapters.append(PostgresAdapter(dsn=dsn))
            continue

        if adapter_type in ('mysql', 'mysql+aiomysql', 'mariadb'):
            from .mysql_adapter import MySQLAdapter
            conn_cfg = {k: entry.get(k) for k in ('host', 'port', 'user', 'username', 'password', 'database', 'db') if entry.get(k) is not None}
            dsn = entry.get('dsn') or entry.get('url')
            adapters.append(MySQLAdapter(dsn=dsn, config=conn_cfg))
            continue

        if adapter_type == 'elasticsearch':
            from .elasticsearch_analytics_adapter import ElasticsearchAnalyticsAdapter
            es_cfg = entry.get('es') or entry.get('elasticsearch') or {}
            index = es_cfg.get('index') or es_cfg.get('name') or (config_manager.config.get('vectordb', {}) or {}).get('index') or 'analytics_index'
            adapters.append(ElasticsearchAnalyticsAdapter(index=index))
            continue

        logger.warning("Unsupported analytics adapter type '%s'", adapter_type)

    return adapters


def _load_analytics_entries() -> List[dict]:
    storages_cfg = config_manager.config.get('storages', {}) or {}
    raw = storages_cfg.get('analytics')

    if isinstance(raw, list):
        entries = [cfg or {} for cfg in raw if cfg is not None]
    elif isinstance(raw, dict):
        entries = [raw]
    elif raw is None:
        entries = []
    else:
        logger.warning("Unexpected analytics storage configuration: %s", type(raw))
        entries = []

    if entries:
        return entries

    # fallback to legacy `database` section for backward compatibility
    db_cfg = config_manager.config.get('database', {}) or {}
    if db_cfg:
        entry = db_cfg.copy()
        entry.setdefault('type', db_cfg.get('type') or 'postgres')
        entries.append(entry)

    return entries
