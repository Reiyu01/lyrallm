from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional, Any, AsyncGenerator
from pydantic import BaseModel
import time
import logging
import json
import asyncio
import uuid
from datetime import datetime
import httpx
from lyrallm.auth.dependencies import RequestSecurityContext, get_request_security_context
from lyrallm.config.config_manager import config_manager
from lyrallm.core import get_default_executor

# Token tracking imports - 高性能版本

from lyrallm.logger_service import TokenUsage
from lyrallm.logger_service.event_bus import event_bus
from lyrallm.logger_service.token_calculator import compute_token_usage

# Semantic Kernel imports

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings

# Multi-Agent System imports

from agents.practical_agent_orchestrator import create_practical_agent_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# 新增請求日誌功能
class RequestLoggingMiddleware:

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def log_request_body(self, request: Request):
        """記錄原始請求內容"""
        if request.url.path == "/api/chat/completions":
            try:
                body = await request.body()
                if body:
                    body_str = body.decode('utf-8')
                    self.logger.info(f"🔍 原始請求內容: {body_str}")

                    # 解析 JSON 並檢查 features
                    try:
                        data = json.loads(body_str)
                        if 'features' in data:
                            self.logger.info(f"🎯 發現 features 參數: {data['features']}")
                        else:
                            self.logger.info(f"❌ 請求中沒有 features 參數")
                            self.logger.info(f"📋 請求包含的字段: {list(data.keys())}")
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ JSON 解析失敗: {e}")
            except Exception as e:
                self.logger.error(f"❌ 讀取請求內容失敗: {e}")
request_logger = RequestLoggingMiddleware()

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

# 簡化的 Features 模型 - 只處理已知參數
class Features(BaseModel):
    web_search: Optional[bool] = False
    image_generation: Optional[bool] = False
    rag_search: Optional[bool] = False
    code_interpreter: Optional[bool] = False  # 保留欄位以維持相容性

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None
    features: Optional[Features] = None  # 前端功能控制

    # 允許額外字段，避免前端發送的其他字段造成解析錯誤
    class Config:
        extra = "allow"

class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage

    # Option A: expose metadata including routing info back to frontend

    meta: Optional[Dict[str, Any]] = None

    # Convenience: also expose routing_info on top-level for easy access

    routing_info: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    model: Optional[str] = None
    feedback: str


def _extract_text_from_stream_payload(payload: Dict[str, Any]) -> str:
    """Extract text delta from streaming payload."""
    if not isinstance(payload, dict):
        return ""

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] or {}
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

    for field in ("response", "content", "text"):
        value = payload.get(field)
        if isinstance(value, str):
            return value
    return ""


def _format_sse(payload: Any) -> bytes:
    """Serialize payload to SSE data line."""
    try:
        data = json.dumps(payload, ensure_ascii=False)
    except Exception:
        data = json.dumps({"error": "serialization_failed"}, ensure_ascii=False)
    return f"data: {data}\n\n".encode("utf-8")

# All kernel management now handled by unified ModelExecutor for consistency
async def _load_plugins(self, kernel: sk.Kernel, model_name: str, features: Optional[Features] = None) -> int:
    """在這個架構中，Plugin 由 Agent Orchestrator 管理，此方法主要用於基本聊天模式"""
    try:
        # 在新架構中，Plugin 載入由 Agent Orchestrator 負責
        # 這裡只處理非 Agent 模式的基本聊天需求
        plugins_loaded = 0
        # 如果啟用了 Agent 模式，Plugin 由 Agent Orchestrator 載入
        if features and (features.web_search or features.image_generation or features.rag_search or features.code_interpreter):
            logger.info(f"🎭 [{model_name}] Agent 模式啟用，Plugin 由 Agent Orchestrator 管理")
            return plugins_loaded

        # 基本聊天模式不需要載入額外的 Plugin

        logger.info(f"💬 [{model_name}] 基本聊天模式，無需載入額外 Plugin")
        return plugins_loaded
    except Exception as e:
        logger.error(f"❌ [{model_name}] Plugin loading check failed: {e}")
        return 0

def _log_plugin_status(self, kernel: sk.Kernel, model_name: str):
    """記錄 plugin 狀態"""
    try:
        plugins = list(kernel.plugins)
        if plugins:
            logger.info(f"🔌 [{model_name}] Loaded Plugins:")
            for plugin in plugins:
                try:

                    # 安全地取得 plugin 資訊

                    plugin_name = getattr(plugin, 'name', str(plugin))

                    # 嘗試取得 functions 資訊

                    functions = []
                    if hasattr(plugin, 'functions'):
                        if hasattr(plugin.functions, 'values'):
                            functions = [f.name for f in plugin.functions.values() if hasattr(f, 'name')]
                        elif hasattr(plugin.functions, 'keys'):
                            functions = list(plugin.functions.keys())
                    elif hasattr(plugin, '_functions'):
                        functions = list(plugin._functions.keys()) if plugin._functions else []
                    logger.info(f"  - {plugin_name}: {functions if functions else 'no functions found'}")
                except Exception as e:
                    logger.warning(f"  - {plugin}: error getting functions - {e}")
        else:
            logger.info(f"🔌 [{model_name}] No plugins loaded - Basic chat mode")
    except Exception as e:
        logger.error(f"❌ [{model_name}] Error logging plugin status: {e}")

def _analyze_response_metadata(self, response, model_name: str) -> dict:
    """分析回應中的 metadata，檢查函數調用等資訊"""
    metadata = {
        "functions_called": [],
        "agent_used": False,
        "response_length": len(str(response[0].content)) if response else 0
    }
    try:

        # 檢查是否有 metadata

        if response and len(response) > 0 and hasattr(response[0], 'metadata') and response[0].metadata:
            function_calls = response[0].metadata.get('function_calls', [])
            if function_calls:
                metadata["functions_called"] = [fc.get('name', 'unknown') for fc in function_calls if isinstance(fc, dict)]
                metadata["agent_used"] = True
                logger.info(f"🎯 [{model_name}] Functions called: {metadata['functions_called']}")
            else:
                logger.info(f"💡 [{model_name}] No functions called - direct response")
        else:
            logger.debug(f"📄 [{model_name}] No metadata in response")
    except Exception as e:
        logger.warning(f"⚠️  [{model_name}] Error analyzing response metadata: {e}")
    return metadata

async def get_kernel_for_model(self, model_name: str, features: Optional[Features] = None) -> sk.Kernel:
    """取得指定模型的 Semantic Kernel 實例，根據 features 動態載入 plugins"""

    # 建立基礎 kernel（不包含 plugins）

    kernel = await self._get_base_kernel_for_model(model_name)

    # 根據 features 動態載入 plugins

    if features:
        plugins_count = await self._load_plugins(kernel, model_name, features)
        logger.info(f"🔌 [{model_name}] Loaded {plugins_count} plugins based on frontend features")
        self._log_plugin_status(kernel, model_name)
    else:
        logger.info(f"🔌 [{model_name}] No features specified, basic chat mode only")
    return kernel

async def _get_base_kernel_for_model(self, model_name: str) -> sk.Kernel:
    """取得指定模型的基礎 Semantic Kernel 實例（不包含 plugins）"""

    # 基礎 kernel 可以快取，因為它不包含 plugins

    cache_key = f"base_{model_name}"
    if cache_key in self.kernels:

        # 返回基礎 kernel 的副本，避免污染快取

        base_kernel = self.kernels[cache_key]

        # 建立新的 kernel 實例，但使用相同的服務配置

        new_kernel = sk.Kernel()

        # 複製服務

        for service in base_kernel.services.values():
            new_kernel.add_service(service)
        return new_kernel

    # 建立新的 kernel

    kernel = sk.Kernel()
    model_config = config_manager.get_model_by_name(model_name)
    if not model_config:
        raise ValueError(f"Model '{model_name}' not found in configuration")
    provider = model_config.get('provider')

    # Azure OpenAI

    if provider == 'azure_openai':
        service_id = f"azure_openai_{model_name}"
        kernel.add_service(
            AzureChatCompletion(
                service_id=service_id,
                deployment_name=model_config.get('deployment_name'),
                endpoint=model_config.get('endpoint'),
                api_key=model_config.get('api_key'),
                api_version=model_config.get('api_version')
            )
        )

    # Azure AI Foundry (may use model_id instead of deployment_name)

    elif provider == 'azure_ai_foundry':
        service_id = f"azure_ai_foundry_{model_name}"
        kernel.add_service(
            AzureChatCompletion(
                service_id=service_id,
                deployment_name=model_config.get('model_id') or model_config.get('deployment_name'),
                endpoint=model_config.get('endpoint'),
                api_key=model_config.get('api_key'),
                api_version=model_config.get('api_version')
            )
        )

    # OpenAI (官方)

    elif provider == 'openai':
        service_id = f"openai_{model_name}"
        kernel.add_service(
            OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_name,
                api_key=model_config.get('api_key'),
                base_url=model_config.get('endpoint')
            )
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # 快取基礎 kernel

    self.kernels[cache_key] = kernel

    # 返回副本

    new_kernel = sk.Kernel()
    for service in kernel.services.values():
        new_kernel.add_service(service)
    return new_kernel

