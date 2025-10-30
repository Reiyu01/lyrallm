"""Generate simulated documents, chunk them, compute embeddings and bulk upload to ES.

Usage:
  python -m lyrallm.tools.generate_and_upload --count 50 --chunk-size 500

This script will:
- create data/generated_docs/ if missing
- generate N markdown files with simulated content
- chunk each file into passages of ~chunk_size characters
- compute embeddings (using project's embedding_provider)
- bulk upload each passage as a document into the configured ES index

Be mindful of rate limits for embedding API; this script does small sleeps between batches.
"""
import argparse
import asyncio
import json
import logging
import os
import random
import string
import sys
import time
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from embedding_provider import get_default_provider
except Exception:
    # resilient imports when run as script
    repo_root = Path(__file__).resolve().parents[2]
    lyrallm_pkg = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(lyrallm_pkg) not in sys.path:
        sys.path.insert(0, str(lyrallm_pkg))
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from embedding_provider import get_default_provider


DATA_DIR = Path('data') / 'generated_docs'


def fake_paragraph(sentences: int = 5) -> str:
    words = [
        '系統', '設定', '測試', '部署', '排程', 'API', '回傳', '錯誤', '處理', '使用者', '資料', '安全', '日誌', '效能',
        '操作', '步驟', '範例', '自動化', '流水線', '監控'
    ]
    s = []
    for _ in range(sentences):
        ln = random.randint(6, 18)
        sent = ' '.join(random.choice(words) for _ in range(ln))
        if not sent.endswith('。'):
            sent = sent + '。'
        s.append(sent)
    return ' '.join(s)


def generate_file_content(idx: int) -> str:
    title = f"模擬文件 {idx} - {''.join(random.choices(string.ascii_uppercase, k=4))}"
    parts = [f"# {title}\n\n"]
    # add several sections
    for sec in range(random.randint(3, 6)):
        parts.append(f"## 節 {sec+1}\n\n")
        parts.append(fake_paragraph(random.randint(3, 8)) + '\n\n')
    # add a code block or list occasionally
    if random.random() < 0.3:
        parts.append('```\n# 示例程式碼\nprint("hello")\n```\n\n')
    return ''.join(parts)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    L = len(text)
    while start < L:
        end = min(start + chunk_size, L)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == L:
            break
        start = end - overlap
    return chunks


async def main(count: int = 50, chunk_size: int = 500, batch_size: int = 16, sleep_sec: float = 0.2):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info('Generating %d files under %s', count, DATA_DIR)
    files = []
    for i in range(1, count + 1):
        fname = DATA_DIR / f'doc_{i:04d}.md'
        content = generate_file_content(i)
        fname.write_text(content, encoding='utf-8')
        files.append(fname)

    # prepare ES client and embedding provider
    es = get_es_client()
    cfg = config_manager.config.get('vectordb') or {}
    index = cfg.get('index') or get_es_index()
    dims = cfg.get('embedding_dims') or cfg.get('dims') or 1536
    emb = get_default_provider()

    actions = []
    total_indexed = 0

    for f in files:
        text = f.read_text(encoding='utf-8')
        title = f.stem
        chunks = chunk_text(text, chunk_size=chunk_size)
        for idx, chunk in enumerate(chunks):
            doc_id = f"{f.stem}-p{idx+1}"
            # compute embedding
            vec = await emb.embed(chunk)
            # create ES action
            action = {
                "index": {
                    "_index": index,
                    "_id": doc_id
                }
            }
            source = {
                "title": title,
                "content": chunk,
                "document_id": doc_id,
                "document_type": "simulated",
                "visibility": "public",
                "effective_allowed_roles": ["standard_user"],
                "restricted_roles": [],
                "source_path": str(f),
                "embedding": vec
            }
            actions.append(json.dumps(action))
            actions.append(json.dumps(source, ensure_ascii=False))

            # flush in batches
            if len(actions) >= batch_size * 2:
                body = '\n'.join(actions) + '\n'
                try:
                    res = await es.bulk(body=body, request_timeout=60)
                    logger.info('Bulk indexed batch: took=%s items=%d', res.get('took'), len(actions)//2)
                    total_indexed += len(actions)//2
                except Exception as e:
                    logger.exception('Bulk upload failed: %s', e)
                actions = []
                await asyncio.sleep(sleep_sec)

    # final flush
    if actions:
        body = '\n'.join(actions) + '\n'
        try:
            res = await es.bulk(body=body, request_timeout=60)
            logger.info('Bulk indexed final batch: took=%s items=%d', res.get('took'), len(actions)//2)
            total_indexed += len(actions)//2
        except Exception as e:
            logger.exception('Bulk upload failed: %s', e)

    logger.info('Total indexed documents (passages): %d', total_indexed)

    # cleanup
    if hasattr(emb, 'cleanup'):
        try:
            await emb.cleanup()
        except Exception:
            pass
    try:
        await es.close()
    except Exception:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=50, help='number of files to generate')
    parser.add_argument('--chunk-size', type=int, default=500, help='approx chars per chunk')
    parser.add_argument('--batch-size', type=int, default=16, help='bulk actions per batch')
    args = parser.parse_args()
    asyncio.run(main(count=args.count, chunk_size=args.chunk_size, batch_size=args.batch_size))
