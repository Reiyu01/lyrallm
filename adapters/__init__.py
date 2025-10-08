"""Adapters package for storage backends (Postgres, Elasticsearch, etc.).
Expose a simple factory in future if multiple adapters are present.
"""

from .elasticsearch_adapter import ElasticsearchAdapter

__all__ = ["ElasticsearchAdapter"]
"""Adapters package for pluggable storage backends.

Contains adapter implementations (Postgres, etc.) and a factory to return adapters
based on configuration. Adapters expose a small async interface used by handlers.
"""

from .factory import get_adapter

__all__ = ["get_adapter"]
