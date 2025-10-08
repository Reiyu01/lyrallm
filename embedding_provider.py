"""
Embedding Provider abstraction (modern full version with AzureOpenAI support)

Supported providers:
- fake: deterministic sha256-based vector (default for demo)
- openai: uses openai>=1.0.0 (or compatible proxy)
- azure_openai: uses AzureOpenAI client for Azure endpoints
- sentence_transformers: uses local SBERT model (offline)

All embedding calls are async-safe (using asyncio.to_thread).
"""

import asyncio
import hashlib
import logging
from typing import List

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    def __init__(self):
        cfg = config_manager.config.get("embeddings", {}) or {}
        self.provider = cfg.get("provider", "fake")
        self.model = cfg.get("model")
        self._st_model = None  # cache for local SBERT model

    # ==============================================================
    # 🧩 Main interface
    # ==============================================================
    async def embed(self, text: str) -> List[float]:
        provider = (self.provider or "fake").lower()

        if provider == "fake":
            return await asyncio.to_thread(self._fake_embed, text)

        if provider == "azure_openai":
            try:
                return await self._embed_azure_openai(text)
            except Exception as e:
                logger.exception(f"AzureOpenAI embedding failed: {e}")
                return await asyncio.to_thread(self._fake_embed, text)

        if provider == "openai":
            try:
                return await self._embed_openai(text)
            except Exception as e:
                logger.exception(f"OpenAI embedding failed: {e}")
                return await asyncio.to_thread(self._fake_embed, text)

        if provider in ("sentence_transformers", "sbert"):
            try:
                return await self._embed_sbert(text)
            except Exception as e:
                logger.exception(f"SentenceTransformer embedding failed: {e}")
                return await asyncio.to_thread(self._fake_embed, text)

        logger.warning(f"Unknown embedding provider: {provider}. Using fake.")
        return await asyncio.to_thread(self._fake_embed, text)

    # ==============================================================
    # ☁️ Azure OpenAI
    # ==============================================================
    async def _embed_azure_openai(self, text: str) -> List[float]:
        from openai import AzureOpenAI

        cfg = config_manager.get_provider_config("azure_openai")
        api_key = cfg.get("api_key") or cfg.get("apiKey")
        endpoint = cfg.get("endpoint") or cfg.get("base_url")
        api_version = cfg.get("api_version") or "2024-02-01"
        deployment = (
            self.model
            or cfg.get("deployment_name")
            or cfg.get("deployment")
            or cfg.get("model_id")
        )

        def _call():
            client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version,
            )
            res = client.embeddings.create(model=deployment, input=text)
            return res.data[0].embedding

        return await asyncio.to_thread(_call)

    # ==============================================================
    # 🌐 OpenAI / Proxy API
    # ==============================================================
    async def _embed_openai(self, text: str) -> List[float]:
        from openai import OpenAI

        cfg = config_manager.get_provider_config("openai")
        api_key = cfg.get("api_key") or cfg.get("apiKey")
        base_url = cfg.get("base_url") or cfg.get("endpoint")
        model = self.model or "text-embedding-3-small"

        def _call():
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = OpenAI(**kwargs)
            res = client.embeddings.create(model=model, input=text)
            return res.data[0].embedding

        return await asyncio.to_thread(_call)

    # ==============================================================
    # 🧠 Sentence Transformers (offline)
    # ==============================================================
    async def _embed_sbert(self, text: str) -> List[float]:
        from sentence_transformers import SentenceTransformer

        if self._st_model is None:
            model_name = self.model or "all-MiniLM-L6-v2"
            self._st_model = await asyncio.to_thread(SentenceTransformer, model_name)

        vec = await asyncio.to_thread(self._st_model.encode, text)
        return list(map(float, vec.tolist())) if hasattr(vec, "tolist") else list(map(float, vec))

    # ==============================================================
    # 🧪 Fake embedding fallback
    # ==============================================================
    def _fake_embed(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [float(b) / 255.0 for b in h]
        dims = config_manager.config.get("vectordb", {}).get("dims", 1536)
        if len(vec) < dims:
            vec = vec * (dims // len(vec) + 1)
        logger.debug(f"Using fake embedding for text: '{text[:30]}...' (dims={dims})")
        return vec[:dims]


_default = EmbeddingProvider()


def get_default_provider() -> EmbeddingProvider:
    return _default
