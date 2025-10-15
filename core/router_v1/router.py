import time
from typing import Dict, Any, Optional

from .analyzer_slm import SLMAnalyzer
from .rule_engine import RuleEngineV1


class RouterV1:
    """Coordinator: SLM intent+complexity -> RuleEngine candidates -> decision."""

    def __init__(self, rules_file: Optional[str] = None):
        self.analyzer = SLMAnalyzer()
        self.rules = RuleEngineV1(rules_file=rules_file)

    async def route(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        t0 = time.time()
        context = context or {}

        # Phase 1: Analyze via small LLM
        analysis = await self.analyzer.analyze(query)

        # Phase 2: Rule-based decision
        decision = self.rules.decide(analysis.intent, analysis.complexity, analysis.confidence)

        total_ms = int((time.time() - t0) * 1000)
        routing_info = {
            'intent': analysis.intent,
            'confidence': analysis.confidence,
            'complexity': analysis.complexity,
            'model': decision.selected,
            'candidates': decision.candidates,
            'trace': {
                'router': 'RouterV1',
                'analyzer': {
                    'intent': analysis.intent,
                    'confidence': analysis.confidence,
                    'complexity': analysis.complexity,
                    'ms': analysis.ms,
                },
                'decision': {
                    'selected': decision.selected,
                    'candidates': decision.candidates,
                    'threshold': decision.threshold,
                    'used_bucket': decision.used_bucket,
                    'capability_details': decision.capability_details,
                },
                'timings': {'total_ms': total_ms},
                'decision_path': ['slm_analyze', f"rules_{decision.used_bucket}"]
            }
        }
        # Include SLM model name if available for observability
        if getattr(analysis, 'slm_model', None):
            routing_info['trace']['analyzer']['slm_model'] = analysis.slm_model
        if getattr(analysis, 'effective_slm_model', None):
            routing_info['trace']['analyzer']['effective_slm_model'] = analysis.effective_slm_model
        if getattr(analysis, 'fallback', None):
            routing_info['trace']['analyzer']['fallback'] = analysis.fallback

        return routing_info
