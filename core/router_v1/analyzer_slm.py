import asyncio
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from config.config_manager import config_manager

# 導入新的資料模型
try:
    from lyrallm.models import SafetyLabels, ToolRequirements, ToolType, ToolPriority, SafetyLevel, ConfidentialDataType
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

            # === 嘗試解析格式 ===
            # 先嘗試解析 S-category 格式（新格式）
            s_category_parsed = self._parse_s_category_format(text)
            
            if s_category_parsed:
                # 使用 S-category 格式
                logger.info("Using S-category format output")
                intent = s_category_parsed.get('intent', 'qa_general')
                confidence = s_category_parsed.get('confidence', 0.6)
                complexity = s_category_parsed.get('complexity_score', 3.0)
                
                # 解析安全標籤
                safety_category = s_category_parsed.get('safety_category', 'None')
                safety_status = s_category_parsed.get('safety_status', 'Safe')
                safety_labels = self._map_s_category_to_safety_labels(safety_category, safety_status)
                
                # S-category 格式不包含工具需求，使用預設
                tool_requirements = None
                if MODELS_AVAILABLE and ToolRequirements:
                    tool_requirements = ToolRequirements.create_no_tools()
                
                required_permissions = None
                
                parsed = s_category_parsed  # 保存原始解析結果
            else:
                # 嘗試解析 JSON 格式（舊格式）
                logger.info("Using JSON format output")
                parsed = self._safe_parse_json(text)
                intent = str(parsed.get('intent') or 'qa_general')
                confidence = float(parsed.get('confidence') or 0.6)
                complexity = float(parsed.get('complexity_score') or 3.0)
                
                # 解析擴展欄位（JSON 格式）
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
    
    def _parse_s_category_format(self, text: str) -> Optional[Dict[str, Any]]:
        """
        解析 S1-S14 安全分類的五行格式
        
        格式：
        Intent: <intent_type>
        Confidence: <0.0-1.0>
        Complexity: <1-10>
        Safety: <Safe|Unsafe>
        Category: <S1-S14 code or None>
        
        Args:
            text: SLM 返回的文字
            
        Returns:
            解析後的字典，如果不是 S-category 格式則返回 None
        """
        try:
            lines = text.strip().split('\n')
            
            # 檢查是否有必要的行
            intent_line = None
            confidence_line = None
            complexity_line = None
            safety_line = None
            category_line = None
            
            for line in lines:
                line = line.strip()
                if line.startswith('Intent:'):
                    intent_line = line
                elif line.startswith('Confidence:'):
                    confidence_line = line
                elif line.startswith('Complexity:'):
                    complexity_line = line
                elif line.startswith('Safety:'):
                    safety_line = line
                elif line.startswith('Category:'):
                    category_line = line
            
            # 至少需要 Intent, Safety, Category 三行（Confidence 和 Complexity 是新增的）
            if intent_line and safety_line and category_line:
                # 解析 Intent
                intent_value = intent_line.split(':', 1)[1].strip()
                
                # 解析 Confidence（如果存在）
                if confidence_line:
                    confidence_str = confidence_line.split(':', 1)[1].strip()
                    try:
                        confidence = float(confidence_str)
                        # 確保在 0.0-1.0 範圍內
                        confidence = max(0.0, min(1.0, confidence))
                    except ValueError:
                        logger.warning(f"Invalid confidence value: {confidence_str}, using default")
                        confidence = 0.7
                else:
                    # 如果沒有 Confidence，根據 Safety 推斷
                    safety_value = safety_line.split(':', 1)[1].strip()
                    if safety_value == 'Safe':
                        confidence = 0.9
                    else:  # Unsafe
                        confidence = 0.85
                
                # 解析 Complexity（如果存在）
                if complexity_line:
                    complexity_str = complexity_line.split(':', 1)[1].strip()
                    try:
                        complexity = float(complexity_str)
                        # 確保在 1-10 範圍內
                        complexity = max(1.0, min(10.0, complexity))
                    except ValueError:
                        logger.warning(f"Invalid complexity value: {complexity_str}, using default")
                        complexity = 3.0
                else:
                    # 如果沒有 Complexity，根據 intent 類型推斷
                    intent_temp = intent_value.lower().replace(' ', '_')
                    complexity_mapping = {
                        'code_generation': 7.0,
                        'data_analysis': 6.0,
                        'creative_writing': 5.0,
                        'text_summary': 4.0,
                        'qa_general': 3.0
                    }
                    complexity = complexity_mapping.get(intent_temp, 3.0)
                
                # 解析 Safety
                safety_value = safety_line.split(':', 1)[1].strip()
                
                # 解析 Category
                category_value = category_line.split(':', 1)[1].strip()
                
                # 映射 intent 到舊格式
                intent_mapping = {
                    # 問答類
                    'Open QA': 'open_qa',               # 一般開放式問答
                    'Closed QA': 'closed_qa',           # 封閉式問答（知識庫查詢等）
                    'Chatbot': 'chatbot',               # 對話型聊天
                    'Classification': 'classification', # 分類任務

                    # 生成類
                    'Summarization': 'text_summary',    # 摘要任務
                    'Rewrite': 'text_rewrite',          # 改寫、潤稿
                    'Text Generation': 'creative_writing',  # 文字創作
                    'Brainstorming': 'idea_generation',     # 腦力激盪／創意生成

                    # 專業應用
                    'Code Generation': 'code_generation',   # 程式生成
                    'Extraction': 'data_analysis',          # 資料萃取／分析
                    'Other': 'qa_general'                   # 預設保底任務
                }
                
                intent = intent_mapping.get(intent_value, intent_value.lower().replace(' ', '_'))
                
                return {
                    'intent': intent,
                    'confidence': confidence,
                    'complexity_score': complexity,
                    'safety_status': safety_value,
                    'safety_category': category_value,
                    'format': 's_category_v2'
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Failed to parse as S-category format: {e}")
            return None
    
    def _map_s_category_to_safety_labels(self, category: str, safety_status: str) -> Optional[Any]:
        """
        將 S1-S14 分類映射到 SafetyLabels
        
        Args:
            category: S1-S14 類別代碼或 "None"
            safety_status: Safe, Unsafe, Controversial
            
        Returns:
            SafetyLabels 實例，如果模組不可用則返回 None
        """
        if not MODELS_AVAILABLE or SafetyLabels is None:
            return None
        
        try:
            # 如果是 Safe 或 category 是 None，返回安全預設值
            if safety_status == 'Safe' or category == 'None':
                return SafetyLabels.create_safe_default()
            
            # S1-S14 映射
            category_mapping = {
                'S1': SafetyLabels(
                    violence=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S1: Violent Crimes - 暴力犯罪']
                ),
                'S2': SafetyLabels(
                    confidential_data=ConfidentialDataType.CREDENTIALS,
                    risk_level=SafetyLevel.HIGH,
                    details=['S2: Non-Violent Crimes - 非暴力犯罪（駭客、詐騙等）']
                ),
                'S3': SafetyLabels(
                    sexual=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S3: Sex-Related Crimes - 性犯罪']
                ),
                'S4': SafetyLabels(
                    sexual=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S4: Child Exploitation - 兒童剝削']
                ),
                'S5': SafetyLabels(
                    risk_level=SafetyLevel.HIGH,
                    details=['S5: Defamation - 誹謗']
                ),
                'S6': SafetyLabels(
                    confidential_data=ConfidentialDataType.MEDICAL,
                    risk_level=SafetyLevel.MEDIUM,
                    details=['S6: Specialized Advice - 專業建議（醫療/金融/法律）']
                ),
                'S7': SafetyLabels(
                    confidential_data=ConfidentialDataType.PII,
                    risk_level=SafetyLevel.HIGH,
                    details=['S7: Privacy - 隱私資料']
                ),
                'S8': SafetyLabels(
                    risk_level=SafetyLevel.MEDIUM,
                    details=['S8: Intellectual Property - 智慧財產權']
                ),
                'S9': SafetyLabels(
                    violence=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S9: Indiscriminate Weapons - 大規模殺傷武器']
                ),
                'S10': SafetyLabels(
                    hate_speech=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S10: Hate - 仇恨言論']
                ),
                'S11': SafetyLabels(
                    self_harm=SafetyLevel.CRITICAL,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S11: Suicide & Self-Harm - 自殺與自殘']
                ),
                'S12': SafetyLabels(
                    sexual=SafetyLevel.HIGH,
                    risk_level=SafetyLevel.MEDIUM,
                    details=['S12: Sexual Content - 成人性內容']
                ),
                'S13': SafetyLabels(
                    risk_level=SafetyLevel.HIGH,
                    details=['S13: Elections - 選舉假資訊']
                ),
                'S14': SafetyLabels(
                    jailbreak_attempt=True,
                    risk_level=SafetyLevel.CRITICAL,
                    details=['S14: Code Interpreter Abuse - 代碼解釋器濫用']
                ),
            }
            
            # 直接返回對應的 SafetyLabels
            return category_mapping.get(category, SafetyLabels.create_safe_default())
            
        except Exception as e:
            logger.warning(f"Failed to map S-category to SafetyLabels: {e}")
            return SafetyLabels.create_safe_default() if SafetyLabels else None
    
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
