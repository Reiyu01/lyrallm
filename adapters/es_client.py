"""Shared AsyncElasticsearch client factory with .env + config support.

Supports api_key or basic_auth and falls back to anonymous access.
"""
import os
import logging
from typing import Optional
from elasticsearch import AsyncElasticsearch
from lyrallm.config.config_manager import config_manager
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env if present
load_dotenv()

_ES_CLIENT: Optional[AsyncElasticsearch] = None


def _get_es_config():
    """Read Elasticsearch configuration from config_manager + env vars."""
    vector_cfg = config_manager.config.get('vectordb', {}) or {}
    storages_cfg = config_manager.config.get('storages', {}) or {}

    # Prefer explicit analytics storage when it is configured for Elasticsearch
    analytics_cfg = storages_cfg.get('analytics', {}) or {}
    es_storage = storages_cfg.get('elasticsearch', {}) or {}
    use_vector_cfg = True
    if not es_storage:
        if isinstance(analytics_cfg, dict):
            analytics_type = (
                analytics_cfg.get('type')
                or analytics_cfg.get('adapter')
                or analytics_cfg.get('backend')
            )
            if analytics_type and analytics_type.lower() == 'elasticsearch':
                es_storage = analytics_cfg.get('es') or analytics_cfg
                use_vector_cfg = False
    elif isinstance(es_storage, dict) and 'es' in es_storage:
        # allow nesting similar to analytics config for consistency
        es_storage = es_storage.get('es') or es_storage
        use_vector_cfg = False
    else:
        # explicit storages.elasticsearch should take precedence over vector_cfg values
        use_vector_cfg = False

    fallback_cfg = vector_cfg if use_vector_cfg else {}

    endpoint = (
        es_storage.get('endpoint')
        or es_storage.get('host')
        or fallback_cfg.get('endpoint')
        or fallback_cfg.get('host')
        or os.getenv("ES_LOCAL_URL")
        or os.getenv("ES_HOST")
        or "http://127.0.0.1:9200"
    )

    index = (
        es_storage.get('index')
        or fallback_cfg.get('index')
        or "semantic_index"
    )

    dims = (
        es_storage.get('dims')
        or fallback_cfg.get('dims')
        or fallback_cfg.get('embedding_dims')
        or 1536
    )

    api_key = (
        es_storage.get('api_key')
        or fallback_cfg.get('api_key')
        or os.getenv("ES_API_KEY")
        or os.getenv("ES_LOCAL_API_KEY")
    )

    username = (
        es_storage.get('username')
        or fallback_cfg.get('username')
        or os.getenv("ES_USERNAME")
    )

    password = (
        es_storage.get('password')
        or fallback_cfg.get('password')
        or os.getenv("ES_PASSWORD")
    )

    return {
        "endpoint": endpoint,
        "index": index,
        "dims": dims,
        "api_key": api_key,
        "username": username,
        "password": password,
    }


def get_es_client() -> AsyncElasticsearch:
    """Return a singleton AsyncElasticsearch client."""
    global _ES_CLIENT
    if _ES_CLIENT is not None:
        return _ES_CLIENT

    cfg = _get_es_config()
    endpoint = cfg["endpoint"]

    es_kwargs = {
        "hosts": [endpoint],
        "verify_certs": False,  # 可依情況改成 True
    }

    if cfg["api_key"]:
        logger.info(f"🔑 Using API key for Elasticsearch at {endpoint}")
        es_kwargs["api_key"] = cfg["api_key"]
    elif cfg["username"] and cfg["password"]:
        logger.info(f"👤 Using basic auth for Elasticsearch at {endpoint}")
        es_kwargs["basic_auth"] = (cfg["username"], cfg["password"])
    else:
        logger.warning(f"⚠️ No credentials found for Elasticsearch ({endpoint}); using anonymous mode")

    _ES_CLIENT = AsyncElasticsearch(**es_kwargs)
    logger.info(f"✅ Connected to Elasticsearch endpoint: {endpoint}")
    return _ES_CLIENT


def get_es_index() -> str:
    """Return configured Elasticsearch index name."""
    return _get_es_config()["index"]


async def close_es_client():
    """Gracefully close the singleton AsyncElasticsearch client."""
    global _ES_CLIENT
    if _ES_CLIENT is not None:
        try:
            await _ES_CLIENT.close()
            logger.info("Closed AsyncElasticsearch client.")
        except Exception as e:
            logger.warning(f"Error closing ES client: {e}")
        finally:
            _ES_CLIENT = None
