"""Shared AsyncElasticsearch client factory with .env + config support.

Supports api_key or basic_auth and falls back to anonymous access.
"""
import os
import logging
from typing import Optional
from elasticsearch import AsyncElasticsearch
from config.config_manager import config_manager
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env if present
load_dotenv()

_ES_CLIENT: Optional[AsyncElasticsearch] = None


def _get_es_config():
    """Read Elasticsearch configuration from config_manager + env vars."""
    cfg = config_manager.config.get('vectordb', {}) or {}
    es_storage = config_manager.config.get('storages', {}).get('elasticsearch', {})

    endpoint = (
        cfg.get('endpoint')
        or cfg.get('host')
        or es_storage.get('endpoint')
        or es_storage.get('host')
        or os.getenv("ES_LOCAL_URL")
        or os.getenv("ES_HOST")
        or "http://127.0.0.1:9200"
    )

    index = (
        cfg.get('index')
        or es_storage.get('index')
        or "semantic_index"
    )

    dims = (
        cfg.get('dims')
        or cfg.get('embedding_dims')
        or es_storage.get('dims')
        or 1536
    )

    api_key = (
        cfg.get('api_key')
        or es_storage.get('api_key')
        or os.getenv("ES_API_KEY")
        or os.getenv("ES_LOCAL_API_KEY")
    )

    username = (
        cfg.get('username')
        or es_storage.get('username')
        or os.getenv("ES_USERNAME")
    )

    password = (
        cfg.get('password')
        or es_storage.get('password')
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
