"""Semantic router: embed -> vector search -> intent vote -> model selection -> model call

This is a minimal implementation for demo/MVP purposes. Embedding provider is
abstracted; the demo script uses a deterministic fake embedding to keep things
self-contained.
"""
import asyncio
from typing import List, Dict, Any
from config.config_manager import config_manager
from adapters.elasticsearch_adapter import ElasticsearchAdapter
from adapters.factory import get_adapter
from embedding_provider import get_default_provider
import logging

logger = logging.getLogger(__name__)


class SemanticRouter:
    def __init__(self):
        self.cfg = config_manager.config
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
        vec = await self.embed(query)
        hits = await self.vec_adapter.search_by_vector(vec, k=self.cfg.get('vectordb', {}).get('top_k', 5))
        resolved = self.resolve_intent_from_hits(hits, threshold=self.cfg.get('intent_routing', {}).get('confidence_threshold', 0.55))
        intent = resolved['intent'] or self.cfg.get('intent_routing', {}).get('default_intent', 'general')
        if resolved['confidence'] < self.cfg.get('intent_routing', {}).get('confidence_threshold', 0.55):
            intent = self.cfg.get('intent_routing', {}).get('default_intent', 'general')

        # choose model: prefer explicit intent_map, else pick first model that lists the intent
        model_id = None
        intent_map = self.cfg.get('intent_routing', {}).get('intent_map', {})
        if intent_map:
            model_id = intent_map.get(intent)
        if not model_id:
            # scan available models for one that declares the intent
            for m in self.cfg.get('models', {}).get('available_models', []):
                if intent in (m.get('intents') or []):
                    model_id = m.get('name')
                    break
        if not model_id:
            model_id = self.cfg.get('models', {}).get('default_model')

        # For MVP, model call is mocked — in production you'd call semantic-kernel's model executor
        reply = f'[MOCK {model_id}] 回應：針對 "{query}"（意圖: {intent}）'

        routing = {'intent': intent, 'confidence': resolved['confidence'], 'model': model_id, 'votes': resolved['votes'], 'hits': hits}

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
