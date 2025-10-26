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

        raw_analysis = analysis.raw if isinstance(analysis.raw, dict) else {}

        safety_category = raw_analysis.get('safety_category') or raw_analysis.get('category')
        safety_status = raw_analysis.get('safety_status') or raw_analysis.get('safety')

        safety_labels_obj = getattr(analysis, 'safety_labels', None)
        safety_labels_dict = None
        is_safe_flag: Optional[bool] = None

        if safety_labels_obj is not None:
            if hasattr(safety_labels_obj, 'to_dict'):
                try:
                    safety_labels_dict = safety_labels_obj.to_dict()  # type: ignore[attr-defined]
                except Exception:
                    safety_labels_dict = None
            elif isinstance(safety_labels_obj, dict):
                safety_labels_dict = safety_labels_obj

            if hasattr(safety_labels_obj, 'is_safe'):
                try:
                    is_safe_flag = bool(safety_labels_obj.is_safe())  # type: ignore[attr-defined]
                except Exception:
                    is_safe_flag = None

        if safety_labels_dict and isinstance(safety_labels_dict, dict) and 'is_safe' in safety_labels_dict:
            try:
                is_safe_flag = bool(safety_labels_dict.get('is_safe'))
            except Exception:
                pass

        if safety_status and isinstance(safety_status, str):
            safety_status = safety_status.strip().lower()
            if safety_status in {'safe', 'unsafe'} and is_safe_flag is None:
                is_safe_flag = safety_status == 'safe'
        else:
            safety_status = None

        if safety_status is None and is_safe_flag is not None:
            safety_status = 'safe' if is_safe_flag else 'unsafe'

        if safety_category is None and isinstance(raw_analysis.get('safety_labels'), dict):
            safety_category = raw_analysis['safety_labels'].get('category') or raw_analysis['safety_labels'].get('safety_category')

        if safety_category is None:
            safety_category = 'unknown'

        if is_safe_flag is None and safety_status is not None:
            if safety_status == 'safe':
                is_safe_flag = True
            elif safety_status == 'unsafe':
                is_safe_flag = False

        routing_info = {
            'intent': analysis.intent,
            'confidence': analysis.confidence,
            'complexity': analysis.complexity,
            'model': decision.selected,
            'candidates': decision.candidates,
            'category': safety_category,
            'safety': is_safe_flag if is_safe_flag is not None else safety_status or 'unknown',
            'safety_status': safety_status or 'unknown',
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

        if safety_labels_dict is not None:
            routing_info['safety_labels'] = safety_labels_dict

        return routing_info
