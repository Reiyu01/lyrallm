"""Simple smoke test for Elasticsearch settings and connectivity.

This prints the resolved ES configuration (as read by adapters.es_client._get_es_config)
and then attempts to call client.info() to verify connectivity and auth.

Run via: python tools/test_elasticsearch.py
"""
import asyncio
import json
import logging
from pathlib import Path

# Import the ES client with a resilient strategy so the script works when run both
# as a module (python -m lyrallm.tools.test_elasticsearch) and as a plain script.
try:
    # Preferred: package-relative import when running as a module
    from lyrallm.adapters import es_client
except Exception:
    try:
        # Fallback: allow running when the package root is on PYTHONPATH
        from adapters import es_client
    except Exception:
        # Last resort: add the repo root (two levels up from this file) to sys.path
        import sys
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from adapters import es_client

from lyrallm.config.config_manager import config_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_elasticsearch")


def print_resolved_config():
    try:
        cfg = es_client._get_es_config()
    except Exception as e:
        logger.exception("Failed getting ES config: %s", e)
        cfg = {}
    # redact secrets for printing
    cfg_redacted = cfg.copy()
    if cfg_redacted.get('api_key'):
        cfg_redacted['api_key'] = '<REDACTED>'
    if cfg_redacted.get('password'):
        cfg_redacted['password'] = '<REDACTED>'
    print("Resolved ES config:")
    print(json.dumps(cfg_redacted, indent=2, ensure_ascii=False))


async def run_info():
    try:
        client = es_client.get_es_client()
        info = await client.info()
        # ObjectApiResponse (async client) is not JSON serializable directly.
        # Try common conversions: to_dict(), raw attribute, or dict()
        info_obj = None
        try:
            if hasattr(info, 'to_dict'):
                info_obj = info.to_dict()
            elif hasattr(info, 'raw'):
                info_obj = info.raw
            else:
                info_obj = dict(info)
        except Exception:
            # Fallback: convert repr
            info_obj = {'info_repr': repr(info)}

        print('\nElasticsearch info:')
        print(json.dumps(info_obj, indent=2, ensure_ascii=False))
    except Exception as e:
        logger.exception("Failed to connect to Elasticsearch: %s", e)
    finally:
        # ensure we close the shared client to avoid unclosed session warnings
        try:
            if hasattr(es_client, 'close_es_client'):
                await es_client.close_es_client()
            else:
                client_obj = getattr(es_client, '_ES_CLIENT', None)
                if client_obj is not None and hasattr(client_obj, 'close'):
                    await client_obj.close()
        except Exception:
            pass


if __name__ == '__main__':
    print_resolved_config()
    asyncio.run(run_info())
