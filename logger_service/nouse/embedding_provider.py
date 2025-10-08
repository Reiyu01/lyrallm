"""Embedding provider abstraction.

Reads embedding configuration from config_manager and exposes an async
embed(text) function. Supported providers (auto-detected if libs present):
- fake: deterministic sha256-based vector (default for demo)
- openai: uses openai. Requires OPENAI_API_KEY / OPENAI_API_BASE_URL configured
- sentence_transformers: uses sentence-transformers library (local)

The implementation uses lazy imports and runs blocking calls in a threadpool
when necessary so callers can `await embed()`.
"""
from typing import List
import asyncio
from semantic_kernel.config.config_manager import config_manager
import logging

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    def __init__(self):
        cfg = config_manager.config.get('embeddings', {}) or {}
        self.provider = cfg.get('provider', 'fake')
        self.model = cfg.get('model')
        # cache for heavy provider instances
        self._st_model = None

    async def embed(self, text: str) -> List[float]:
        if self.provider in (None, '', 'fake'):
            return await asyncio.to_thread(self._fake_embed, text)
        if self.provider == 'azure_openai':
            try:
                import openai
            except Exception:
                logger.exception('openai library not installed')
                return await asyncio.to_thread(self._fake_embed, text)

            # read azure config from providers.azure_openai
            cfg = config_manager.get_provider_config('azure_openai')
            api_key = cfg.get('api_key') or cfg.get('apiKey') or cfg.get('api_key')
            base_url = cfg.get('endpoint') or cfg.get('base_url') or cfg.get('baseUrl')
            api_version = cfg.get('api_version') or cfg.get('apiVersion')
            deployment = self.model or cfg.get('deployment_name') or cfg.get('deployment') or cfg.get('model_id')

            # configure openai for Azure
            try:
                # try to configure legacy openai library if present
                openai.api_type = 'azure'
                if base_url:
                    openai.api_base = base_url
                if api_version:
                    openai.api_version = api_version
                if api_key:
                    openai.api_key = api_key
            except Exception:
                # it's fine if setting these on the module fails; we'll try modern client below
                logger.debug('Could not configure legacy openai module for Azure, will try modern client if available')

            # Prefer the new OpenAI client (openai>=1.0). Fallback to legacy openai.Embedding.create
            try:
                from openai import OpenAI as OpenAIClient  # modern client

                def _call_azure_modern():
                    client_kwargs = {}
                    if api_key:
                        client_kwargs['api_key'] = api_key
                    if base_url:
                        client_kwargs['api_base'] = base_url
                    # api_type and api_version are recognized for Azure
                    if api_version:
                        client_kwargs['api_version'] = api_version
                    client_kwargs['api_type'] = 'azure'

                    client = OpenAIClient(**client_kwargs) if client_kwargs else OpenAIClient()
                    resp = client.embeddings.create(model=deployment, input=text)
                    # resp may be a mapping-like or object; try to access safely
                    try:
                        return resp.data[0].embedding
                    except Exception:
                        return resp['data'][0]['embedding']

                return await asyncio.to_thread(_call_azure_modern)
            except Exception:
                # fallback to legacy openai module usage
                logger.debug('Modern OpenAI client not available or failed; falling back to legacy openai API for Azure')

            # call embedding API using legacy openai if modern client failed.
            def _call_azure_legacy():
                try:
                    return openai.Embedding.create(model=deployment, input=text)['data'][0]['embedding']
                except Exception:
                    # fallback to engine param
                    return openai.Embedding.create(engine=deployment, input=text)['data'][0]['embedding']

            try:
                return await asyncio.to_thread(_call_azure_legacy)
            except Exception:
                logger.exception('Legacy openai embedding call failed (possibly openai>=1.0); using fake embedding')
                return await asyncio.to_thread(self._fake_embed, text)

        if self.provider == 'openai':
            try:
                import openai
            except Exception:
                logger.exception('openai library not installed')
                return await asyncio.to_thread(self._fake_embed, text)

            cfg = config_manager.get_provider_config('openai')
            api_key = cfg.get('api_key') or cfg.get('apiKey') or cfg.get('api_key')
            base_url = cfg.get('base_url') or cfg.get('endpoint')
            if api_key:
                openai.api_key = api_key
            if base_url:
                openai.api_base = base_url

            model = self.model or 'text-embedding-3-small'

            # Try modern OpenAI client first (openai>=1.0)
            try:
                from openai import OpenAI as OpenAIClient

                def _call_openai_modern():
                    client_kwargs = {}
                    if api_key:
                        client_kwargs['api_key'] = api_key
                    if base_url:
                        client_kwargs['api_base'] = base_url

                    client = OpenAIClient(**client_kwargs) if client_kwargs else OpenAIClient()
                    resp = client.embeddings.create(model=model, input=text)
                    try:
                        return resp.data[0].embedding
                    except Exception:
                        return resp['data'][0]['embedding']

                return await asyncio.to_thread(_call_openai_modern)
            except Exception:
                logger.debug('Modern OpenAI client not available; falling back to legacy openai API')

            # Legacy openai package fallback (catch APIRemovedInV1 and other errors)
            def _call_openai_legacy():
                resp = openai.Embedding.create(model=model, input=text)
                vec = resp['data'][0]['embedding']
                return vec

            try:
                return await asyncio.to_thread(_call_openai_legacy)
            except Exception:
                logger.exception('Legacy openai embedding call failed (possibly openai>=1.0); using fake embedding')
                return await asyncio.to_thread(self._fake_embed, text)

        if self.provider in ('sentence_transformers', 'sbert'):
            try:
                from sentence_transformers import SentenceTransformer
            except Exception:
                logger.exception('sentence-transformers not installed')
                return await asyncio.to_thread(self._fake_embed, text)

            if self._st_model is None:
                model_name = self.model or 'all-MiniLM-L6-v2'
                # load in thread
                self._st_model = await asyncio.to_thread(SentenceTransformer, model_name)

            vec = await asyncio.to_thread(self._st_model.encode, text)
            return list(map(float, vec.tolist())) if hasattr(vec, 'tolist') else list(map(float, vec))

        # fallback to fake
        return await asyncio.to_thread(self._fake_embed, text)

    def _fake_embed(self, text: str):
        import hashlib
        h = hashlib.sha256(text.encode('utf-8')).digest()
        vec = [float(b) / 255.0 for b in h]
        dims = config_manager.config.get('vectordb', {}).get('dims', 1536)
        if len(vec) < dims:
            vec = vec * (dims // len(vec) + 1)
        return vec[:dims]


_default = EmbeddingProvider()


def get_default_provider() -> EmbeddingProvider:
    return _default
