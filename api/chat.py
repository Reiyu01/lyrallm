from fastapi import APIRouter, Depends, HTTPException, Request
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

# 添加請求日誌功能
class RequestLoggingMiddleware:

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def log_request_body(self, request: Request):
        """記錄原始請求體"""
        if request.url.path == "/api/chat/completions":
            try:
                body = await request.body()
                if body:
                    body_str = body.decode('utf-8')
                    self.logger.info(f"🔍 原始請求體: {body_str}")

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
                self.logger.error(f"❌ 讀取請求體失敗: {e}")
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
    code_interpreter: Optional[bool] = False

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

# All kernel management now handled by unified ModelExecutor for consistency
    async def _load_plugins(self, kernel: sk.Kernel, model_name: str, features: Optional[Features] = None) -> int:
        """在這個架構中，Plugin 由 Agent 協調器管理，此方法主要用於基本聊天模式"""
        try:

            # 在新架構中，Plugin 載入由 Agent 協調器負責
            # 這裡只處理非 Agent 模式的基本聊天需求

            plugins_loaded = 0

            # 如果啟用了 Agent 模式，Plugin 由 Agent 協調器載入

            if features and (features.web_search or features.image_generation or features.code_interpreter):
                logger.info(f"🎭 [{model_name}] Agent 模式啟用，Plugin 由 Agent 協調器管理")
                return plugins_loaded

            # 基本聊天模式不需要載入額外的 Plugin

            logger.info(f"� [{model_name}] 基本聊天模式，無需載入額外 Plugin")
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

                    # 安全地獲取 plugin 資訊

                    plugin_name = getattr(plugin, 'name', str(plugin))

                    # 嘗試獲取 functions 資訊

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
                logger.info(f"💭 [{model_name}] No functions called - direct response")
        else:
            logger.debug(f"📄 [{model_name}] No metadata in response")
    except Exception as e:
        logger.warning(f"⚠️  [{model_name}] Error analyzing response metadata: {e}")
    return metadata