async def create_chat_completion(self, model_name: str, messages: List[ChatMessage],
                                temperature: float = 0.7, max_tokens: Optional[int] = None,
                                features: Optional[Features] = None) -> ChatCompletionResponse:
    """使用 Semantic Kernel 建立聊天完成"""
    try:
        kernel = await self.get_kernel_for_model(model_name, features)
        model_config = config_manager.get_model_by_name(model_name)

        # 取得聊天完成服務

        chat_completion = kernel.get_service(type=ChatCompletionClientBase)

        # 建立聊天歷史

        chat_history = ChatHistory()

        # 添加訊息到聊天歷史

        for message in messages:
            if message.role == "system":
                chat_history.add_system_message(message.content)
            else:
                chat_history.add_message(
                    ChatMessageContent(role=message.role, content=message.content)
                )

        # 擷取請求設定

        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )

        # 動態設定參數 - 不會覆寫任何模型設定

        provider = model_config.get('provider')

        # Azure OpenAI 統一不嘗試設定 temperature 以避免衝突

        if provider != 'azure_openai':
            try:
                execution_settings.temperature = temperature
            except Exception as e:
                logger.warning(f"無法設定 temperature: {e}")

        # 動態處理 max_tokens vs max_completion_tokens

        max_tokens_value = max_tokens or model_config.get('max_completion_tokens') or model_config.get('max_tokens', 4096)

        # 先嘗試使用 max_completion_tokens，若失敗再嘗試使用 max_tokens

        token_set = False
        if model_config.get('max_completion_tokens'):
            try:
                execution_settings.max_completion_tokens = max_tokens_value
                token_set = True
                logger.info(f"使用 max_completion_tokens: {max_tokens_value}")
            except Exception as e:
                logger.warning(f"無法設定 max_completion_tokens: {e}")

        # 檢查是否有 plugin（工具）可用
        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):

            # 重設 function choice 行為，但先記錄可用的細節

            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
            logger.info(f"🎭 [{model_name}] Agent mode enabled with {len(list(kernel.plugins))} plugins")

            # 記錄可用的函數

            for plugin in kernel.plugins:
                plugin_name = getattr(plugin, 'name', str(plugin))
                logger.info(f"✅ [{model_name}] Plugin '{plugin_name}' available for function calls")
        elif hasattr(execution_settings, 'function_choice_behavior'):
            logger.info(f"🧩 [{model_name}] Basic chat mode (no plugins available)")
        else:
            logger.warning(f"⚠️  [{model_name}] FunctionChoiceBehavior not supported by this execution settings type")

        # 執行聊天完成
        # 如果使用了函數呼叫，需要傳入 kernel 實例

        if plugins_available and hasattr(execution_settings, 'function_choice_behavior') and execution_settings.function_choice_behavior:
            response = await chat_completion.get_chat_message_contents(
                chat_history=chat_history,
                settings=execution_settings,
                kernel=kernel
            )
        else:
            response = await chat_completion.get_chat_message_contents(
                chat_history=chat_history,
                settings=execution_settings
            )
        if not response:
            raise ValueError("No response from chat completion service")

        # 檢查是否有函數呼叫產生

        response_metadata = self._analyze_response_metadata(response, model_name)

        # 轉換為 OpenAI 兼容格式

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=str(response[0].content)),
            finish_reason="stop"
        )

        # 估算 token 使用量（Semantic Kernel 可能不提供詳細計算）

        prompt_tokens = sum(len(msg.content.split()) for msg in messages)
        completion_tokens = len(str(response[0].content).split())
        usage = ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=model_name,
            choices=[choice],
            usage=usage
        )
    except Exception as e:
        logger.error(f"Semantic Kernel 聊天完成失敗: {e}")
        raise

# Event-driven: use in-process event bus to publish TokenUsage events

from lyrallm.logger_service.event_bus import event_bus as global_event_bus

async def track_token_usage(request_id: str, model_name: str, usage: Optional[ChatCompletionUsage],
                          start_time: datetime, status: str, user_id: Optional[str] = None, messages: Optional[List[ChatMessage]] = None, response_text: Optional[str] = None):
    """
    簡化的 Token Usage 追蹤 - SK 只負責建立和回傳
    所有計費相關邏輯都由 Logger Service 自行處理
    """
    try:

        # SK 只提供基本的資料來源

        cost_usd = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if usage and getattr(usage, 'total_tokens', 0) > 0:

            # Use provider/SDK provided usage when available

            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens

            # 簡單成本估算 (will be overridden by compute_token_usage if used)

            model_config = config_manager.get_model_by_name(model_name)
            if model_config:
                input_cost_per_1k = model_config.get('input_cost_per_1k', 0.001)
                output_cost_per_1k = model_config.get('output_cost_per_1k', 0.002)
                cost_usd = (prompt_tokens / 1000) * input_cost_per_1k + (completion_tokens / 1000) * output_cost_per_1k
        else:

            # Fallback to estimator (tiktoken) or provider usage extractor via token_calculator

            model_config = config_manager.get_model_by_name(model_name)
            msgs = messages or []
            resp_text = response_text or ''
            calc = compute_token_usage(None, msgs, model_name, model_config, resp_text)
            prompt_tokens = calc.get('prompt_tokens', 0)
            completion_tokens = calc.get('completion_tokens', 0)
            total_tokens = calc.get('total_tokens', prompt_tokens + completion_tokens)
            cost_usd = calc.get('cost_usd', 0.0)

        # 建立資料物件

        token_usage = TokenUsage(
            request_id=request_id,
            timestamp=start_time,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=round(cost_usd, 6),
            user_id=user_id,
            endpoint="/api/chat/completions",
            status=status
        )

        # 發布事件到 EventBus，由 logger_service 的 consumer 處理寫入 DB/ELK

        try:

            # publish the pydantic model as dict for downstream consumers

            global_event_bus.publish(token_usage.model_dump())
            logger.debug(f"[{request_id}] Token usage published to EventBus")
        except Exception as e:

            # SK 不應該中斷 logging 流程，此處只做記錄

            logger.error(f"[{request_id}] Token tracking error: {e}")
    except Exception as e:

        # 捕捉資料準備階段的錯誤，不影響主要流程

        logger.error(f"[{request_id}] Token tracking preparation error: {e}")
        return

def get_queue_status():
    """Return EventBus status for health checks."""
    try:

        # event_bus provides helpers

        return {
            "queue_length": global_event_bus.queue_size(),
            "subscribers": global_event_bus.subscriber_count(),
            "running": global_event_bus.is_running()
        }
    except Exception as e:
        logger.error(f"Failed to get event bus status: {e}")
        return {"queue_length": -1, "subscribers": 0, "running": False}

async def handle_agent_mode_request(request: ChatCompletionRequest, security_ctx: RequestSecurityContext = None) -> ChatCompletionResponse:
    """
    流程示意 #004: Agent 模式處理入口 - 初始化 Agent 協調器
    處理 Agent 模式請求 - 使用多 Agent 協作
    """
    request_id = f"agent_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()
    try:
        logger.info(f"[{request_id}] 進入 Agent 模式處理")

        # 取得使用者最新訊息

        user_messages = [msg.content for msg in request.messages if msg.role == 'user']
        if not user_messages:
            raise ValueError("No user message found")
        user_input = user_messages[-1]

        # Resolve model name (handle 'auto' routing) and 建立聊天服務
        model_name_to_use = request.model
        try:
            if request.model == 'auto':
                # Use ModelExecutor routing logic to pick the best model for 'auto'
                from lyrallm.core.model_executor import ModelExecutor
                executor = ModelExecutor()
                routed_model, routing_info = await executor._route_model(request.messages, request_id)
                logger.info(f"[{request_id}] Auto-routed model: {routed_model}")
                model_name_to_use = routed_model or config_manager.get_default_model()

        except Exception as route_err:
            logger.warning(f"[{request_id}] Auto routing failed, falling back to requested model '{request.model}': {route_err}")

        model_config = config_manager.get_model_by_name(model_name_to_use)
        if not model_config:
            raise ValueError(f"Model '{model_name_to_use}' not found")
        chat_service = await create_chat_service_for_model(model_name_to_use, model_config)

        # 流程示意 #005: 建立Agent協調器
        orchestrator = await create_practical_agent_orchestrator(chat_service)
        if not orchestrator:
            raise ValueError("無法初始化 Agent 協調器")

        # 流程示意 #006: 動態能力註冊 - 根據 features 增加對應功能
        capabilities_added = []
        if request.features:
            if request.features.web_search:
                if orchestrator.add_web_search_capability():
                    capabilities_added.append("web_search")
            if request.features.rag_search:
                if orchestrator.add_rag_capability():
                    capabilities_added.append("rag_search")
            if request.features.image_generation:

                # TODO: 增加圖像生成能力

                logger.info(f"[{request_id}] Image generation 功能尚未實作")
                pass
            if request.features.code_interpreter:

                # TODO: 增加代碼解釋器能力

                logger.info(f"[{request_id}] Code interpreter 功能尚未實作")
                pass
        logger.info(f"[{request_id}] Agent 模式使用功能: {capabilities_added}")

        # 構建 features dict
        features_dict = {}
        if request.features:

            if request.features.web_search:
                features_dict["web_search"] = True
            if request.features.rag_search:
                features_dict["rag_search"] = True
            if request.features.image_generation:
                features_dict["image_generation"] = True
            if request.features.code_interpreter:
                features_dict["code_interpreter"] = True
            logger.info(f"[{request_id}] Agent 模式使用功能: {list(features_dict.keys())}")

        # 流程示意 #007: 實際使用者請求 - 交給 Agent 協調器處理
        try:
            # Protect agent processing from hanging by imposing a timeout.
            # If the orchestrator (or its agents) blocks (e.g., external MCP not available),
            # we timeout and allow the caller to fall back to standard model execution.
            result = await asyncio.wait_for(
                orchestrator.process_request(user_input, features_dict, security_ctx=security_ctx),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Agent processing timed out (possible external tool/unavailable web search). Falling back to standard execution.")

        # 流程示意 #050: 格式轉換 - 將Agent結果轉為OpenAI兼容格式
        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=result),
            finish_reason="stop"
        )

        # 估算 token 使用量

        prompt_tokens = sum(len(msg.content.split()) for msg in request.messages)
        completion_tokens = len(result.split())
        usage = ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
        response = ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=model_name_to_use,
            choices=[choice],
            usage=usage
        )

        # 記錄對話歷史（如有）

        conversation_history = orchestrator.get_conversation_history()
        if conversation_history:
            logger.info(f"[{request_id}] Agent 對話歷史: {len(conversation_history)} 次互動")
        logger.info(f"[{request_id}] Agent 模式處理完成")
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Agent 模式處理失敗: {e}")
        import traceback

        logger.error(f"[{request_id}] 例外追蹤: {traceback.format_exc()}")
        raise

