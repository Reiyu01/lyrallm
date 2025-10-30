"""Upload sample documents to Elasticsearch using rag_graph's expected schema.

This script:
- reads vectordb config from config_manager
- ensures an index with the mapping rag_graph expects (content, embedding, effective_allowed_roles, etc.)
- uses the project's embedding provider to compute embeddings
- indexes sample documents (upsert by document_id)

Run as: python -m lyrallm.tools.upload_rag_graph_docs
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List

try:
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from embedding_provider import get_default_provider
except Exception:
    # resilient imports when run as module or script
    repo_root = Path(__file__).resolve().parents[2]
    lyrallm_pkg = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(lyrallm_pkg) not in sys.path:
        sys.path.insert(0, str(lyrallm_pkg))
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from embedding_provider import get_default_provider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SAMPLE_DOCS = [
    {
        "document_id": "doc-1",
        "title": "產品 A 使用說明",
        "content": "這是一份關於產品 A 的使用說明範例，說明如何安裝與設定。",
        "document_type": "manual",
        "visibility": "public",
        "effective_allowed_roles": ["standard_user"],
        "restricted_roles": [],
        "source_path": "upload/sample/doc-1.md",
    },
    {
        "document_id": "doc-2",
        "title": "系統管理指引",
        "content": "系統管理員專用的操作指引，包含部署、監控與故障排除步驟。",
        "document_type": "guide",
        "visibility": "private",
        "effective_allowed_roles": ["admin","ops"],
        "restricted_roles": [],
        "source_path": "upload/sample/doc-2.md",
    }
]


async def ensure_mapping(es, index: str, dims: int):
    exists = await es.indices.exists(index=index)
    if exists:
        logger.info("Index %s already exists", index)
        return

    mapping = {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {"type": "text"},
                "document_id": {"type": "keyword"},
                "document_type": {"type": "keyword"},
                "visibility": {"type": "keyword"},
                "effective_allowed_roles": {"type": "keyword"},
                "restricted_roles": {"type": "keyword"},
                "source_path": {"type": "keyword"},
                "embedding": {"type": "dense_vector", "dims": dims},
                "created_at": {"type": "date"},
            }
        }
    }

    logger.info("Creating index %s with dims=%s...", index, dims)
    await es.indices.create(index=index, body=mapping, request_timeout=30)
    logger.info("Index created: %s", index)


async def main():
    cfg = config_manager.config.get('vectordb') or {}
    index = cfg.get('index') or get_es_index()
    dims = cfg.get('embedding_dims') or cfg.get('dims') or 1536

    es = get_es_client()

    # ensure mapping
    await ensure_mapping(es, index, dims)

    # embedding provider
    emb = get_default_provider()

    for d in SAMPLE_DOCS:
        text = d.get('content') or d.get('title') or ''
        logger.info('Embedding doc %s...', d['document_id'])
        vec = await emb.embed(text)
        body = {
            'title': d.get('title'),
            'content': d.get('content'),
            'document_id': d.get('document_id'),
            'document_type': d.get('document_type'),
            'visibility': d.get('visibility'),
            'effective_allowed_roles': d.get('effective_allowed_roles', []),
            'restricted_roles': d.get('restricted_roles', []),
            'source_path': d.get('source_path'),
            'embedding': vec,
        }
        # index by document_id
        await es.index(index=index, id=d['document_id'], body=body, request_timeout=30)
        logger.info('Indexed %s into %s', d['document_id'], index)

    # optional cleanup
    if hasattr(emb, 'cleanup'):
        try:
            await emb.cleanup()
        except Exception:
            pass

    # close async es client
    try:
        await es.close()
    except Exception:
        pass

    logger.info('Done uploading sample docs')


if __name__ == '__main__':
    asyncio.run(main())