async def get_kernel_for_model(self, model_name: str, features: Optional[Features] = None) -> sk.Kernel:
    """取得指定模型的 Semantic Kernel 實例，根據 features 動態載入 plugins"""

    # 創建基礎 kernel（不包含 plugins）

    kernel = await self._get_base_kernel_for_model(model_name)

    # 根據 features 動態載入 plugins

    if features:
        plugins_count = await self._load_plugins(kernel, model_name, features)
        logger.info(f"🔌 [{model_name}] Loaded {plugins_count} plugins based on frontend features")

        # 記錄 plugin 狀態

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

        # 創建新的 kernel 實例，但使用相同的服務配置

        new_kernel = sk.Kernel()

        # 複製服務

        for service in base_kernel.services.values():
            new_kernel.add_service(service)
        return new_kernel

    # 創建新的 kernel

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
    """使用 Semantic Kernel 創建聊天完成"""
    try:
        kernel = await self.get_kernel_for_model(model_name, features)
        model_config = config_manager.get_model_by_name(model_name)

        # 取得聊天完成服務

        chat_completion = kernel.get_service(type=ChatCompletionClientBase)

        # 創建聊天歷史

        chat_history = ChatHistory()

        # 添加訊息到聊天歷史

        for message in messages:
            if message.role == "system":
                chat_history.add_system_message(message.content)
            else:
                chat_history.add_message(
                    ChatMessageContent(role=message.role, content=message.content)
                )

        # 準備請求設定

        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )

        # 動態設定參數 - 不寫死任何模型設定

        provider = model_config.get('provider')

        # Azure OpenAI 統一不設定 temperature 避免參數衝突

        if provider != 'azure_openai':
            try:
                execution_settings.temperature = temperature
            except Exception as e:
                logger.warning(f"無法設定 temperature: {e}")

        # 動態處理 max_tokens vs max_completion_tokens

        max_tokens_value = max_tokens or model_config.get('max_completion_tokens') or model_config.get('max_tokens', 4096)

        # 先嘗試 max_completion_tokens，如果失敗再嘗試 max_tokens

        token_set = False
        if model_config.get('max_completion_tokens'):
            try:
                execution_settings.max_completion_tokens = max_tokens_value
                token_set = True
                logger.info(f"使用 max_completion_tokens: {max_tokens_value}")
            except Exception as e:
                logger.warning(f"無法設定 max_completion_tokens: {e}")

        # 啟用函數調用（工具選擇）- 條件性啟用

        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):

            # 重新啟用函數調用，但先記錄詳細資訊

            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
            logger.info(f"🤖 [{model_name}] Agent mode enabled with {len(list(kernel.plugins))} plugins")

            # 記錄可用的函數

            for plugin in kernel.plugins:
                plugin_name = getattr(plugin, 'name', str(plugin))
                logger.info(f"🔧 [{model_name}] Plugin '{plugin_name}' available for function calls")
        elif hasattr(execution_settings, 'function_choice_behavior'):
            logger.info(f"💬 [{model_name}] Basic chat mode (no plugins available)")
        else:
            logger.warning(f"⚠️  [{model_name}] FunctionChoiceBehavior not supported by this execution settings type")

        # 執行聊天完成
        # 如果啟用了函數調用，需要傳遞 kernel 實例

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

        # 檢查是否有函數調用發生

        response_metadata = self._analyze_response_metadata(response, model_name)

        # 轉換為 OpenAI 兼容格式

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=str(response[0].content)),
            finish_reason="stop"
        )

        # 估算 token 使用量（Semantic Kernel 可能不提供詳細統計）

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
    簡化的 Token Usage 追蹤 - SK 只負責創建和發送
    所有性能優化都由 Logger Service 自己處理
    """
    try:

        # SK 只負責基本的資料準備

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

        # 創建資料物件

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

            # SK 不處理 logging 錯誤，專注於 AI

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

async def handle_agent_mode_request(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """
    流程編號 #004: Agent模式處理入口 - 初始化Agent協調器
    處理 Agent 模式請求 - 使用多 Agent 協作
    """
    request_id = f"agent_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()
    try:
        logger.info(f"[{request_id}] 進入 Agent 模式處理")

        # 獲取用戶最新訊息

        user_messages = [msg.content for msg in request.messages if msg.role == 'user']
        if not user_messages:
            raise ValueError("No user message found")
        user_input = user_messages[-1]

        # 創建聊天服務

        model_config = config_manager.get_model_by_name(request.model)
        if not model_config:
            raise ValueError(f"Model '{request.model}' not found")
        chat_service = await create_chat_service_for_model(request.model, model_config)

        # 流程編號 #005: 創建Agent協調器
        # 創建 Agent 協調器 (使用使用者選擇的模型)

        orchestrator = await create_practical_agent_orchestrator(chat_service)
        if not orchestrator:
            raise ValueError("無法初始化 Agent 協調器")

        # 流程編號 #006: 動態能力註冊 - 根據features啟用相應功能
        # 根據 features 動態添加能力

        capabilities_added = []
        if request.features:
            if request.features.web_search:
                if orchestrator.add_web_search_capability():
                    capabilities_added.append("web_search")
            if request.features.image_generation:

                # TODO: 添加圖像生成能力

                logger.info(f"[{request_id}] Image generation 功能尚未實現")
                pass
            if request.features.code_interpreter:

                # TODO: 添加代碼解釋器能力

                logger.info(f"[{request_id}] Code interpreter 功能尚未實現")
                pass
        logger.info(f"[{request_id}] Agent 模式啟用功能: {capabilities_added}")

        # 準備 features 參數

        features_dict = {}
        if request.features:

            # 直接檢查具體的功能開關

            if request.features.web_search:
                features_dict["web_search"] = True
            if request.features.image_generation:
                features_dict["image_generation"] = True
            if request.features.code_interpreter:
                features_dict["code_interpreter"] = True
            logger.info(f"[{request_id}] Agent 模式啟用功能: {list(features_dict.keys())}")

        # 流程編號 #007: 處理用戶請求 - 調用Agent協調器
        # 處理請求

        result = await orchestrator.process_request(user_input, features_dict)

        # 流程編號 #050: 格式轉換 - 將Agent結果轉為OpenAI格式
        # 轉換為 OpenAI 兼容格式

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
            model=request.model,
            choices=[choice],
            usage=usage
        )

        # 記錄對話歷史（用於除錯）

        conversation_history = orchestrator.get_conversation_history()
        if conversation_history:
            logger.info(f"[{request_id}] Agent 對話歷史: {len(conversation_history)} 輪交互")
        logger.info(f"[{request_id}] Agent 模式處理完成")
        return response
    except Exception as e:
        logger.error(f"[{request_id}] Agent 模式處理失敗: {e}")
        import traceback

        logger.error(f"[{request_id}] 錯誤堆疊: {traceback.format_exc()}")
        raise

async def create_chat_service_for_model(model_name: str, model_config: Dict[str, Any]) -> ChatCompletionClientBase:
    """
    為指定模型創建聊天服務
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

