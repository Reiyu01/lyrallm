"""Batch upload all .md/.txt files in a folder to Elasticsearch with embeddings.

Usage:
  python -m lyrallm.tools.upload_rag_docs_folder --folder lyrallm/tools/RAG_docs --chunk-size 600

This script uses the project's embedding provider and ElasticsearchAdapter
to upsert chunked passages into the configured ES index (vectordb.index).
"""
import argparse
import asyncio
import logging
from pathlib import Path
from typing import List

from lyrallm.embedding_provider import get_default_provider
from lyrallm.adapters.elasticsearch_adapter import ElasticsearchAdapter
from lyrallm.adapters.es_client import close_es_client


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 50) -> List[str]:
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    L = len(text)
    while start < L:
        end = min(start + chunk_size, L)
        chunks.append(text[start:end])
        if end == L:
            break
        start = end - overlap
    return chunks


async def main():
    parser = argparse.ArgumentParser(description="Upload all docs in a folder to Elasticsearch with embeddings")
    parser.add_argument("--folder", default=str(Path(__file__).resolve().parents[0] / 'RAG_docs'), help="Folder containing .md/.txt files")
    parser.add_argument("--chunk-size", type=int, default=600, help="Chunk size in characters (default 600)")
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        logger.error("Folder not found or not a directory: %s", folder)
        return

    files = list(folder.glob('*.md')) + list(folder.glob('*.txt'))
    if not files:
        logger.warning("No .md or .txt files found in %s", folder)
        return

    emb = get_default_provider()
    adapter = ElasticsearchAdapter()
    try:
        await adapter.ensure_index()

        total_chunks = 0
        for f in files:
            title = f.stem
            text = f.read_text(encoding='utf-8')
            chunks = chunk_text(text, chunk_size=args.chunk_size)
            logger.info("Uploading %s (%d chunks)", f.name, len(chunks))
            for i, chunk in enumerate(chunks, start=1):
                passage_id = f"{title}-p{i}"
                vec = await emb.embed(chunk)
                await adapter.upsert_doc(doc_id=passage_id, text=chunk, embedding=vec, intent=None, metadata={"title": title, "source_path": str(f)})
                total_chunks += 1

        logger.info("Done. Uploaded %d passages from %d files into ES index '%s'", total_chunks, len(files), adapter.index)
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise
    finally:
        # cleanup
        if hasattr(emb, 'cleanup'):
            try:
                await emb.cleanup()
            except Exception:
                pass
        try:
            await close_es_client()
        except Exception:
            pass


if __name__ == '__main__':
    asyncio.run(main())
