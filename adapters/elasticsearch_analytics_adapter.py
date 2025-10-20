"""Elasticsearch adapter for analytics events (async).

Implements async connect/close/write_token_usage/query_token_usage so it
can be used interchangeably with PostgresAdapter via the factory.
"""
from typing import Dict, Any, List, Optional
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
import traceback
import logging
import hashlib
from elasticsearch import AsyncElasticsearch
from config.config_manager import config_manager

logger = logging.getLogger(__name__)


class ElasticsearchAnalyticsAdapter:
    def __init__(self, index: Optional[str] = None):
        self.es = get_es_client()
        cfg = config_manager.config.get('storages', {}).get('elasticsearch', {})
        self.index = index or cfg.get('index') or get_es_index() or 'analytics_index'

    async def connect(self):
        try:
            exists = await self.es.indices.exists(index=self.index)
            if not exists:
                mapping = {
                    "mappings": {
                        "properties": {
                            "request_id": {"type": "keyword"},
                            "user_id": {"type": "keyword"},
                            "model_name": {"type": "keyword"},
                            "prompt_tokens": {"type": "integer"},
                            "completion_tokens": {"type": "integer"},
                            "total_tokens": {"type": "integer"},
                            "routed_intent": {"type": "keyword"},
                            "routing_model": {"type": "keyword"},
                            "request_time": {"type": "date"},
                            "metadata": {"type": "object", "enabled": True}
                        }
                    }
                }
                await self.es.indices.create(index=self.index, body=mapping)
        except Exception as e:
            logger.exception(f"Error ensuring analytics index: {e}")

    async def close(self):
        try:
            # do not close shared client here
            pass
        except Exception:
            pass

    async def write_token_usage(self, event: Dict[str, Any]):
        try:
            if "request_time" not in event:
                from datetime import datetime
                event["request_time"] = datetime.utcnow().isoformat()
            await self.es.index(index=self.index, body=event)
        except Exception as e:
            logger.exception(f"Failed to write analytics event to ES: {e}")

    async def query_token_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            body = {
                "size": limit,
                "sort": [{"request_time": {"order": "desc"}}],
                "query": {"match_all": {}}
            }
            res = await self.es.search(index=self.index, body=body)
            return [hit.get("_source", {}) for hit in res.get("hits", {}).get("hits", [])]
        except Exception:
            return []
