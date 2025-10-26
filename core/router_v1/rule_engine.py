import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

import yaml
from pathlib import Path

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


@dataclass
class RuleDecision:
    selected: str
    candidates: List[str]
    threshold: float
    used_bucket: str  # "high" | "low" | "capability"
    capability_details: Optional[List[Dict[str, Any]]] = None


class RuleEngineV1:
    """Minimal rule engine: intent + complexity threshold -> candidates."""

    def __init__(self, rules_file: Optional[str] = None):
        self.rules_path = self._resolve_rules_path(rules_file)
        self.rules = self._load_rules(self.rules_path)

    def _resolve_rules_path(self, rules_file: Optional[str]) -> Path:
        if rules_file:
            p = Path(rules_file)
            if not p.is_absolute():
                p = Path(__file__).parent.parent.parent / 'config' / p.name
            return p
        # default: use main routing_rules.yaml (unified config)
        return Path(__file__).parent.parent.parent / 'config' / 'routing_rules.yaml'

    def _load_rules(self, path: Path) -> Dict[str, Any]:
        try:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            logger.warning(f"Rules file not found: {path}")
            return {}
        except Exception as e:
            logger.error(f"Failed to load rules {path}: {e}")
            return {}

    def decide(self, intent: str, complexity: float, confidence: float) -> RuleDecision:
        defaults = (self.rules.get('defaults') or {})
        confidence_floor = float(defaults.get('confidence_floor', 0.6))
        fallback_model = defaults.get('fallback_model') or (config_manager.get_default_model() or 'gpt-3.5-turbo')

        intents_cfg = self.rules.get('intents') or {}
        key_intent = intent
        if confidence < confidence_floor or key_intent not in intents_cfg:
            key_intent = 'qa_general'

        intent_cfg = intents_cfg.get(key_intent) or {}
        threshold = float(intent_cfg.get('threshold', 5.0))

        # Capability-based path: if models have iq_score we compute capability levels
        capabilities = config_manager.get_all_capabilities()
        capability_mode = bool(capabilities)
        capability_details: List[Dict[str, Any]] = []

        if capability_mode:
            # gather enabled models excluding synthetic 'auto'
            enabled_model_objs = [m for m in config_manager.get_available_models() if m.get('name') != 'auto']
            # intent-based filtering: only keep models whose intents list contains the classified intent (or it's empty meaning generic)
            intent_lower = key_intent.lower()
            filtered_models = []
            for m in enabled_model_objs:
                intents = [i.lower() for i in (m.get('intents') or [])]
                if not intents or intent_lower in intents:
                    filtered_models.append(m)
            # If nothing matches the intent, fall back to all enabled models (graceful degradation)
            model_pool = filtered_models if filtered_models else enabled_model_objs
            target = complexity
            required = round(target, 2)
            for m in model_pool:
                name = m.get('name')
                cap = config_manager.get_model_capability(name, key_intent)
                level = cap.get('level')
                if level is None:
                    continue
                diff = abs(level - target)
                intents = [i.lower() for i in (m.get('intents') or [])]
                intent_match = (not intents) or (intent_lower in intents)
                capability_details.append({
                    'model': name,
                    'level': level,
                    'target': required,
                    'required': required,
                    'meets': level >= required,
                    'diff': round(diff, 2),
                    'pr': cap.get('pr'),
                    'iq': cap.get('iq'),
                    'intent_match': intent_match,
                })
            capability_details.sort(key=lambda d: (not d['intent_match'], d['diff'], d['level']))
            candidates = [d['model'] for d in capability_details]
            selected = candidates[0] if candidates else fallback_model
            return RuleDecision(
                selected=selected,
                candidates=candidates or [fallback_model],
                threshold=threshold,
                used_bucket='capability',
                capability_details=capability_details
            )

        # Fallback to legacy high/low buckets if no capability info
        high = list(intent_cfg.get('high') or [])
        low = list(intent_cfg.get('low') or [])
        used_bucket = 'high' if complexity >= threshold else 'low'
        bucket = high if used_bucket == 'high' else low
        filtered = [m for m in bucket if config_manager.is_model_enabled(m)]
        selected = filtered[0] if filtered else (fallback_model or (bucket[0] if bucket else fallback_model))
        return RuleDecision(selected=selected, candidates=filtered or bucket or [fallback_model], threshold=threshold, used_bucket=used_bucket)
