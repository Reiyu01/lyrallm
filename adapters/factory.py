from lyrallm.config.config_manager import config_manager
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


def get_adapter(kind: str = 'analytics') -> Any:
    """Return an adapter instance for the given kind based on configuration.

    kind:
      - 'analytics' -> analytics storage adapter (postgres|elasticsearch)
      - 'vector_store' -> vector storage/search adapter (defaults to Elasticsearch)
    """
    storages_cfg = config_manager.config.get('storages', {}) or {}
    kind_cfg = storages_cfg.get(kind, {}) or {}
    adapter_type = (kind_cfg.get('type') or kind_cfg.get('adapter') or kind_cfg.get('backend') or '').lower()

    # Vector store adapter (currently Elasticsearch-backed)
    if kind == 'vector_store':
        from .elasticsearch_adapter import ElasticsearchAdapter
        return ElasticsearchAdapter()

    # Analytics adapters
    if adapter_type in ('', 'postgres', None):
        # default to Postgres adapter
        from .postgres_adapter import PostgresAdapter
        dsn = kind_cfg.get('dsn') or kind_cfg.get('url') or (config_manager.config.get('database', {}) or {}).get('dsn')
        return PostgresAdapter(dsn=dsn)

    if adapter_type == 'elasticsearch':
        # return an Elasticsearch analytics adapter
        from .elasticsearch_analytics_adapter import ElasticsearchAnalyticsAdapter
        es_cfg = kind_cfg.get('es') or kind_cfg.get('elasticsearch') or {}
        index = es_cfg.get('index') or es_cfg.get('name') or (config_manager.config.get('vectordb', {}) or {}).get('index') or 'analytics_index'
        return ElasticsearchAnalyticsAdapter(index=index)

    # future: support qdrant, mongodb, etc.
    raise ValueError(f"Unsupported adapter type for '{kind}': {adapter_type}")
