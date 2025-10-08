"""Demo script for semantic_router: ingest a few docs and run a routing example.

Usage: python scripts/semantic_router_demo.py
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure repository root (parent of semantic_kernel) is on sys.path so
# `import semantic_kernel.*` works when running the script from repo root.
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Also ensure the semantic_kernel package directory itself is available on sys.path
semantic_pkg_dir = Path(__file__).resolve().parents[1]
if str(semantic_pkg_dir) not in sys.path:
    sys.path.insert(0, str(semantic_pkg_dir))

try:
    from semantic_kernel.semantic_router import SemanticRouter
    from semantic_kernel.config.config_manager import config_manager
except ModuleNotFoundError:
    # Fallback: load modules directly by file path (robust when package layout isn't importable)
    import importlib.util
    repo_root = Path(__file__).resolve().parents[2]
    sr_path = repo_root / 'semantic_kernel' / 'semantic_router.py'
    cfg_path = repo_root / 'semantic_kernel' / 'config' / 'config_manager.py'

    spec = importlib.util.spec_from_file_location('semantic_router_module', str(sr_path))
    semantic_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semantic_mod)
    SemanticRouter = getattr(semantic_mod, 'SemanticRouter')

    spec2 = importlib.util.spec_from_file_location('config_manager_module', str(cfg_path))
    cfg_mod = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(cfg_mod)
    config_manager = getattr(cfg_mod, 'config_manager')

logging.basicConfig(level=logging.INFO)


async def main(force_fake: bool = False):
    router = SemanticRouter()

    # If requested or if provider credentials are missing, fall back to fake embedding
    provider_cfg = config_manager.config.get('embeddings', {}) or {}
    provider_name = provider_cfg.get('provider', 'fake')
    if force_fake:
        logging.warning('Force using fake embeddings (CLI flag)')
        router.embedding_provider.provider = 'fake'
    else:
        if provider_name == 'azure_openai':
            azure_cfg = config_manager.get_provider_config('azure_openai')
            if not azure_cfg.get('api_key') or not azure_cfg.get('endpoint'):
                logging.warning('Azure OpenAI credentials not found in config; falling back to fake embeddings for demo')
                router.embedding_provider.provider = 'fake'

    await router.ensure_indexes()

    # ingest a few sample docs
    docs = [
        ('doc-fin-1', '如何申請信用卡？', 'finance'),
        ('doc-qa-1', '如何重設密碼？', 'qa'),
        ('doc-sum-1', '請幫我摘要這段會議記錄', 'summarize'),
    ]
    for doc_id, text, intent in docs:
        emb = await router.embed(text)
        await router.vec_adapter.upsert_doc(doc_id, text, emb, intent=intent)

    # run routing demo
    q = '我要申請信用卡，流程為何？'
    result = await router.route(q)
    print('Reply:', result['reply'])
    print('Routing:', result['routing'])

    # query analytics
    analytics = router.analytics
    rows = await analytics.query_token_usage(10)
    print('Analytics recent rows:', rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force-fake', action='store_true', help='Force demo to use fake embeddings')
    args = parser.parse_args()
    asyncio.run(main(force_fake=args.force_fake))