# 流程編號 #001: API請求入口點 - 接收聊天完成請求
# 此處是整個聊天流程的起點，所有的對話請求都會經過這裡
@router.post("/api/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """
    創建聊天完成 - 支援傳統模式和 Agent 模式
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

        # 特別檢查 features 字段

        logger.info(f"[{request_id}] Features 原始值: {request.features}")
        logger.info(f"[{request_id}] Features 類型: {type(request.features)}")
        if request.features:
            logger.info(f"[{request_id}] Features 內容: web_search={request.features.web_search}, image_generation={request.features.image_generation}, code_interpreter={request.features.code_interpreter}")
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
            logger.info(f"[{request_id}] Features 內容: web_search={request.features.web_search}, image_generation={request.features.image_generation}, code_interpreter={request.features.code_interpreter}")

        # 流程編號 #002: 模式決策點 - 判斷使用Agent模式或直接模式
        # 根據前端傳來的features參數決定處理方式

        agent_mode_enabled = False
        if request.features:

            # 檢查是否有任何功能啟用

            agent_mode_enabled = (request.features.web_search or
                                request.features.image_generation or
                                request.features.code_interpreter)
            if agent_mode_enabled:
                logger.info(f"[{request_id}] 偵測到 features 參數，進入 Agent 模式")
                enabled_features = []
                if request.features.web_search:
                    enabled_features.append("web_search")
                if request.features.image_generation:
                    enabled_features.append("image_generation")
                if request.features.code_interpreter:
                    enabled_features.append("code_interpreter")
                logger.info(f"[{request_id}] 啟用功能: {enabled_features}")
        else:
            logger.info(f"[{request_id}] 前端未指定功能，使用基本聊天模式")

        # 流程編號 #003A: Agent模式分支 - 進入多Agent協作流程
        # 當啟用任何特殊功能時走此分支

        if agent_mode_enabled:
            try:
                response = await handle_agent_mode_request(request)

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
                logger.error(f"[{request_id}] Agent 模式失敗，嘗試降級到傳統模式: {e}")

                # 降級到傳統模式

                agent_mode_enabled = False

        # 流程編號 #003B: 直接模式分支 - 使用基本聊天功能（不啟用特殊功能時）
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

            # Use ModelExecutor with built-in auto routing

            executor = get_default_executor()
            exec_result = await executor.generate(
                model_name=request.model,  # Pass 'auto' directly to executor
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                features=request.features,
                security_ctx=security_ctx
            )

            # Convert ModelExecutor result to ChatCompletionResponse

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

            # Enterprise-grade token usage tracking

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

            # Log routing information for enterprise observability

            if routing_meta:
                raw_conf = routing_meta.get('confidence')
                if isinstance(raw_conf, (int, float)):
                    confidence_str = f"{raw_conf:.3f}"
                else:
                    confidence_str = "n/a"
                logger.info(
                    f"[{request_id}] Auto-routing: {actual_model} "
                    f"(intent={routing_meta.get('intent')}, confidence={confidence_str})"
                )
            logger.info(f"[{request_id}] Chat completion successful - Model: {actual_model}, "
                       f"Tokens: {usage_obj.total_tokens}, "
                       f"Latency: {exec_result.get('meta', {}).get('latency_ms', 0)}ms")
            return response
    except HTTPException:

        # 追蹤失敗的請求

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

        # 追蹤系統錯誤

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

        logger.error(f"[{request_id}] 錯誤堆疊: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@router.get("/api/chat/models")
async def get_chat_models(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """取得支援聊天的模型列表"""
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

        # 獲取已加載的模型數量

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

# @router.get("/api/chat/agent/status")
# async def get_agent_status():
#     """獲取 Agent 模式狀態"""
#     try:
#         # 創建一個測試用的聊天服務來檢查 Agent 可用性
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
#         logger.error(f"獲取 Agent 狀態失敗: {e}")
#         return {
#             "status": "error",
#             "agent_mode": "disabled",
#             "error": str(e),
#             "timestamp": datetime.now().isoformat()
#         }
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
                "description": "Web Search Plugin - 提供網路搜尋功能",
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
