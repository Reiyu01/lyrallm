import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List

from lyrallm.embedding_provider import get_default_provider
from lyrallm.adapters.elasticsearch_adapter import ElasticsearchAdapter
from lyrallm.adapters.es_client import close_es_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 600) -> List[str]:
    """Very simple character-based chunker. Returns list of chunks."""
    if not text:
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        chunks.append(chunk)
        i += chunk_size
    return chunks


async def main():
    parser = argparse.ArgumentParser(description="Upload a single document (or file) to Elasticsearch with embeddings")
    parser.add_argument("--doc-id", required=True, help="Document ID to use in the index (e.g. doc_0003-p1)")
    parser.add_argument("--title", required=False, help="Title of the document")
    parser.add_argument("--content-file", required=False, help="Path to a text/markdown file containing the document content")
    parser.add_argument("--content", required=False, help="Document text inline (alternative to --content-file)")
    parser.add_argument("--use-provided-embedding", required=False, help="Path to a JSON file containing an array vector to use instead of computing embedding")
    parser.add_argument("--chunk-size", type=int, default=600, help="Chunk size in characters for splitting the document (default 600)")
    parser.add_argument("--index", required=False, help="Elasticsearch index name (defaults to configured index)")

    args = parser.parse_args()

    doc_id = args.doc_id
    title = args.title or doc_id
    index = args.index

    # Read content
    if args.content_file:
        p = Path(args.content_file)
        if not p.exists():
            logger.error("Content file not found: %s", args.content_file)
            return
        text = p.read_text(encoding='utf-8')
    elif args.content:
        text = args.content
    else:
        logger.error("Either --content-file or --content must be provided")
        return

    # Initialize adapter and ensure index
    adapter = ElasticsearchAdapter(index=index)
    await adapter.ensure_index()

    # Chunk text
    chunks = chunk_text(text, chunk_size=args.chunk_size)
    logger.info("Text split into %d chunk(s)", len(chunks))

    emb_provider = get_default_provider()

    # If user provided embedding file, read it and use for first chunk
    provided_embedding = None
    if args.use_provided_embedding:
        emb_path = Path(args.use_provided_embedding)
        if not emb_path.exists():
            logger.error("Provided embedding file not found: %s", args.use_provided_embedding)
            return
        provided_embedding = json.loads(emb_path.read_text(encoding='utf-8'))
        if not isinstance(provided_embedding, list):
            logger.error("Provided embedding file must contain a JSON array of floats")
            return

    # Upload each chunk as a separate passage id: {doc_id}-p{i}
    results = []
    for i, chunk in enumerate(chunks, start=1):
        passage_id = f"{doc_id}-p{i}"
        # use provided embedding only for the first chunk if available
        if i == 1 and provided_embedding is not None:
            emb = provided_embedding
        else:
            emb = await emb_provider.embed(chunk)
        res = await adapter.upsert_doc(doc_id=passage_id, text=chunk, embedding=emb, intent=None, metadata={"title": title})
        results.append({"id": passage_id, "result": res})
        logger.info("Indexed %s (result: %s)", passage_id, getattr(res, 'get', lambda k, d=None: 'OK')('result', 'ok'))

    print(json.dumps([{"id": r["id"], "result": str(r["result"]) } for r in results], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        # ensure ES client closed to avoid unclosed session warnings
        try:
            asyncio.run(close_es_client())
        except Exception:
            pass
