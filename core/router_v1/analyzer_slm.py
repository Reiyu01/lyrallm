import asyncio
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from config.config_manager import config_manager

# 導入新的資料模型
try:
    from models import SafetyLabels, ToolRequirements, ToolType, ToolPriority, SafetyLevel, ConfidentialDataType
    MODELS_AVAILABLE = True
except ImportError:
    # 向後兼容：如果 models 模組不存在，設置為 None
    SafetyLabels = None
    ToolRequirements = None
    ToolType = None
    ToolPriority = None
    SafetyLevel = None
    ConfidentialDataType = None
    MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class IntentResult:
    """
    SLM 分析結果
    
    包含基礎分析（intent, confidence, complexity）和擴展分析
    （required_tools, safety_labels, required_permissions）
    """
    # === 基礎欄位 ===
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
    
    # === 擴展欄位（Phase 1 新增） ===
    required_tools: Optional[Any] = None  # ToolRequirements 類型，但用 Any 以保持向後兼容
    safety_labels: Optional[Any] = None   # SafetyLabels 類型
    required_permissions: Optional[Dict[str, Any]] = None


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
            
            # === 解析擴展欄位（Phase 1 新增） ===
            tool_requirements = self._parse_tool_requirements(parsed)
            safety_labels = self._parse_safety_labels(parsed)
            required_permissions = parsed.get('required_permissions')
            
            result = IntentResult(
                # 基礎欄位
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
                # 擴展欄位
                required_tools=tool_requirements,
                safety_labels=safety_labels,
                required_permissions=required_permissions,
            )
            return result
        except Exception as e:
            logger.warning(f"SLMAnalyzer failed, fallback to qa_general: {e}")
            
            # 降級時也提供安全的預設值
            fallback_tools = None
            fallback_safety = None
            if MODELS_AVAILABLE:
                if ToolRequirements:
                    fallback_tools = ToolRequirements.create_no_tools()
                if SafetyLabels:
                    fallback_safety = SafetyLabels.create_safe_default()
            
            return IntentResult(
                intent='qa_general', 
                confidence=0.5, 
                complexity=3.0,
                ms=int((time.time() - start) * 1000), 
                slm_model=self.slm_cfg.get('model'),
                effective_slm_model=self.slm_cfg.get('model'), 
                fallback=True,
                # 降級時的預設值
                required_tools=fallback_tools,
                safety_labels=fallback_safety,
                required_permissions=None
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
    
    def _parse_tool_requirements(self, data: Dict[str, Any]) -> Optional[Any]:
        """
        解析工具需求
        
        Args:
            data: SLM 返回的完整 JSON 資料
            
        Returns:
            ToolRequirements 實例，如果模組不可用或沒有工具需求則返回 None
        """
        if not MODELS_AVAILABLE or ToolRequirements is None:
            return None
        
        try:
            # 檢查是否有 required_tools 欄位
            tools_data = data.get('required_tools', [])
            
            if not tools_data:
                # 沒有工具需求，返回預設的無工具實例
                return ToolRequirements.create_no_tools()
            
            # 創建 ToolRequirements 實例
            tool_requirements = ToolRequirements(needs_tools=True)
            
            # 解析每個工具需求
            for tool_item in tools_data:
                if isinstance(tool_item, dict):
                    tool_type_str = tool_item.get('tool_type', 'none')
                    priority_str = tool_item.get('priority', 'optional')
                    reason = tool_item.get('reason', '')
                    parameters = tool_item.get('parameters', {})
                    
                    # 將字串轉換為枚舉
                    try:
                        tool_type = ToolType(tool_type_str)
                    except (ValueError, AttributeError):
                        logger.warning(f"Unknown tool_type: {tool_type_str}, skipping")
                        continue
                    
                    try:
                        priority = ToolPriority(priority_str)
                    except (ValueError, AttributeError):
                        priority = ToolPriority.OPTIONAL
                    
                    # 加入工具需求
                    tool_requirements.add_tool(
                        tool_type=tool_type,
                        priority=priority,
                        reason=reason,
                        parameters=parameters
                    )
            
            return tool_requirements
            
        except Exception as e:
            logger.warning(f"Failed to parse tool_requirements: {e}, using default")
            return ToolRequirements.create_no_tools() if ToolRequirements else None
    
    def _parse_safety_labels(self, data: Dict[str, Any]) -> Optional[Any]:
        """
        解析安全標籤
        
        Args:
            data: SLM 返回的完整 JSON 資料
            
        Returns:
            SafetyLabels 實例，如果模組不可用或沒有安全標籤則返回預設安全實例
        """
        if not MODELS_AVAILABLE or SafetyLabels is None:
            return None
        
        try:
            # 檢查是否有 safety_labels 欄位
            safety_data = data.get('safety_labels', {})
            
            if not safety_data:
                # 沒有安全標籤，返回預設的安全實例
                return SafetyLabels.create_safe_default()
            
            # 解析各個安全維度
            violence_str = safety_data.get('violence', 'none')
            sexual_str = safety_data.get('sexual', 'none')
            hate_speech_str = safety_data.get('hate_speech', 'none')
            self_harm_str = safety_data.get('self_harm', 'none')
            confidential_data_str = safety_data.get('confidential_data', 'none')
            jailbreak_attempt = safety_data.get('jailbreak_attempt', False)
            risk_level_str = safety_data.get('risk_level', 'none')
            details = safety_data.get('details', [])
            
            # 將字串轉換為枚舉
            try:
                violence = SafetyLevel(violence_str)
            except (ValueError, AttributeError):
                violence = SafetyLevel.NONE
            
            try:
                sexual = SafetyLevel(sexual_str)
            except (ValueError, AttributeError):
                sexual = SafetyLevel.NONE
            
            try:
                hate_speech = SafetyLevel(hate_speech_str)
            except (ValueError, AttributeError):
                hate_speech = SafetyLevel.NONE
            
            try:
                self_harm = SafetyLevel(self_harm_str)
            except (ValueError, AttributeError):
                self_harm = SafetyLevel.NONE
            
            try:
                confidential_data = ConfidentialDataType(confidential_data_str)
            except (ValueError, AttributeError):
                confidential_data = ConfidentialDataType.NONE
            
            try:
                risk_level = SafetyLevel(risk_level_str)
            except (ValueError, AttributeError):
                risk_level = SafetyLevel.NONE
            
            # 創建 SafetyLabels 實例
            safety_labels = SafetyLabels(
                violence=violence,
                sexual=sexual,
                hate_speech=hate_speech,
                self_harm=self_harm,
                confidential_data=confidential_data,
                jailbreak_attempt=jailbreak_attempt,
                risk_level=risk_level,
                details=details if isinstance(details, list) else []
            )
            
            return safety_labels
            
        except Exception as e:
            logger.warning(f"Failed to parse safety_labels: {e}, using safe default")
            return SafetyLabels.create_safe_default() if SafetyLabels else None
