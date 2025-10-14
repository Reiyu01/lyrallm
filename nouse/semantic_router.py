"""Semantic router: embed -> vector search -> intent vote -> model selection -> model call

Minimal MVP implementation of vector-based intent routing. Now reads routing
configuration via config_manager accessors to keep keys consistent with
`models.routing.*` and `config/routing_rules.yaml`.
"""
import asyncio
from typing import List, Dict, Any
import logging

from lyrallm.config.config_manager import config_manager
from lyrallm.adapters.elasticsearch_adapter import ElasticsearchAdapter
from lyrallm.adapters.factory import get_adapter
from lyrallm.embedding_provider import get_default_provider

logger = logging.getLogger(__name__)


class SemanticRouter:
    def __init__(self):
        # Snapshot configs via accessors to avoid relying on raw dict structure
        self.routing_cfg = config_manager.get_routing_config() or {}
        self.vector_cfg = config_manager.get_vector_config() or {}
        self.fusion_cfg = config_manager.get_fusion_config() or {}
        self.vec_adapter = ElasticsearchAdapter()
        # analytics adapter via factory
        self.analytics = get_adapter('analytics')
        self.embedding_provider = get_default_provider()

    async def ensure_indexes(self):
        await self.vec_adapter.ensure_index()
        if hasattr(self.analytics, 'connect'):
            await self.analytics.connect()

    async def embed(self, text: str) -> List[float]:
        return await self.embedding_provider.embed(text)

    def resolve_intent_from_hits(self, hits: List[Dict[str, Any]], threshold: float = 0.55) -> Dict[str, Any]:
        votes = {}
        total = 0.0
        for h in hits:
            score = float(h.get('_score', 0.0))
            intent = h.get('_source', {}).get('intent')
            if not intent:
                continue
            votes[intent] = votes.get(intent, 0.0) + score
            total += score
        if total == 0:
            return {'intent': None, 'confidence': 0.0, 'votes': votes}
        best_intent = max(votes.items(), key=lambda kv: kv[1])[0]
        confidence = votes[best_intent] / total
        return {'intent': best_intent, 'confidence': confidence, 'votes': votes}

    async def route(self, query: str) -> Dict[str, Any]:
        # Embed & vector search
        vec = await self.embed(query)
        top_k = self.vector_cfg.get('top_k', config_manager.config.get('vectordb', {}).get('top_k', 5))
        hits = await self.vec_adapter.search_by_vector(vec, k=top_k)

        # Resolve intent and apply threshold from routing config
        # Default thresholds
        default_conf_threshold = 0.55
        # Prefer SLM threshold if configured (usually stricter), else no-op for vector-only
        slm_cfg = config_manager.get_slm_config() or {}
        conf_threshold = (
            slm_cfg.get('confidence_threshold')
            or self.fusion_cfg.get('uncertainty_threshold')
            or default_conf_threshold
        )

        resolved = self.resolve_intent_from_hits(hits, threshold=conf_threshold)

        default_intent = 'general'
        intent = resolved['intent'] or default_intent
        if resolved['confidence'] < conf_threshold:
            intent = default_intent

        # Choose model: try intent mapping from routing rules first
        model_id = None
        intent_map = config_manager.get_intent_mapping() or {}
        if intent_map:
            # intent_mapping can be a nested structure; try simple direct mapping first
            mapped = intent_map.get(intent)
            if isinstance(mapped, str):
                model_id = mapped
            elif isinstance(mapped, dict):
                # If preferred_models exists, pick the first available & enabled
                preferred = mapped.get('preferred_models') or []
                for cand in preferred:
                    if config_manager.is_model_enabled(cand):
                        model_id = cand
                        break

        # Fallback: scan available models that declare the intent
        if not model_id:
            for m in config_manager.get_available_models():
                if intent in (m.get('intents') or []):
                    model_id = m.get('name')
                    break

        # Final fallback to default model
        if not model_id:
            model_id = config_manager.get_default_model()

        # MVP mock reply — production path handled by ModelExecutor
        reply = f'[MOCK {model_id}] 回應：針對 "{query}"（意圖: {intent}）'

        routing = {
            'intent': intent,
            'confidence': resolved['confidence'],
            'model': model_id,
            'votes': resolved['votes'],
            'hits': hits,
        }

        # write analytics (best-effort)
        try:
            event = {
                'request_id': 'demo-1',
                'user_id': 'demo',
                'model_name': model_id,
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
                'routed_intent': intent,
                'routing_model': model_id,
                'metadata': {'query': query}
            }
            await self.analytics.write_token_usage(event)
        except Exception:
            logger.exception('Failed to write analytics event')

        return {'reply': reply, 'routing': routing}


__all__ = ['SemanticRouter']
