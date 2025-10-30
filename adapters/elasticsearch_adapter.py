"""Async Elasticsearch adapter for vector storage and search.

Uses a shared AsyncElasticsearch client (es_client.get_es_client) and reads
endpoint/index/dims from config_manager.vectordb or storages.elasticsearch.
"""
from typing import List, Dict, Any, Optional
from lyrallm.config.config_manager import config_manager
from .es_client import get_es_client, get_es_index
import logging

logger = logging.getLogger(__name__)


class ElasticsearchAdapter:
    def __init__(self, index: Optional[str] = None, dims: Optional[int] = None):
        cfg = config_manager.config.get('vectordb') or {}
        es_storage = config_manager.config.get('storages', {}).get('elasticsearch', {})
        self.index = index or cfg.get('index') or es_storage.get('index') or get_es_index()
        self.dims = dims or cfg.get('dims') or cfg.get('embedding_dims') or es_storage.get('dims') or 1536
        self.es = get_es_client()

    async def ensure_index(self):
        try:
            exists = await self.es.indices.exists(index=self.index)
            if not exists:
                mapping = {
                    "mappings": {
                        "properties": {
                            "text": {"type": "text"},
                            "embedding": {"type": "dense_vector", "dims": self.dims},
                            "intent": {"type": "keyword"},
                            "metadata": {"type": "object", "enabled": True},
                            "created_at": {"type": "date"}
                        }
                    }
                }
                await self.es.indices.create(index=self.index, body=mapping, request_timeout=30)
        except Exception as e:
            logger.exception(f"ensure_index failed: {e}")

    async def upsert_doc(self, doc_id: str, text: str, embedding: List[float], intent: Optional[str] = None, metadata: Optional[Dict[str,Any]] = None):
        body = {
            "text": text,
            "embedding": embedding,
            "intent": intent,
            "metadata": metadata or {}
        }
        return await self.es.index(index=self.index, id=doc_id, body=body)

    async def search_by_vector(self, vector: List[float], k: int = 5) -> List[Dict[str, Any]]:
        query = {
            "size": k,
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        # guard the script with try/catch to avoid runtime errors when documents
                        # have missing/incorrect embedding fields
                        "source": "double s = 0.0; try { s = cosineSimilarity(params.query_vector, 'embedding') + 1.0; } catch (Exception e) { s = 0.0; } return s;",
                        "params": {"query_vector": vector}
                    }
                }
            }
        }
        # Increase request timeout to handle heavier vector/script_score queries
        try:
            res = await self.es.search(index=self.index, body=query, request_timeout=30)
            return res.get("hits", {}).get("hits", [])
        except Exception as e:
            logger.exception(f"search_by_vector failed: {e}")
            # Try to include more details when available
            try:
                err_text = getattr(e, 'info', None) or getattr(e, 'args', None) or str(e)
                logger.error("Elasticsearch error details: %s", err_text)
            except Exception:
                pass
            # On failure return empty results rather than crash caller
            return []
