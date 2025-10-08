"""Shared AsyncElasticsearch client factory.

This module exposes get_es_client() which returns a singleton AsyncElasticsearch
instance configured from `config_manager`. Callers should not close the client
directly; use close_es_client() if needed during shutdown.
"""
from typing import Optional
from elasticsearch import AsyncElasticsearch
from config.config_manager import config_manager
import logging

logger = logging.getLogger(__name__)

_ES_CLIENT: Optional[AsyncElasticsearch] = None


def _get_es_config():
    cfg = config_manager.config.get('vectordb') or {}
    # fallback to storages.elasticsearch
    es_storage = config_manager.config.get('storages', {}).get('elasticsearch', {})
    endpoint = cfg.get('endpoint') or es_storage.get('endpoint') or es_storage.get('url') or 'http://127.0.0.1:9200'
    index = cfg.get('index') or es_storage.get('index') or 'semantic_index'
    dims = cfg.get('dims') or cfg.get('embedding_dims') or es_storage.get('dims') or 1536
    return {'endpoint': endpoint, 'index': index, 'dims': dims}


def get_es_client() -> AsyncElasticsearch:
    global _ES_CLIENT
    if _ES_CLIENT is None:
        cfg = _get_es_config()
        endpoint = cfg['endpoint']
        logger.info(f"Creating AsyncElasticsearch client for {endpoint}")
        # support basic auth or api_key
        es_storage = config_manager.config.get('storages', {}).get('elasticsearch', {})
        username = es_storage.get('username') or es_storage.get('user')
        password = es_storage.get('password')
        api_key = es_storage.get('api_key') or es_storage.get('apiKey') or es_storage.get('api-key')

        if username and password:
            _ES_CLIENT = AsyncElasticsearch(hosts=[endpoint], http_auth=(username, password))
        elif api_key:
            # api_key can be provided as '{id}:{api_key}' or base64; elasticsearch-py supports api_key param
            _ES_CLIENT = AsyncElasticsearch(hosts=[endpoint], api_key=api_key)
        else:
            _ES_CLIENT = AsyncElasticsearch(hosts=[endpoint])
    return _ES_CLIENT


def get_es_index() -> str:
    return _get_es_config()['index']


async def close_es_client():
    global _ES_CLIENT
    if _ES_CLIENT is not None:
        try:
            await _ES_CLIENT.close()
        except Exception:
            pass
        _ES_CLIENT = None