async def create_chat_service_for_model(model_name: str, model_config: Dict[str, Any]) -> ChatCompletionClientBase:
    """
    為指定模型建立聊天服務
    """
    provider = model_config.get('provider')
    if provider == 'azure_openai':
        return AzureChatCompletion(
            service_id=f"azure_openai_{model_name}",
            deployment_name=model_config.get('deployment_name'),
            endpoint=model_config.get('endpoint'),
            api_key=model_config.get('api_key'),
            api_version=model_config.get('api_version')
        )
    elif provider == 'azure_ai_foundry':
        return AzureChatCompletion(
            service_id=f"azure_ai_foundry_{model_name}",
            deployment_name=model_config.get('model_id') or model_config.get('deployment_name'),
            endpoint=model_config.get('endpoint'),
            api_key=model_config.get('api_key'),
            api_version=model_config.get('api_version')
        )
    elif provider == 'openai':
        return OpenAIChatCompletion(
            service_id=f"openai_{model_name}",
            ai_model_id=model_name,
            api_key=model_config.get('api_key'),
            base_url=model_config.get('endpoint')
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

# 流程示意 #001: API 請求入口 - 接收聊天完成請求
# 此端是整個聊天流程的起點，所有的請求都會經過這裡
@router.post("/api/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """
    建立聊天完成 - 支援基本模式和 Agent 模式
    """

    # 生成唯一請求 ID

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()

    # 記錄原始請求

    await request_logger.log_request_body(raw_request)
    try:
        logger.info(f"[{request_id}] 收到聊天請求 - 模型: {request.model}")
        request_dict = request.model_dump()

        # Enforce role-based model access

        if not security_ctx.allows_model(request.model):
            logger.warning(
                "[%s] Role '%s' is not allowed to invoke model '%s'",
                request_id,
                security_ctx.role.name,
                request.model,
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed",
                    "model": request.model,
                    "role": security_ctx.role.name,
                },
            )

        # 特別檢查 features 欄位

        logger.info(f"[{request_id}] Features 原始值: {request.features}")
        logger.info(f"[{request_id}] Features 型別: {type(request.features)}")
        if request.features:
            logger.info(f"[{request_id}] Features 內容: web_search={request.features.web_search}, image_generation={request.features.image_generation}, rag_search={request.features.rag_search}, code_interpreter={request.features.code_interpreter}")
            feature_payload = request.features.model_dump(exclude_none=True)
            requested_features = [key for key, value in feature_payload.items() if isinstance(value, bool) and value]
            disallowed_features = [feature for feature in requested_features if not security_ctx.allows_feature(feature)]
            if disallowed_features:
                logger.warning(
                    "[%s] Role '%s' is not permitted to use features %s",
                    request_id,
                    security_ctx.role.name,
                    disallowed_features,
                )
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_not_allowed",
                        "features": disallowed_features,
                        "role": security_ctx.role.name,
                    },
                )
            logger.info(f"[{request_id}] Features 內容: web_search={request.features.web_search}, image_generation={request.features.image_generation}, rag_search={request.features.rag_search}, code_interpreter={request.features.code_interpreter}")

        # 流程示意 #002: 模型選擇分支 - 判斷使用 Agent 模式或直接模型
        agent_mode_enabled = False
        if request.features:

            # 檢查是否有任何功能被使用

            agent_mode_enabled = (request.features.web_search or
                                request.features.image_generation or
                                request.features.rag_search or
                                request.features.code_interpreter)
            if agent_mode_enabled:
                logger.info(f"[{request_id}] 偵測到 features 參數，進入 Agent 模式")
                enabled_features = []
                if request.features.web_search:
                    enabled_features.append("web_search")
                if request.features.image_generation:
                    enabled_features.append("image_generation")
                if request.features.rag_search:
                    enabled_features.append("rag_search")
                if request.features.code_interpreter:
                    enabled_features.append("code_interpreter")
                logger.info(f"[{request_id}] 使用功能: {enabled_features}")
        else:
            logger.info(f"[{request_id}] 前端未指定功能，使用基本聊天模式")

        # 流程示意 #003A: Agent 模式分支 - 進入多 Agent 協作流程
        if agent_mode_enabled:
            try:
                # 如果前端要求串流，則 Agent 模式提供 SSE 串流支援
                if request.stream:
                    async def agent_stream_generator():
                        done_sent = False
                        final_text = ""
                        try:
                            # 嘗試先取得 Router 的預測分配（例如 'auto' 模式）
                            routed_model = None
                            routing_info = None
                            try:
                                if request.model == 'auto':
                                    from lyrallm.core.model_executor import ModelExecutor
                                    _executor = ModelExecutor()
                                    routed_model, routing_info = await _executor._route_model(request.messages, request_id)
                                    logger.info(f"[{request_id}] Agent stream - routed to: {routed_model}")
                                    # 立刻告知前端路由資訊
                                    info_payload = {
                                        "type": "info",
                                        "model": routed_model or request.model,
                                        "routing_info": routing_info or {}
                                    }
                                    yield _format_sse(info_payload)

                            except Exception as route_err:
                                logger.warning(f"[{request_id}] Router early resolution failed: {route_err}")

                            # 呼叫現有的 Agent 處理函式（會回傳完整結果）
                            response = await handle_agent_mode_request(request, security_ctx)
                            if response and isinstance(response.choices, list) and response.choices:
                                final_text = response.choices[0].message.content or ""

                            # 將回傳分段送出，以模擬 streaming 行為
                            chunk_size = 256
                            for i in range(0, len(final_text), chunk_size):
                                piece = final_text[i:i+chunk_size]
                                payload = {
                                    "type": "delta",
                                    "model": response.model if response else request.model,
                                    "text": piece,
                                }
                                yield _format_sse(payload)
                                await asyncio.sleep(0)

                            # 傳送 final payload
                            final_payload = {
                                "type": "final",
                                "model": response.model if response else request.model,
                                "text": final_text,
                                "usage": response.usage.model_dump() if (response and response.usage) else None,
                            }
                            yield _format_sse(final_payload)
                            yield b"data: [DONE]\n\n"
                            done_sent = True

                            # 追蹤 token 使用
                            try:
                                await track_token_usage(
                                    request_id=request_id,
                                    model_name=response.model if response else request.model,
                                    usage=response.usage if response else None,
                                    start_time=start_time,
                                    status="success",
                                    user_id=security_ctx.user_id,
                                    messages=request.messages,
                                    response_text=final_text or ""
                                )
                            except Exception as metric_error:
                                logger.error(f"[{request_id}] Failed to record agent streaming token usage: {metric_error}")

                        except Exception as stream_err:
                            logger.error(f"[{request_id}] Agent streaming error: {stream_err}")
                            err_payload = {"error": str(stream_err), "model": request.model}
                            yield _format_sse(err_payload)
                            if not done_sent:
                                yield b"data: [DONE]\n\n"

                    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
                    return StreamingResponse(agent_stream_generator(), media_type="text/event-stream", headers=headers)

                # 非串流情況仍然保留原始行為
                response = await handle_agent_mode_request(request, security_ctx)

                # 追蹤 token 使用
                await track_token_usage(
                    request_id=request_id,
                    model_name=request.model,
                    usage=response.usage,
                    start_time=start_time,
                    status="success",
                    user_id=security_ctx.user_id,
                    messages=request.messages,
                    response_text=response.choices[0].message.content
                )
                return response
            except Exception as e:
                logger.error(f"[{request_id}] Agent 模式失敗，嘗試降級到標準模式: {e}")

                # 降級到標準模型
                agent_mode_enabled = False

        # 流程示意 #003B: 直接模型分支 - 使用基本聊天功能（不使用特殊功能）
        if not agent_mode_enabled:
            logger.info(f"[{request_id}] Processing with standard model execution")

            # Log feature settings for debugging

            if request.features:
                enabled_features = [
                    name for name, enabled in [
                        ("web_search", request.features.web_search),
                        ("image_generation", request.features.image_generation),
                        ("code_interpreter", request.features.code_interpreter)
                    ] if enabled
                ]
                logger.info(f"[{request_id}] Frontend features: {enabled_features or 'none'}")
            else:
                logger.info(f"[{request_id}] No frontend features specified, using basic chat mode")

            executor = get_default_executor()

            if request.stream:
                stream_iterator = executor.stream_generate(
                    model_name=request.model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    features=request.features,
                    security_ctx=security_ctx
                )

                full_text: str = ""
                final_payload: Optional[Dict[str, Any]] = None
                streamed_model: Optional[str] = None

                async def stream_generator():
                    nonlocal full_text, final_payload, streamed_model
                    done_sent = False
                    try:
                        async for event in stream_iterator:
                            if not isinstance(event, dict):
                                continue
                            event_type = event.get("type")
                            payload = event.get("payload") or {}
                            if not isinstance(payload, dict):
                                continue

                            if event_type == "info":
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint
                                yield _format_sse(payload)
                                continue

                            if event_type == "delta":
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint
                                text_piece = _extract_text_from_stream_payload(payload)
                                if text_piece:
                                    full_text += text_piece
                                yield _format_sse(payload)
                                continue

                            if event_type == "final":
                                final_payload = payload
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint

                                if not full_text:
                                    final_text = _extract_text_from_stream_payload(payload)
                                    if final_text:
                                        full_text = final_text
                                if not full_text and isinstance(payload.get("text"), str):
                                    full_text = payload["text"]

                                yield _format_sse(payload)
                                continue

                            # Unexpected payload, forward as-is
                            if payload:
                                yield _format_sse(payload)

                        yield b"data: [DONE]\n\n"
                        done_sent = True
                    except Exception as stream_error:
                        logger.error(f"[{request_id}] Streaming generator error: {stream_error}")
                        error_payload = {
                            "error": str(stream_error),
                            "model": streamed_model or request.model,
                        }
                        yield _format_sse(error_payload)
                        if not done_sent:
                            yield b"data: [DONE]\n\n"
                            done_sent = True
                    finally:
                        status = "success" if final_payload else "system_error"
                        tracked_model = streamed_model
                        if final_payload:
                            tracked_model = final_payload.get("model", tracked_model)
                        if not tracked_model:
                            tracked_model = request.model

                        usage_payload: Optional[Dict[str, Any]] = None
                        if final_payload and isinstance(final_payload.get("usage"), dict):
                            usage_payload = final_payload["usage"]
                        if not usage_payload and full_text:
                            try:
                                usage_payload = executor._calculate_usage(request.messages, full_text)  # type: ignore[attr-defined]
                            except Exception:
                                usage_payload = None

                        if final_payload and not full_text and isinstance(final_payload.get("text"), str):
                            full_text = final_payload["text"]

                        usage_obj: Optional[ChatCompletionUsage] = None
                        if isinstance(usage_payload, dict):
                            usage_obj = ChatCompletionUsage(
                                prompt_tokens=int(usage_payload.get("prompt_tokens", 0)),
                                completion_tokens=int(usage_payload.get("completion_tokens", 0)),
                                total_tokens=int(usage_payload.get("total_tokens", 0)),
                            )

                        try:
                            await track_token_usage(
                                request_id=request_id,
                                model_name=tracked_model,
                                usage=usage_obj,
                                start_time=start_time,
                                status=status,
                                user_id=security_ctx.user_id,
                                messages=request.messages,
                                response_text=full_text or ""
                            )
                        except Exception as metric_error:
                            logger.error(f"[{request_id}] Failed to record streaming token usage: {metric_error}")

                headers = {
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                }
                return StreamingResponse(stream_generator(), media_type="text/event-stream", headers=headers)

            exec_result = await executor.generate(
                model_name=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                features=request.features,
                security_ctx=security_ctx
            )

            actual_model = exec_result.get('model', request.model)
            routing_meta = exec_result.get('meta', {}).get('routing_info', {})
            choice = ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role='assistant',
                    content=exec_result['choices'][0]['message']['content']
                ),
                finish_reason=exec_result['choices'][0].get('finish_reason', 'stop')
            )
            usage_obj = ChatCompletionUsage(
                prompt_tokens=exec_result.get('usage', {}).get('prompt_tokens', 0),
                completion_tokens=exec_result.get('usage', {}).get('completion_tokens', 0),
                total_tokens=exec_result.get('usage', {}).get('total_tokens', 0)
            )
            response = ChatCompletionResponse(
                id=f"{request_id}-{exec_result.get('id', int(time.time()))}",
                created=exec_result.get('created', int(time.time())),
                model=actual_model,
                choices=[choice],
                usage=usage_obj,
                meta=exec_result.get('meta', {}),
                routing_info=routing_meta or exec_result.get('meta', {}).get('routing_info', None)
            )

            await track_token_usage(
                request_id=request_id,
                model_name=actual_model,
                usage=response.usage,
                start_time=start_time,
                status="success",
                user_id=security_ctx.user_id,
                messages=request.messages,
                response_text=response.choices[0].message.content
            )

            if routing_meta:
                raw_conf = routing_meta.get('confidence')
                confidence_str = f"{raw_conf:.3f}" if isinstance(raw_conf, (int, float)) else "n/a"
                logger.info(
                    f"[{request_id}] Auto-routing: {actual_model} "
                    f"(intent={routing_meta.get('intent')}, confidence={confidence_str})"
                )
            logger.info(
                f"[{request_id}] Chat completion successful - Model: {actual_model}, "
                f"Tokens: {usage_obj.total_tokens}, "
                f"Latency: {exec_result.get('meta', {}).get('latency_ms', 0)}ms"
            )
            return response
    except HTTPException:

        # 被拒絕的請求

        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="http_error",
            user_id=security_ctx.user_id,
            messages=request.messages
        )
        raise
    except Exception as e:

        # 系統錯誤記錄

        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="system_error",
            user_id=security_ctx.user_id,
            messages=request.messages
        )
        logger.error(f"[{request_id}] 聊天完成失敗: {e}")
        import traceback

        logger.error(f"[{request_id}] 例外追蹤: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@router.get("/api/chat/models")
async def get_chat_models(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """取得支援的聊天模型列表"""
    try:
        available_models = config_manager.get_available_models()
        visible_models = [
            model for model in available_models
            if security_ctx.allows_model(model.get("name", ""))
        ]
        chat_models = []
        for model in visible_models:
            chat_models.append({
                "id": model["name"],
                "name": model["name"],
                "provider": model.get("provider", ""),
                "description": model.get("description", ""),
                "max_tokens": model.get("max_completion_tokens") or model.get("max_tokens", 4096),
                "temperature": model.get("temperature", 0.7)
            })
        names = [model["name"] for model in chat_models]
        logger.info(f"Chat models available: {names}")
        return {
            "object": "list",
            "data": chat_models
        }
    except Exception as e:
        logger.error(f"取得聊天模型失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat models: {str(e)}")

@router.post("/api/chat/feedback")
async def submit_chat_feedback(
    payload: FeedbackRequest,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """Record lightweight chat feedback for routing adjustments."""
    try:
        logger.info("[feedback] role=%s user=%s conversation=%s message=%s model=%s feedback=%s",
                    security_ctx.role.name,
                    security_ctx.user_id,
                    payload.conversation_id,
                    payload.message_id,
                    payload.model,
                    payload.feedback)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Feedback handler failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")

@router.get("/api/chat/health")
async def chat_health_check():
    """聊天服務健康檢查 + Token Tracking 狀態"""
    try:
        event_status = get_queue_status()

        # check postgres health (non-blocking wrapper)

        from lyrallm.logger_service.db_client import postgres_health

        try:
            pg_health = await postgres_health()
        except Exception:
            pg_health = {"connected": False}

        # 取得已載入的模型數量

        available_models = config_manager.get_available_models()
        visible_models = [
            model for model in available_models
            if security_ctx.allows_model(model.get("name", ""))
        ]
        models_count = len([m for m in available_models if m.get('enabled', False)])
        services = {
            "semantic_kernel": "ready",
            "event_bus": "running" if event_status.get("running") else "stopped",
            "postgres": "connected" if pg_health.get("connected") else "disconnected",
            "token_tracking": "enabled",
        }

        # Ollama health check (for SLM analyzer)

        ollama_models: List[str] = []
        try:
            ollama_cfg = config_manager.get_provider_config("ollama") or {}
            base_url = (ollama_cfg.get("base_url") or "").strip()
            if base_url:
                if not base_url.startswith("http://") and not base_url.startswith("https://"):
                    base_url = f"http://{base_url}"
                url = base_url.rstrip("/") + "/api/tags"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
                if resp.status_code == 200:
                    services["ollama"] = "reachable"
                    try:
                        payload = resp.json()
                        ollama_models = [m.get("name") for m in payload.get("models", []) if m.get("name")]
                    except Exception:
                        ollama_models = []
                else:
                    services["ollama"] = f"unreachable:{resp.status_code}"
            else:
                services["ollama"] = "not_configured"
        except Exception as ollama_error:
            services["ollama"] = f"error:{ollama_error}"
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": services,
            "event_bus_info": event_status,
            "postgres_info": pg_health,
            "models_loaded": models_count,
            "ollama_models": ollama_models
        }
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

@router.get("/api/chat/plugins")
async def get_plugin_info():
    """取得 Plugin 配置資訊"""
    try:
        plugin_info = plugin_manager.get_plugin_info()
        return {
            "status": "success",
            "data": plugin_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"取得 Plugin 資訊失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get plugin info: {str(e)}")

@router.post("/api/chat/plugins/reload")
async def reload_plugin_config():
    """重新載入 Plugin 配置（熱更新）"""
    try:
        plugin_manager.reload_config()
        plugin_info = plugin_manager.get_plugin_info()
        return {
            "status": "success",
            "message": "Plugin configuration reloaded successfully",
            "data": plugin_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"重新載入 Plugin 配置失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload plugin config: {str(e)}")

@router.get("/api/chat/features")
async def get_available_features():
    """取得所有可用的功能列表"""
    try:

        # 簡化的功能列表

        available_features = ["web_search", "image_generation"]

        # 取得每個功能的詳細資訊

        feature_details = [
            {
                "name": "web_search",
                "description": "Web Search Plugin - 提供線上搜尋功能",
                "require_config": True,
                "plugin_id": "web_search"
            },
            {
                "name": "image_generation",
                "description": "Image Generation Plugin - 提供圖像生成功能",
                "require_config": True,
                "plugin_id": "image_generation"
            }
        ]
        return {
            "status": "success",
            "data": {
                "available_features": available_features,
                "feature_details": feature_details,
                "total_count": len(available_features)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"取得可用功能失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get available features: {str(e)}")
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional, Any, AsyncGenerator
from pydantic import BaseModel
import time
import logging
import json
import asyncio
import uuid
from datetime import datetime
import httpx
from lyrallm.auth.dependencies import RequestSecurityContext, get_request_security_context
from lyrallm.config.config_manager import config_manager
from lyrallm.core import get_default_executor

# Token tracking imports - 高性能版本

from lyrallm.logger_service import TokenUsage
from lyrallm.logger_service.event_bus import event_bus
from lyrallm.logger_service.token_calculator import compute_token_usage

# Semantic Kernel imports

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.connectors.ai import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings

# Multi-Agent System imports

from agents.practical_agent_orchestrator import create_practical_agent_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# 新增請求日誌功能
class RequestLoggingMiddleware:

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def log_request_body(self, request: Request):
        """記錄原始請求內容"""
        if request.url.path == "/api/chat/completions":
            try:
                body = await request.body()
                if body:
                    body_str = body.decode('utf-8')
                    self.logger.info(f"🔍 原始請求內容: {body_str}")

                    # 解析 JSON 並檢查 features
                    try:
                        data = json.loads(body_str)
                        if 'features' in data:
                            self.logger.info(f"🎯 發現 features 參數: {data['features']}")
                        else:
                            self.logger.info(f"❌ 請求中沒有 features 參數")
                            self.logger.info(f"📋 請求包含的字段: {list(data.keys())}")
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ JSON 解析失敗: {e}")
            except Exception as e:
                self.logger.error(f"❌ 讀取請求內容失敗: {e}")
request_logger = RequestLoggingMiddleware()

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

# 簡化的 Features 模型 - 只處理已知參數
class Features(BaseModel):
    web_search: Optional[bool] = False
    image_generation: Optional[bool] = False
    rag_search: Optional[bool] = False
    code_interpreter: Optional[bool] = False  # 保留欄位以維持相容性

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[List[str]] = None
    features: Optional[Features] = None  # 前端功能控制

    # 允許額外字段，避免前端發送的其他字段造成解析錯誤
    class Config:
        extra = "allow"

class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage

    # Option A: expose metadata including routing info back to frontend

    meta: Optional[Dict[str, Any]] = None

    # Convenience: also expose routing_info on top-level for easy access

    routing_info: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    model: Optional[str] = None
    feedback: str


def _extract_text_from_stream_payload(payload: Dict[str, Any]) -> str:
    """Extract text delta from streaming payload."""
    if not isinstance(payload, dict):
        return ""

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] or {}
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content

    for field in ("response", "content", "text"):
        value = payload.get(field)
        if isinstance(value, str):
            return value
    return ""


def _format_sse(payload: Any) -> bytes:
    """Serialize payload to SSE data line."""
    try:
        data = json.dumps(payload, ensure_ascii=False)
    except Exception:
        data = json.dumps({"error": "serialization_failed"}, ensure_ascii=False)
    return f"data: {data}\n\n".encode("utf-8")

# All kernel management now handled by unified ModelExecutor for consistency
    async def _load_plugins(self, kernel: sk.Kernel, model_name: str, features: Optional[Features] = None) -> int:
        """在這個架構中，Plugin 由 Agent Orchestrator 管理，此方法主要用於基本聊天模式"""
        try:
            # 在新架構中，Plugin 載入由 Agent Orchestrator 負責
            # 這裡只處理非 Agent 模式的基本聊天需求
            plugins_loaded = 0
            # 如果啟用了 Agent 模式，Plugin 由 Agent Orchestrator 載入
            if features and (features.web_search or features.image_generation or features.rag_search or features.code_interpreter):
                logger.info(f"🎭 [{model_name}] Agent 模式啟用，Plugin 由 Agent Orchestrator 管理")
                return plugins_loaded

            # 基本聊天模式不需要載入額外的 Plugin

            logger.info(f"💬 [{model_name}] 基本聊天模式，無需載入額外 Plugin")
            return plugins_loaded
        except Exception as e:
            logger.error(f"❌ [{model_name}] Plugin loading check failed: {e}")
            return 0

def _log_plugin_status(self, kernel: sk.Kernel, model_name: str):
    """記錄 plugin 狀態"""
    try:
        plugins = list(kernel.plugins)
        if plugins:
            logger.info(f"🔌 [{model_name}] Loaded Plugins:")
            for plugin in plugins:
                try:

                    # å®‰å…¨åœ°ç²å– plugin è³‡è¨Š

                    plugin_name = getattr(plugin, 'name', str(plugin))

                    # å˜—è©¦ç²å– functions è³‡è¨Š

                    functions = []
                    if hasattr(plugin, 'functions'):
                        if hasattr(plugin.functions, 'values'):
                            functions = [f.name for f in plugin.functions.values() if hasattr(f, 'name')]
                        elif hasattr(plugin.functions, 'keys'):
                            functions = list(plugin.functions.keys())
                    elif hasattr(plugin, '_functions'):
                        functions = list(plugin._functions.keys()) if plugin._functions else []
                    logger.info(f"  - {plugin_name}: {functions if functions else 'no functions found'}")
                except Exception as e:
                    logger.warning(f"  - {plugin}: error getting functions - {e}")
        else:
            logger.info(f"🔌 [{model_name}] No plugins loaded - Basic chat mode")
    except Exception as e:
        logger.error(f"❌ [{model_name}] Error logging plugin status: {e}")

def _analyze_response_metadata(self, response, model_name: str) -> dict:
    """分析回應中的 metadata，檢查函數調用等資訊"""
    metadata = {
        "functions_called": [],
        "agent_used": False,
        "response_length": len(str(response[0].content)) if response else 0
    }
    try:

        # æª¢æŸ¥æ˜¯å¦æœ‰ metadata

        if response and len(response) > 0 and hasattr(response[0], 'metadata') and response[0].metadata:
            function_calls = response[0].metadata.get('function_calls', [])
            if function_calls:
                metadata["functions_called"] = [fc.get('name', 'unknown') for fc in function_calls if isinstance(fc, dict)]
                metadata["agent_used"] = True
                logger.info(f"🎯 [{model_name}] Functions called: {metadata['functions_called']}")
            else:
                logger.info(f"💡 [{model_name}] No functions called - direct response")
        else:
            logger.debug(f"📄 [{model_name}] No metadata in response")
    except Exception as e:
        logger.warning(f"⚠️  [{model_name}] Error analyzing response metadata: {e}")
    return metadata

async def get_kernel_for_model(self, model_name: str, features: Optional[Features] = None) -> sk.Kernel:
    """å–å¾—æŒ‡å®šæ¨¡åž‹çš„ Semantic Kernel å¯¦ä¾‹ï¼Œæ ¹æ“š features å‹•æ…‹è¼‰å…¥ plugins"""

    # å‰µå»ºåŸºç¤Ž kernelï¼ˆä¸åŒ…å« pluginsï¼‰

    kernel = await self._get_base_kernel_for_model(model_name)

    # æ ¹æ“š features å‹•æ…‹è¼‰å…¥ plugins

    if features:
        plugins_count = await self._load_plugins(kernel, model_name, features)
        logger.info(f"🔌 [{model_name}] Loaded {plugins_count} plugins based on frontend features")
        self._log_plugin_status(kernel, model_name)
    else:
        logger.info(f"🔌 [{model_name}] No features specified, basic chat mode only")
    return kernel

async def _get_base_kernel_for_model(self, model_name: str) -> sk.Kernel:
    """å–å¾—æŒ‡å®šæ¨¡åž‹çš„åŸºç¤Ž Semantic Kernel å¯¦ä¾‹ï¼ˆä¸åŒ…å« pluginsï¼‰"""

    # åŸºç¤Ž kernel å¯ä»¥å¿«å–ï¼Œå› ç‚ºå®ƒä¸åŒ…å« plugins

    cache_key = f"base_{model_name}"
    if cache_key in self.kernels:

        # è¿”å›žåŸºç¤Ž kernel çš„å‰¯æœ¬ï¼Œé¿å…æ±¡æŸ“å¿«å–

        base_kernel = self.kernels[cache_key]

        # å‰µå»ºæ–°çš„ kernel å¯¦ä¾‹ï¼Œä½†ä½¿ç”¨ç›¸åŒçš„æœå‹™é…ç½®

        new_kernel = sk.Kernel()

        # è¤‡è£½æœå‹™

        for service in base_kernel.services.values():
            new_kernel.add_service(service)
        return new_kernel

    # å‰µå»ºæ–°çš„ kernel

    kernel = sk.Kernel()
    model_config = config_manager.get_model_by_name(model_name)
    if not model_config:
        raise ValueError(f"Model '{model_name}' not found in configuration")
    provider = model_config.get('provider')

    # Azure OpenAI

    if provider == 'azure_openai':
        service_id = f"azure_openai_{model_name}"
        kernel.add_service(
            AzureChatCompletion(
                service_id=service_id,
                deployment_name=model_config.get('deployment_name'),
                endpoint=model_config.get('endpoint'),
                api_key=model_config.get('api_key'),
                api_version=model_config.get('api_version')
            )
        )

    # Azure AI Foundry (may use model_id instead of deployment_name)

    elif provider == 'azure_ai_foundry':
        service_id = f"azure_ai_foundry_{model_name}"
        kernel.add_service(
            AzureChatCompletion(
                service_id=service_id,
                deployment_name=model_config.get('model_id') or model_config.get('deployment_name'),
                endpoint=model_config.get('endpoint'),
                api_key=model_config.get('api_key'),
                api_version=model_config.get('api_version')
            )
        )

    # OpenAI (official)

    elif provider == 'openai':
        service_id = f"openai_{model_name}"
        kernel.add_service(
            OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_name,
                api_key=model_config.get('api_key'),
                base_url=model_config.get('endpoint')
            )
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # å¿«å–åŸºç¤Ž kernel

    self.kernels[cache_key] = kernel

    # è¿”å›žå‰¯æœ¬

    new_kernel = sk.Kernel()
    for service in kernel.services.values():
        new_kernel.add_service(service)
    return new_kernel

async def create_chat_completion(self, model_name: str, messages: List[ChatMessage],
                                temperature: float = 0.7, max_tokens: Optional[int] = None,
                                features: Optional[Features] = None) -> ChatCompletionResponse:
    """ä½¿ç”¨ Semantic Kernel å‰µå»ºèŠå¤©å®Œæˆ"""
    try:
        kernel = await self.get_kernel_for_model(model_name, features)
        model_config = config_manager.get_model_by_name(model_name)

        # å–å¾—èŠå¤©å®Œæˆæœå‹™

        chat_completion = kernel.get_service(type=ChatCompletionClientBase)

        # å‰µå»ºèŠå¤©æ­·å²

        chat_history = ChatHistory()

        # æ·»åŠ è¨Šæ¯åˆ°èŠå¤©æ­·å²

        for message in messages:
            if message.role == "system":
                chat_history.add_system_message(message.content)
            else:
                chat_history.add_message(
                    ChatMessageContent(role=message.role, content=message.content)
                )

        # æº–å‚™è«‹æ±‚è¨­å®š

        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )

        # å‹•æ…‹è¨­å®šåƒæ•¸ - ä¸å¯«æ­»ä»»ä½•æ¨¡åž‹è¨­å®š

        provider = model_config.get('provider')

        # Azure OpenAI çµ±ä¸€ä¸è¨­å®š temperature é¿å…åƒæ•¸è¡çª

        if provider != 'azure_openai':
            try:
                execution_settings.temperature = temperature
            except Exception as e:
                logger.warning(f"ç„¡æ³•è¨­å®š temperature: {e}")

        # å‹•æ…‹è™•ç† max_tokens vs max_completion_tokens

        max_tokens_value = max_tokens or model_config.get('max_completion_tokens') or model_config.get('max_tokens', 4096)

        # 先嘗試使用 max_completion_tokens，若失敗再嘗試使用 max_tokens

        token_set = False
        if model_config.get('max_completion_tokens'):
            try:
                execution_settings.max_completion_tokens = max_tokens_value
                token_set = True
                logger.info(f"ä½¿ç”¨ max_completion_tokens: {max_tokens_value}")
            except Exception as e:
                logger.warning(f"ç„¡æ³•è¨­å®š max_completion_tokens: {e}")

        # å•Ÿç”¨å‡½æ•¸èª¿ç”¨ï¼ˆå·¥å…·é¸æ“‡ï¼‰- æ¢ä»¶æ€§å•Ÿç”¨

        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):

            # é‡æ–°å•Ÿç”¨å‡½æ•¸èª¿ç”¨ï¼Œä½†å…ˆè¨˜éŒ„è©³ç´°è³‡è¨Š

            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
            logger.info(f"ðŸ¤– [{model_name}] Agent mode enabled with {len(list(kernel.plugins))} plugins")

            # è¨˜éŒ„å¯ç”¨çš„å‡½æ•¸

            for plugin in kernel.plugins:
                plugin_name = getattr(plugin, 'name', str(plugin))
                logger.info(f"ðŸ”§ [{model_name}] Plugin '{plugin_name}' available for function calls")
        elif hasattr(execution_settings, 'function_choice_behavior'):
            logger.info(f"ðŸ’¬ [{model_name}] Basic chat mode (no plugins available)")
        else:
            logger.warning(f"âš ï¸  [{model_name}] FunctionChoiceBehavior not supported by this execution settings type")

        # åŸ·è¡ŒèŠå¤©å®Œæˆ
        # å¦‚æžœå•Ÿç”¨äº†å‡½æ•¸èª¿ç”¨ï¼Œéœ€è¦å‚³éž kernel å¯¦ä¾‹

        if plugins_available and hasattr(execution_settings, 'function_choice_behavior') and execution_settings.function_choice_behavior:
            response = await chat_completion.get_chat_message_contents(
                chat_history=chat_history,
                settings=execution_settings,
                kernel=kernel
            )
        else:
            response = await chat_completion.get_chat_message_contents(
                chat_history=chat_history,
                settings=execution_settings
            )
        if not response:
            raise ValueError("No response from chat completion service")

        # æª¢æŸ¥æ˜¯å¦æœ‰å‡½æ•¸èª¿ç”¨ç™¼ç”Ÿ

        response_metadata = self._analyze_response_metadata(response, model_name)

        # è½‰æ›ç‚º OpenAI å…¼å®¹æ ¼å¼

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=str(response[0].content)),
            finish_reason="stop"
        )

        # ä¼°ç®— token ä½¿ç”¨é‡ï¼ˆSemantic Kernel å¯èƒ½ä¸æä¾›è©³ç´°çµ±è¨ˆï¼‰

        prompt_tokens = sum(len(msg.content.split()) for msg in messages)
        completion_tokens = len(str(response[0].content).split())
        usage = ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=model_name,
            choices=[choice],
            usage=usage
        )
    except Exception as e:
        logger.error(f"Semantic Kernel èŠå¤©å®Œæˆå¤±æ•—: {e}")
        raise

# Event-driven: use in-process event bus to publish TokenUsage events

from lyrallm.logger_service.event_bus import event_bus as global_event_bus

async def track_token_usage(request_id: str, model_name: str, usage: Optional[ChatCompletionUsage],
                          start_time: datetime, status: str, user_id: Optional[str] = None, messages: Optional[List[ChatMessage]] = None, response_text: Optional[str] = None):
    """
    ç°¡åŒ–çš„ Token Usage è¿½è¹¤ - SK åªè² è²¬å‰µå»ºå’Œç™¼é€
    æ‰€æœ‰æ€§èƒ½å„ªåŒ–éƒ½ç”± Logger Service è‡ªå·±è™•ç†
    """
    try:

        # SK åªè² è²¬åŸºæœ¬çš„è³‡æ–™æº–å‚™

        cost_usd = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        if usage and getattr(usage, 'total_tokens', 0) > 0:

            # Use provider/SDK provided usage when available

            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens

            # ç°¡å–®æˆæœ¬ä¼°ç®— (will be overridden by compute_token_usage if used)

            model_config = config_manager.get_model_by_name(model_name)
            if model_config:
                input_cost_per_1k = model_config.get('input_cost_per_1k', 0.001)
                output_cost_per_1k = model_config.get('output_cost_per_1k', 0.002)
                cost_usd = (prompt_tokens / 1000) * input_cost_per_1k + (completion_tokens / 1000) * output_cost_per_1k
        else:

            # Fallback to estimator (tiktoken) or provider usage extractor via token_calculator

            model_config = config_manager.get_model_by_name(model_name)
            msgs = messages or []
            resp_text = response_text or ''
            calc = compute_token_usage(None, msgs, model_name, model_config, resp_text)
            prompt_tokens = calc.get('prompt_tokens', 0)
            completion_tokens = calc.get('completion_tokens', 0)
            total_tokens = calc.get('total_tokens', prompt_tokens + completion_tokens)
            cost_usd = calc.get('cost_usd', 0.0)

        # å‰µå»ºè³‡æ–™ç‰©ä»¶

        token_usage = TokenUsage(
            request_id=request_id,
            timestamp=start_time,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=round(cost_usd, 6),
            user_id=user_id,
            endpoint="/api/chat/completions",
            status=status
        )

        # ç™¼å¸ƒäº‹ä»¶åˆ° EventBusï¼Œç”± logger_service çš„ consumer è™•ç†å¯«å…¥ DB/ELK

        try:

            # publish the pydantic model as dict for downstream consumers

            global_event_bus.publish(token_usage.model_dump())
            logger.debug(f"[{request_id}] Token usage published to EventBus")
        except Exception as e:

            # SK ä¸è™•ç† logging éŒ¯èª¤ï¼Œå°ˆæ³¨æ–¼ AI

            logger.error(f"[{request_id}] Token tracking error: {e}")
    except Exception as e:

        # æ•æ‰è³‡æ–™æº–å‚™éšŽæ®µçš„éŒ¯èª¤ï¼Œä¸å½±éŸ¿ä¸»è¦æµç¨‹

        logger.error(f"[{request_id}] Token tracking preparation error: {e}")
        return

def get_queue_status():
    """Return EventBus status for health checks."""
    try:

        # event_bus provides helpers

        return {
            "queue_length": global_event_bus.queue_size(),
            "subscribers": global_event_bus.subscriber_count(),
            "running": global_event_bus.is_running()
        }
    except Exception as e:
        logger.error(f"Failed to get event bus status: {e}")
        return {"queue_length": -1, "subscribers": 0, "running": False}

async def handle_agent_mode_request(request: ChatCompletionRequest, security_ctx: RequestSecurityContext = None) -> ChatCompletionResponse:
    """
    æµç¨‹ç·¨è™Ÿ #004: Agentæ¨¡å¼è™•ç†å…¥å£ - åˆå§‹åŒ–Agentå”èª¿å™¨
    è™•ç† Agent æ¨¡å¼è«‹æ±‚ - ä½¿ç”¨å¤š Agent å”ä½œ
    """
    request_id = f"agent_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()
    try:
        logger.info(f"[{request_id}] é€²å…¥ Agent æ¨¡å¼è™•ç†")

        # ç²å–ç”¨æˆ¶æœ€æ–°è¨Šæ¯

        user_messages = [msg.content for msg in request.messages if msg.role == 'user']
        if not user_messages:
            raise ValueError("No user message found")
        user_input = user_messages[-1]

        # Resolve model name (handle 'auto' routing) and å‰µå»ºèŠå¤©æœå‹™
        model_name_to_use = request.model
        try:
            if request.model == 'auto':
                # Use ModelExecutor routing logic to pick the best model for 'auto'
                from lyrallm.core.model_executor import ModelExecutor
                executor = ModelExecutor()
                routed_model, routing_info = await executor._route_model(request.messages, request_id)
                logger.info(f"[{request_id}] Auto-routed model: {routed_model}")
                model_name_to_use = routed_model or config_manager.get_default_model()

        except Exception as route_err:
            logger.warning(f"[{request_id}] Auto routing failed, falling back to requested model '{request.model}': {route_err}")

        model_config = config_manager.get_model_by_name(model_name_to_use)
        if not model_config:
            raise ValueError(f"Model '{model_name_to_use}' not found")
        chat_service = await create_chat_service_for_model(model_name_to_use, model_config)

        # æµç¨‹ç·¨è™Ÿ #005: å‰µå»ºAgentå”èª¿å™¨
        # å‰µå»º Agent å”èª¿å™¨ (ä½¿ç”¨ä½¿ç”¨è€…é¸æ“‡çš„æ¨¡åž‹)

        orchestrator = await create_practical_agent_orchestrator(chat_service)
        if not orchestrator:
            raise ValueError("ç„¡æ³•åˆå§‹åŒ– Agent å”èª¿å™¨")

        # æµç¨‹ç·¨è™Ÿ #006: å‹•æ…‹èƒ½åŠ›è¨»å†Š - æ ¹æ“šfeatureså•Ÿç”¨ç›¸æ‡‰åŠŸèƒ½
        # æ ¹æ“š features å‹•æ…‹æ·»åŠ èƒ½åŠ›

        capabilities_added = []
        if request.features:
            if request.features.web_search:
                if orchestrator.add_web_search_capability():
                    capabilities_added.append("web_search")
            if request.features.rag_search:
                if orchestrator.add_rag_capability():
                    capabilities_added.append("rag_search")
            if request.features.image_generation:

                # TODO: æ·»åŠ åœ–åƒç”Ÿæˆèƒ½åŠ›

                logger.info(f"[{request_id}] Image generation åŠŸèƒ½å°šæœªå¯¦ç¾")
                pass
            if request.features.code_interpreter:

                # TODO: æ·»åŠ ä»£ç¢¼è§£é‡‹å™¨èƒ½åŠ›

                logger.info(f"[{request_id}] Code interpreter åŠŸèƒ½å°šæœªå¯¦ç¾")
                pass
        logger.info(f"[{request_id}] Agent æ¨¡å¼å•Ÿç”¨åŠŸèƒ½: {capabilities_added}")

        # æº–å‚™ features åƒæ•¸

        features_dict = {}
        if request.features:

            # ç›´æŽ¥æª¢æŸ¥å…·é«”çš„åŠŸèƒ½é–‹é—œ

            if request.features.web_search:
                features_dict["web_search"] = True
            if request.features.rag_search:
                features_dict["rag_search"] = True
            if request.features.image_generation:
                features_dict["image_generation"] = True
            if request.features.code_interpreter:
                features_dict["code_interpreter"] = True
            logger.info(f"[{request_id}] Agent æ¨¡å¼å•Ÿç”¨åŠŸèƒ½: {list(features_dict.keys())}")

        # æµç¨‹ç·¨è™Ÿ #007: è™•ç†ç”¨æˆ¶è«‹æ±‚ - èª¿ç”¨Agentå”èª¿å™¨
        # è™•ç†è«‹æ±‚

        try:
            # Protect agent processing from hanging by imposing a timeout.
            # If the orchestrator (or its agents) blocks (e.g., external MCP not available),
            # we timeout and allow the caller to fall back to standard model execution.
            result = await asyncio.wait_for(
                orchestrator.process_request(user_input, features_dict, security_ctx=security_ctx),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Agent processing timed out (possible external tool/unavailable web search). Falling back to standard execution.")

        # æµç¨‹ç·¨è™Ÿ #050: æ ¼å¼è½‰æ› - å°‡Agentçµæžœè½‰ç‚ºOpenAIæ ¼å¼
        # è½‰æ›ç‚º OpenAI å…¼å®¹æ ¼å¼

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=result),
            finish_reason="stop"
        )

        # ä¼°ç®— token ä½¿ç”¨é‡

        prompt_tokens = sum(len(msg.content.split()) for msg in request.messages)
        completion_tokens = len(result.split())
        usage = ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )
        response = ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=model_name_to_use,
            choices=[choice],
            usage=usage
        )

        # è¨˜éŒ„å°è©±æ­·å²ï¼ˆç”¨æ–¼é™¤éŒ¯ï¼‰

        conversation_history = orchestrator.get_conversation_history()
        if conversation_history:
            logger.info(f"[{request_id}] Agent å°è©±æ­·å²: {len(conversation_history)} è¼ªäº¤äº’")
        logger.info(f"[{request_id}] Agent æ¨¡å¼è™•ç†å®Œæˆ")
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Agent æ¨¡å¼è™•ç†å¤±æ•—: {e}")
        import traceback

        logger.error(f"[{request_id}] éŒ¯èª¤å †ç–Š: {traceback.format_exc()}")
        raise

async def create_chat_service_for_model(model_name: str, model_config: Dict[str, Any]) -> ChatCompletionClientBase:
    """
    ç‚ºæŒ‡å®šæ¨¡åž‹å‰µå»ºèŠå¤©æœå‹™
    """
    provider = model_config.get('provider')
    if provider == 'azure_openai':
        return AzureChatCompletion(
            service_id=f"azure_openai_{model_name}",
            deployment_name=model_config.get('deployment_name'),
            endpoint=model_config.get('endpoint'),
            api_key=model_config.get('api_key'),
            api_version=model_config.get('api_version')
        )
    elif provider == 'azure_ai_foundry':
        return AzureChatCompletion(
            service_id=f"azure_ai_foundry_{model_name}",
            deployment_name=model_config.get('model_id') or model_config.get('deployment_name'),
            endpoint=model_config.get('endpoint'),
            api_key=model_config.get('api_key'),
            api_version=model_config.get('api_version')
        )
    elif provider == 'openai':
        return OpenAIChatCompletion(
            service_id=f"openai_{model_name}",
            ai_model_id=model_name,
            api_key=model_config.get('api_key'),
            base_url=model_config.get('endpoint')
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

# æµç¨‹ç·¨è™Ÿ #001: APIè«‹æ±‚å…¥å£é»ž - æŽ¥æ”¶èŠå¤©å®Œæˆè«‹æ±‚
# æ­¤è™•æ˜¯æ•´å€‹èŠå¤©æµç¨‹çš„èµ·é»žï¼Œæ‰€æœ‰çš„å°è©±è«‹æ±‚éƒ½æœƒç¶“éŽé€™è£¡
@router.post("/api/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """
    å‰µå»ºèŠå¤©å®Œæˆ - æ”¯æ´å‚³çµ±æ¨¡å¼å’Œ Agent æ¨¡å¼
    """

    # ç”Ÿæˆå”¯ä¸€è«‹æ±‚ ID

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()

    # è¨˜éŒ„åŽŸå§‹è«‹æ±‚

    await request_logger.log_request_body(raw_request)
    try:
        logger.info(f"[{request_id}] æ”¶åˆ°èŠå¤©è«‹æ±‚ - æ¨¡åž‹: {request.model}")
        request_dict = request.model_dump()

        # Enforce role-based model access

        if not security_ctx.allows_model(request.model):
            logger.warning(
                "[%s] Role '%s' is not allowed to invoke model '%s'",
                request_id,
                security_ctx.role.name,
                request.model,
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed",
                    "model": request.model,
                    "role": security_ctx.role.name,
                },
            )

        # ç‰¹åˆ¥æª¢æŸ¥ features å­—æ®µ

        logger.info(f"[{request_id}] Features åŽŸå§‹å€¼: {request.features}")
        logger.info(f"[{request_id}] Features é¡žåž‹: {type(request.features)}")
        if request.features:
            logger.info(f"[{request_id}] Features å…§å®¹: web_search={request.features.web_search}, image_generation={request.features.image_generation}, rag_search={request.features.rag_search}, code_interpreter={request.features.code_interpreter}")
            feature_payload = request.features.model_dump(exclude_none=True)
            requested_features = [key for key, value in feature_payload.items() if isinstance(value, bool) and value]
            disallowed_features = [feature for feature in requested_features if not security_ctx.allows_feature(feature)]
            if disallowed_features:
                logger.warning(
                    "[%s] Role '%s' is not permitted to use features %s",
                    request_id,
                    security_ctx.role.name,
                    disallowed_features,
                )
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_not_allowed",
                        "features": disallowed_features,
                        "role": security_ctx.role.name,
                    },
                )
            logger.info(f"[{request_id}] Features å…§å®¹: web_search={request.features.web_search}, image_generation={request.features.image_generation}, rag_search={request.features.rag_search}, code_interpreter={request.features.code_interpreter}")

        # æµç¨‹ç·¨è™Ÿ #002: æ¨¡å¼æ±ºç­–é»ž - åˆ¤æ–·ä½¿ç”¨Agentæ¨¡å¼æˆ–ç›´æŽ¥æ¨¡å¼
        # æ ¹æ“šå‰ç«¯å‚³ä¾†çš„featuresåƒæ•¸æ±ºå®šè™•ç†æ–¹å¼

        agent_mode_enabled = False
        if request.features:

            # æª¢æŸ¥æ˜¯å¦æœ‰ä»»ä½•åŠŸèƒ½å•Ÿç”¨

            agent_mode_enabled = (request.features.web_search or
                                request.features.image_generation or
                                request.features.rag_search or
                                request.features.code_interpreter)
            if agent_mode_enabled:
                logger.info(f"[{request_id}] åµæ¸¬åˆ° features åƒæ•¸ï¼Œé€²å…¥ Agent æ¨¡å¼")
                enabled_features = []
                if request.features.web_search:
                    enabled_features.append("web_search")
                if request.features.image_generation:
                    enabled_features.append("image_generation")
                if request.features.rag_search:
                    enabled_features.append("rag_search")
                if request.features.code_interpreter:
                    enabled_features.append("code_interpreter")
                logger.info(f"[{request_id}] å•Ÿç”¨åŠŸèƒ½: {enabled_features}")
        else:
            logger.info(f"[{request_id}] å‰ç«¯æœªæŒ‡å®šåŠŸèƒ½ï¼Œä½¿ç”¨åŸºæœ¬èŠå¤©æ¨¡å¼")

        # æµç¨‹ç·¨è™Ÿ #003A: Agentæ¨¡å¼åˆ†æ”¯ - é€²å…¥å¤šAgentå”ä½œæµç¨‹
        # ç•¶å•Ÿç”¨ä»»ä½•ç‰¹æ®ŠåŠŸèƒ½æ™‚èµ°æ­¤åˆ†æ”¯

        if agent_mode_enabled:
            try:
                # å¦‚æžœå‰ç«¯è¦æ±‚ä¸²æµï¼Œç‚º Agent æ¨¡å¼æä¾› SSE ä¸²æµæ”¯æ´
                if request.stream:
                    async def agent_stream_generator():
                        done_sent = False
                        final_text = ""
                        try:
                            # é å…ˆå˜—è©¦å–å¾— Router çš„å¯¦éš›åˆ†é…ï¼ˆå°æ–¼ 'auto' æ¨¡å¼ï¼‰
                            routed_model = None
                            routing_info = None
                            try:
                                if request.model == 'auto':
                                    from lyrallm.core.model_executor import ModelExecutor
                                    _executor = ModelExecutor()
                                    routed_model, routing_info = await _executor._route_model(request.messages, request_id)
                                    logger.info(f"[{request_id}] Agent stream - routed to: {routed_model}")
                                    # ç«‹åˆ»å‘ŠçŸ¥å‰ç«¯è·¯ç”±è³‡è¨Š
                                    info_payload = {
                                        "type": "info",
                                        "model": routed_model or request.model,
                                        "routing_info": routing_info or {}
                                    }
                                    yield _format_sse(info_payload)

                            except Exception as route_err:
                                logger.warning(f"[{request_id}] Router early resolution failed: {route_err}")

                            # å‘¼å«ç¾æœ‰çš„ Agent è™•ç†å‡½å¼ï¼ˆæœƒå›žå‚³å®Œæ•´çµæžœï¼‰
                            response = await handle_agent_mode_request(request, security_ctx)
                            if response and isinstance(response.choices, list) and response.choices:
                                final_text = response.choices[0].message.content or ""

                            # å°‡å›žè¦†åˆ†æ®µé€å‡ºï¼Œä»¥æ¨¡æ“¬ streaming behavior
                            chunk_size = 256
                            for i in range(0, len(final_text), chunk_size):
                                piece = final_text[i:i+chunk_size]
                                payload = {
                                    "type": "delta",
                                    "model": response.model if response else request.model,
                                    "text": piece,
                                }
                                yield _format_sse(payload)
                                await asyncio.sleep(0)

                            # å‚³é€ final payload
                            final_payload = {
                                "type": "final",
                                "model": response.model if response else request.model,
                                "text": final_text,
                                "usage": response.usage.model_dump() if (response and response.usage) else None,
                            }
                            yield _format_sse(final_payload)
                            yield b"data: [DONE]\n\n"
                            done_sent = True

                            # è¿½è¹¤ token ä½¿ç”¨
                            try:
                                await track_token_usage(
                                    request_id=request_id,
                                    model_name=response.model if response else request.model,
                                    usage=response.usage if response else None,
                                    start_time=start_time,
                                    status="success",
                                    user_id=security_ctx.user_id,
                                    messages=request.messages,
                                    response_text=final_text or ""
                                )
                            except Exception as metric_error:
                                logger.error(f"[{request_id}] Failed to record agent streaming token usage: {metric_error}")

                        except Exception as stream_err:
                            logger.error(f"[{request_id}] Agent streaming error: {stream_err}")
                            err_payload = {"error": str(stream_err), "model": request.model}
                            yield _format_sse(err_payload)
                            if not done_sent:
                                yield b"data: [DONE]\n\n"

                    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
                    return StreamingResponse(agent_stream_generator(), media_type="text/event-stream", headers=headers)

                # éžä¸²æµæƒ…æ³ä»ç¶­æŒåŽŸè¡Œç‚º
                response = await handle_agent_mode_request(request, security_ctx)

                # è¿½è¹¤ token ä½¿ç”¨
                await track_token_usage(
                    request_id=request_id,
                    model_name=request.model,
                    usage=response.usage,
                    start_time=start_time,
                    status="success",
                    user_id=security_ctx.user_id,
                    messages=request.messages,
                    response_text=response.choices[0].message.content
                )
                return response
            except Exception as e:
                logger.error(f"[{request_id}] Agent æ¨¡å¼å¤±æ•—ï¼Œå˜—è©¦é™ç´šåˆ°å‚³çµ±æ¨¡å¼: {e}")

                # é™ç´šåˆ°å‚³çµ±æ¨¡å¼
                agent_mode_enabled = False

        # æµç¨‹ç·¨è™Ÿ #003B: ç›´æŽ¥æ¨¡å¼åˆ†æ”¯ - ä½¿ç”¨åŸºæœ¬èŠå¤©åŠŸèƒ½ï¼ˆä¸å•Ÿç”¨ç‰¹æ®ŠåŠŸèƒ½æ™‚ï¼‰
        # Standard model processing (optimized with new ModelExecutor)

        if not agent_mode_enabled:
            logger.info(f"[{request_id}] Processing with standard model execution")

            # Log feature settings for debugging

            if request.features:
                enabled_features = [
                    name for name, enabled in [
                        ("web_search", request.features.web_search),
                        ("image_generation", request.features.image_generation),
                        ("code_interpreter", request.features.code_interpreter)
                    ] if enabled
                ]
                logger.info(f"[{request_id}] Frontend features: {enabled_features or 'none'}")
            else:
                logger.info(f"[{request_id}] No frontend features specified, using basic chat mode")

            executor = get_default_executor()

            if request.stream:
                stream_iterator = executor.stream_generate(
                    model_name=request.model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    features=request.features,
                    security_ctx=security_ctx
                )

                full_text: str = ""
                final_payload: Optional[Dict[str, Any]] = None
                streamed_model: Optional[str] = None

                async def stream_generator():
                    nonlocal full_text, final_payload, streamed_model
                    done_sent = False
                    try:
                        async for event in stream_iterator:
                            if not isinstance(event, dict):
                                continue
                            event_type = event.get("type")
                            payload = event.get("payload") or {}
                            if not isinstance(payload, dict):
                                continue

                            if event_type == "info":
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint
                                yield _format_sse(payload)
                                continue

                            if event_type == "delta":
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint
                                text_piece = _extract_text_from_stream_payload(payload)
                                if text_piece:
                                    full_text += text_piece
                                yield _format_sse(payload)
                                continue

                            if event_type == "final":
                                final_payload = payload
                                model_hint = payload.get("model")
                                if isinstance(model_hint, str):
                                    streamed_model = model_hint

                                if not full_text:
                                    final_text = _extract_text_from_stream_payload(payload)
                                    if final_text:
                                        full_text = final_text
                                if not full_text and isinstance(payload.get("text"), str):
                                    full_text = payload["text"]

                                yield _format_sse(payload)
                                continue

                            # Unexpected payload, forward as-is
                            if payload:
                                yield _format_sse(payload)

                        yield b"data: [DONE]\n\n"
                        done_sent = True
                    except Exception as stream_error:
                        logger.error(f"[{request_id}] Streaming generator error: {stream_error}")
                        error_payload = {
                            "error": str(stream_error),
                            "model": streamed_model or request.model,
                        }
                        yield _format_sse(error_payload)
                        if not done_sent:
                            yield b"data: [DONE]\n\n"
                            done_sent = True
                    finally:
                        status = "success" if final_payload else "system_error"
                        tracked_model = streamed_model
                        if final_payload:
                            tracked_model = final_payload.get("model", tracked_model)
                        if not tracked_model:
                            tracked_model = request.model

                        usage_payload: Optional[Dict[str, Any]] = None
                        if final_payload and isinstance(final_payload.get("usage"), dict):
                            usage_payload = final_payload["usage"]
                        if not usage_payload and full_text:
                            try:
                                usage_payload = executor._calculate_usage(request.messages, full_text)  # type: ignore[attr-defined]
                            except Exception:
                                usage_payload = None

                        if final_payload and not full_text and isinstance(final_payload.get("text"), str):
                            full_text = final_payload["text"]

                        usage_obj: Optional[ChatCompletionUsage] = None
                        if isinstance(usage_payload, dict):
                            usage_obj = ChatCompletionUsage(
                                prompt_tokens=int(usage_payload.get("prompt_tokens", 0)),
                                completion_tokens=int(usage_payload.get("completion_tokens", 0)),
                                total_tokens=int(usage_payload.get("total_tokens", 0)),
                            )

                        try:
                            await track_token_usage(
                                request_id=request_id,
                                model_name=tracked_model,
                                usage=usage_obj,
                                start_time=start_time,
                                status=status,
                                user_id=security_ctx.user_id,
                                messages=request.messages,
                                response_text=full_text or ""
                            )
                        except Exception as metric_error:
                            logger.error(f"[{request_id}] Failed to record streaming token usage: {metric_error}")

                headers = {
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                }
                return StreamingResponse(stream_generator(), media_type="text/event-stream", headers=headers)

            exec_result = await executor.generate(
                model_name=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                features=request.features,
                security_ctx=security_ctx
            )

            actual_model = exec_result.get('model', request.model)
            routing_meta = exec_result.get('meta', {}).get('routing_info', {})
            choice = ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role='assistant',
                    content=exec_result['choices'][0]['message']['content']
                ),
                finish_reason=exec_result['choices'][0].get('finish_reason', 'stop')
            )
            usage_obj = ChatCompletionUsage(
                prompt_tokens=exec_result.get('usage', {}).get('prompt_tokens', 0),
                completion_tokens=exec_result.get('usage', {}).get('completion_tokens', 0),
                total_tokens=exec_result.get('usage', {}).get('total_tokens', 0)
            )
            response = ChatCompletionResponse(
                id=f"{request_id}-{exec_result.get('id', int(time.time()))}",
                created=exec_result.get('created', int(time.time())),
                model=actual_model,
                choices=[choice],
                usage=usage_obj,
                meta=exec_result.get('meta', {}),
                routing_info=routing_meta or exec_result.get('meta', {}).get('routing_info', None)
            )

            await track_token_usage(
                request_id=request_id,
                model_name=actual_model,
                usage=response.usage,
                start_time=start_time,
                status="success",
                user_id=security_ctx.user_id,
                messages=request.messages,
                response_text=response.choices[0].message.content
            )

            if routing_meta:
                raw_conf = routing_meta.get('confidence')
                confidence_str = f"{raw_conf:.3f}" if isinstance(raw_conf, (int, float)) else "n/a"
                logger.info(
                    f"[{request_id}] Auto-routing: {actual_model} "
                    f"(intent={routing_meta.get('intent')}, confidence={confidence_str})"
                )
            logger.info(
                f"[{request_id}] Chat completion successful - Model: {actual_model}, "
                f"Tokens: {usage_obj.total_tokens}, "
                f"Latency: {exec_result.get('meta', {}).get('latency_ms', 0)}ms"
            )
            return response
    except HTTPException:

        # è¿½è¹¤å¤±æ•—çš„è«‹æ±‚

        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="http_error",
            user_id=security_ctx.user_id,
            messages=request.messages
        )
        raise
    except Exception as e:

        # è¿½è¹¤ç³»çµ±éŒ¯èª¤

        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="system_error",
            user_id=security_ctx.user_id,
            messages=request.messages
        )
        logger.error(f"[{request_id}] èŠå¤©å®Œæˆå¤±æ•—: {e}")
        import traceback

        logger.error(f"[{request_id}] éŒ¯èª¤å †ç–Š: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@router.get("/api/chat/models")
async def get_chat_models(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """å–å¾—æ”¯æ´èŠå¤©çš„æ¨¡åž‹åˆ—è¡¨"""
    try:
        available_models = config_manager.get_available_models()
        visible_models = [
            model for model in available_models
            if security_ctx.allows_model(model.get("name", ""))
        ]
        chat_models = []
        for model in visible_models:
            chat_models.append({
                "id": model["name"],
                "name": model["name"],
                "provider": model.get("provider", ""),
                "description": model.get("description", ""),
                "max_tokens": model.get("max_completion_tokens") or model.get("max_tokens", 4096),
                "temperature": model.get("temperature", 0.7)
            })
        names = [model["name"] for model in chat_models]
        logger.info(f"Chat models available: {names}")
        return {
            "object": "list",
            "data": chat_models
        }
    except Exception as e:
        logger.error(f"å–å¾—èŠå¤©æ¨¡åž‹å¤±æ•—: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat models: {str(e)}")

@router.post("/api/chat/feedback")
async def submit_chat_feedback(
    payload: FeedbackRequest,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """Record lightweight chat feedback for routing adjustments."""
    try:
        logger.info("[feedback] role=%s user=%s conversation=%s message=%s model=%s feedback=%s",
                    security_ctx.role.name,
                    security_ctx.user_id,
                    payload.conversation_id,
                    payload.message_id,
                    payload.model,
                    payload.feedback)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Feedback handler failure: {e}")
        raise HTTPException(status_code=500, detail="Failed to record feedback")

@router.get("/api/chat/health")
async def chat_health_check():
    """èŠå¤©æœå‹™å¥åº·æª¢æŸ¥ + Token Tracking ç‹€æ…‹"""
    try:
        event_status = get_queue_status()

        # check postgres health (non-blocking wrapper)

        from lyrallm.logger_service.db_client import postgres_health

        try:
            pg_health = await postgres_health()
        except Exception:
            pg_health = {"connected": False}

        # ç²å–å·²åŠ è¼‰çš„æ¨¡åž‹æ•¸é‡

        available_models = config_manager.get_available_models()
        visible_models = [
            model for model in available_models
            if security_ctx.allows_model(model.get("name", ""))
        ]
        models_count = len([m for m in available_models if m.get('enabled', False)])
        services = {
            "semantic_kernel": "ready",
            "event_bus": "running" if event_status.get("running") else "stopped",
            "postgres": "connected" if pg_health.get("connected") else "disconnected",
            "token_tracking": "enabled",
        }

        # Ollama health check (for SLM analyzer)

        ollama_models: List[str] = []
        try:
            ollama_cfg = config_manager.get_provider_config("ollama") or {}
            base_url = (ollama_cfg.get("base_url") or "").strip()
            if base_url:
                if not base_url.startswith("http://") and not base_url.startswith("https://"):
                    base_url = f"http://{base_url}"
                url = base_url.rstrip("/") + "/api/tags"
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(url)
                if resp.status_code == 200:
                    services["ollama"] = "reachable"
                    try:
                        payload = resp.json()
                        ollama_models = [m.get("name") for m in payload.get("models", []) if m.get("name")]
                    except Exception:
                        ollama_models = []
                else:
                    services["ollama"] = f"unreachable:{resp.status_code}"
            else:
                services["ollama"] = "not_configured"
        except Exception as ollama_error:
            services["ollama"] = f"error:{ollama_error}"
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": services,
            "event_bus_info": event_status,
            "postgres_info": pg_health,
            "models_loaded": models_count,
            "ollama_models": ollama_models
        }
    except Exception as e:
        logger.error(f"å¥åº·æª¢æŸ¥å¤±æ•—: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

@router.get("/api/chat/plugins")
async def get_plugin_info():
    """å–å¾— Plugin é…ç½®è³‡è¨Š"""
    try:
        plugin_info = plugin_manager.get_plugin_info()
        return {
            "status": "success",
            "data": plugin_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"å–å¾— Plugin è³‡è¨Šå¤±æ•—: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get plugin info: {str(e)}")

@router.post("/api/chat/plugins/reload")
async def reload_plugin_config():
    """é‡æ–°è¼‰å…¥ Plugin é…ç½®ï¼ˆç†±æ›´æ–°ï¼‰"""
    try:
        plugin_manager.reload_config()
        plugin_info = plugin_manager.get_plugin_info()
        return {
            "status": "success",
            "message": "Plugin configuration reloaded successfully",
            "data": plugin_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"é‡æ–°è¼‰å…¥ Plugin é…ç½®å¤±æ•—: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload plugin config: {str(e)}")

# @router.get("/api/chat/agent/status")
# async def get_agent_status():
#     """ç²å– Agent æ¨¡å¼ç‹€æ…‹"""
#     try:
#         # å‰µå»ºä¸€å€‹æ¸¬è©¦ç”¨çš„èŠå¤©æœå‹™ä¾†æª¢æŸ¥ Agent å¯ç”¨æ€§
#         test_model = config_manager.get_default_model()
#         if not test_model:
#             available_models = config_manager.get_available_models()

        visible_models = [
            model for model in available_models
            if security_ctx.allows_model(model.get("name", ""))
        ]

#             if available_models:
#                 test_model = available_models[0]['name']
#             else:
#                 raise ValueError("No models available")
#         model_config = config_manager.get_model_by_name(test_model)
#         if not model_config:
#             raise ValueError(f"Model config not found for {test_model}")
#         chat_service = await create_chat_service_for_model(test_model, model_config)
#         orchestrator = AgentOrchestrator(chat_service)
#         available_features = orchestrator.get_available_features()
#         return {
#             "status": "available",
#             "agent_mode": "enabled",
#             "available_features": available_features,
#             "agents": {
#                 "ThinkerAgent": "available",
#                 "WebSearchAgent": "available" if "web_search" in available_features else "unavailable"
#             },
#             "timestamp": datetime.now().isoformat()
#         }
#     except Exception as e:
#         logger.error(f"ç²å– Agent ç‹€æ…‹å¤±æ•—: {e}")
#         return {
#             "status": "error",
#             "agent_mode": "disabled",
#             "error": str(e),
#             "timestamp": datetime.now().isoformat()
#         }
@router.get("/api/chat/features")
async def get_available_features():
    """å–å¾—æ‰€æœ‰å¯ç”¨çš„åŠŸèƒ½åˆ—è¡¨"""
    try:

        # ç°¡åŒ–çš„åŠŸèƒ½åˆ—è¡¨

        available_features = ["web_search", "image_generation"]

        # å–å¾—æ¯å€‹åŠŸèƒ½çš„è©³ç´°è³‡è¨Š

        feature_details = [
            {
                "name": "web_search",
                "description": "Web Search Plugin - æä¾›ç¶²è·¯æœå°‹åŠŸèƒ½",
                "require_config": True,
                "plugin_id": "web_search"
            },
            {
                "name": "image_generation",
                "description": "Image Generation Plugin - æä¾›åœ–åƒç”ŸæˆåŠŸèƒ½",
                "require_config": True,
                "plugin_id": "image_generation"
            }
        ]
        return {
            "status": "success",
            "data": {
                "available_features": available_features,
                "feature_details": feature_details,
                "total_count": len(available_features)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"å–å¾—å¯ç”¨åŠŸèƒ½å¤±æ•—: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get available features: {str(e)}")

