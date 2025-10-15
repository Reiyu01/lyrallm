import asyncio
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    intent: str
    confidence: float
    complexity: float
    domain: Optional[str] = None
    language: Optional[str] = None
    estimated_tokens: Optional[int] = None
    ms: int = 0
    raw: Optional[Dict[str, Any]] = None
    slm_model: Optional[str] = None
    effective_slm_model: Optional[str] = None  # actual model attempted
    fallback: bool = False  # True if analyzer fell back to default values


class SLMAnalyzer:
    """Small LLM analyzer that returns intent + complexity via JSON output.

    Uses Azure OpenAI or OpenAI depending on provider config in config.yaml
    under models.routing.intent_analysis.small_model or providers.*.
    """

    def __init__(self):
        self.slm_cfg = config_manager.get_slm_config() or {}
        self.system_prompt = config_manager.get_slm_system_prompt() or (
            "You are a classifier. Return a JSON with intent, confidence, complexity_score."
        )
        self.user_template = config_manager.get_slm_user_prompt_template() or (
            'Analyze the user query: "{user_query}" and return JSON.'
        )

    async def analyze(self, query: str) -> IntentResult:
        start = time.time()
        try:
            provider = (self.slm_cfg.get('provider') or 'azure_openai').lower()
            model = self.slm_cfg.get('model') or self.slm_cfg.get('deployment_name') or 'o3-mini'
            temperature = float(self.slm_cfg.get('temperature') or 0.1)
            max_tokens = int(self.slm_cfg.get('max_tokens') or 150)
            timeout_ms = int(self.slm_cfg.get('max_inference_time') or 1500)

            content = self.user_template.format(user_query=query)

            effective_model = model
            # Minimal validation for ollama model naming (heuristic): if model not in config available_models and provider=ollama mark potential fallback.
            if provider == 'ollama':
                # Try to detect obviously fake model names (e.g., version suffix unlikely)
                # A simple heuristic: if model not referenced in any available_models entry and contains digits+"b" size token -> mark as suspect
                all_models = [m.get('name') for m in config_manager.get_all_models()]
                if model not in all_models and any(tok in model.lower() for tok in ['7b','13b','21b','70b','405b']):
                    logger.warning(f"SLMAnalyzer: configured small_model '{model}' not found in available_models; using heuristic fallback intent parsing.")
                    # We'll still attempt call; if provider errors we'll catch and set fallback flag.
            if provider == 'azure_openai':
                from openai import AzureOpenAI
                p = config_manager.get_provider_config('azure_openai')
                if not p or not p.get('api_key') or not p.get('endpoint'):
                    raise RuntimeError('Azure OpenAI credentials not configured')
                client = AzureOpenAI(
                    api_key=p.get('api_key'),
                    azure_endpoint=p.get('endpoint'),
                    api_version=p.get('api_version')
                )
                def _call():
                    kwargs = dict(
                        model=self.slm_cfg.get('deployment_name') or model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": content},
                        ],
                        max_tokens=max_tokens,
                    )
                    # Some reasoning models (o3-family, o1) disallow temperature
                    if not any(x in (self.slm_cfg.get('deployment_name') or model) for x in ['o3', 'o1']):
                        kwargs['temperature'] = temperature
                    res = client.chat.completions.create(**kwargs)
                    return res.choices[0].message.content
                text = await asyncio.to_thread(_call)
            elif provider == 'ollama':
                # Use Ollama local API: POST /api/chat with model and messages
                import http.client
                import urllib.parse
                p = config_manager.get_provider_config('ollama') or {}
                base_url = p.get('base_url', 'http://localhost:11434')
                parsed = urllib.parse.urlparse(base_url)
                host = parsed.hostname or 'localhost'
                port = parsed.port or 11434
                scheme = parsed.scheme
                path = '/api/chat'

                payload = json.dumps({
                    'model': model,
                    'messages': [
                        {'role': 'system', 'content': self.system_prompt},
                        {'role': 'user', 'content': content}
                    ],
                    'stream': False,
                    'options': {
                        'temperature': temperature
                    }
                })

                def _call_ollama():
                    conn_cls = http.client.HTTPSConnection if scheme == 'https' else http.client.HTTPConnection
                    conn = conn_cls(host, port, timeout=30)
                    headers = {'Content-Type': 'application/json'}
                    conn.request('POST', path, body=payload, headers=headers)
                    resp = conn.getresponse()
                    body = resp.read().decode('utf-8', errors='ignore')
                    conn.close()
                    try:
                        data = json.loads(body)
                        # Chat API returns {'message': {'role': 'assistant','content': '...'}, ...}
                        msg = data.get('message', {}).get('content')
                        return msg or body
                    except Exception:
                        return body
                text = await asyncio.to_thread(_call_ollama)
            else:
                from openai import OpenAI
                p = config_manager.get_provider_config('openai')
                if not p or not p.get('api_key'):
                    raise RuntimeError('OpenAI API key not configured')
                def _call():
                    client = OpenAI(api_key=p.get('api_key'), base_url=p.get('base_url') or p.get('endpoint'))
                    kwargs = dict(
                        model=model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": content},
                        ],
                        max_tokens=max_tokens,
                    )
                    if not any(x in model for x in ['o3', 'o1']):
                        kwargs['temperature'] = temperature
                    res = client.chat.completions.create(**kwargs)
                    return res.choices[0].message.content
                text = await asyncio.to_thread(_call)

            parsed = self._safe_parse_json(text)
            intent = str(parsed.get('intent') or 'qa_general')
            confidence = float(parsed.get('confidence') or 0.6)
            complexity = float(parsed.get('complexity_score') or 3.0)
            result = IntentResult(
                intent=intent,
                confidence=confidence,
                complexity=complexity,
                domain=parsed.get('domain'),
                language=parsed.get('language'),
                estimated_tokens=int(parsed.get('estimated_tokens') or 0),
                ms=int((time.time() - start) * 1000),
                raw=parsed,
                slm_model=model,
                effective_slm_model=effective_model,
            )
            return result
        except Exception as e:
            logger.warning(f"SLMAnalyzer failed, fallback to qa_general: {e}")
            return IntentResult(
                intent='qa_general', confidence=0.5, complexity=3.0,
                ms=int((time.time() - start) * 1000), slm_model=self.slm_cfg.get('model'),
                effective_slm_model=self.slm_cfg.get('model'), fallback=True
            )

    def _safe_parse_json(self, text: str) -> Dict[str, Any]:
        try:
            # Try extract JSON substring
            s = text.strip()
            start = s.find('{')
            end = s.rfind('}')
            if start >= 0 and end >= 0 and end > start:
                s = s[start:end+1]
            return json.loads(s)
        except Exception:
            return {}
