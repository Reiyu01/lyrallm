from lyrallm.config.config_manager import config_manager
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


def get_adapter(kind: str = 'analytics') -> Any:
    """Return an adapter instance for the given kind based on configuration.

    kind: 'analytics' -> database adapter, 'vector_store' -> qdrant etc.
    """
    cfg = config_manager.config.get('storages', {})
    kind_cfg = cfg.get(kind, {})
    adapter_type = kind_cfg.get('type') or kind_cfg.get('adapter') or kind_cfg.get('backend')

    if adapter_type in (None, '', 'postgres'):
        # default to Postgres adapter
        from .postgres_adapter import PostgresAdapter
        dsn = kind_cfg.get('dsn') or kind_cfg.get('url') or config_manager.config.get('database', {}).get('dsn')
        return PostgresAdapter(dsn=dsn)

    if adapter_type == 'elasticsearch':
        # return an Elasticsearch analytics adapter
        from .elasticsearch_analytics_adapter import ElasticsearchAnalyticsAdapter
        es_cfg = kind_cfg.get('es') or kind_cfg.get('elasticsearch') or {}
    index = es_cfg.get('index') or es_cfg.get('name') or config_manager.config.get('vectordb', {}).get('index')
    return ElasticsearchAnalyticsAdapter(index=index)

    if kind == 'vector_store':
        # return an adapter for vector storage/search (Elasticsearch by default)
        from .elasticsearch_adapter import ElasticsearchAdapter
        # pass None to let adapter read config_manager for index/dims
        return ElasticsearchAdapter()

    # future: support qdrant, mongodb, etc.
    raise ValueError(f"Unsupported adapter type: {adapter_type}")
