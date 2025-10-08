from fastapi import APIRouter, HTTPException, Request
from typing import List, Dict, Optional, Any, AsyncGenerator
from pydantic import BaseModel
import time
import logging
import json
import asyncio
import uuid
from datetime import datetime
from lyrallm.config.config_manager import config_manager

# Token tracking imports - 高性能版本
from logger_service import TokenUsage
from logger_service.event_bus import event_bus
from logger_service.token_calculator import compute_token_usage

# Semantic Kernel imports
import lyrallm as sk
from lyrallm.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from lyrallm.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from lyrallm.contents.chat_history import ChatHistory
from lyrallm.contents.chat_message_content import ChatMessageContent
from lyrallm.connectors.ai import FunctionChoiceBehavior
from lyrallm.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings



logger = logging.getLogger(__name__)
router = APIRouter()

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

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

class SemanticKernelService:
    """Semantic Kernel 服務類別"""
    
    def __init__(self):
        self.kernels = {}  # 存儲不同模型的 kernel 實例
        self.chat_services = {}  # 存儲聊天服務實例
    
    async def get_kernel_for_model(self, model_name: str) -> sk.Kernel:
        """取得指定模型的 Semantic Kernel 實例"""
        if model_name in self.kernels:
            return self.kernels[model_name]

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
        
        self.kernels[model_name] = kernel
        return kernel
    
    async def create_chat_completion(self, model_name: str, messages: List[ChatMessage], 
                                   temperature: float = 0.7, max_tokens: Optional[int] = None) -> ChatCompletionResponse:
        """使用 Semantic Kernel 創建聊天完成"""
        try:
            kernel = await self.get_kernel_for_model(model_name)
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
            
            # 啟用函數調用（工具選擇）
            if hasattr(execution_settings, 'function_choice_behavior'):
                execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
                logger.info(f"Enabled function calling for model: {model_name}")
            
            # 執行聊天完成
            response = await chat_completion.get_chat_message_contents(
                chat_history=chat_history,
                settings=execution_settings
            )
            
            if not response:
                raise ValueError("No response from chat completion service")
            
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
    

# 全域服務實例
sk_service = SemanticKernelService()
# Event-driven: use in-process event bus to publish TokenUsage events
from logger_service.event_bus import event_bus as global_event_bus

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

@router.post("/api/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """
    創建聊天完成 - 使用 Semantic Kernel 框架 + 企業級 Token Tracking
    """
    # 生成唯一請求 ID
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()
    
    try:
        logger.info(f"[{request_id}] 收到聊天請求 - 模型: {request.model}")
        
        # 檢查模型是否存在和啟用
        model_config = config_manager.get_model_by_name(request.model)
        if not model_config:
            logger.error(f"[{request_id}] 模型不存在: {request.model}")
            raise HTTPException(status_code=404, detail=f"Model '{request.model}' not found")
        
        if not model_config.get('enabled', False):
            logger.error(f"[{request_id}] 模型未啟用: {request.model}")
            raise HTTPException(status_code=400, detail=f"Model '{request.model}' is disabled")
        
        logger.info(f"[{request_id}] 使用 Semantic Kernel 處理聊天請求 - 模型: {request.model}, 訊息數: {len(request.messages)}")
        
        # 使用 Semantic Kernel 服務處理聊天完成
        response = await sk_service.create_chat_completion(
            model_name=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        

        # === 企業級 Token Usage Tracking ===
        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=response.usage,
            start_time=start_time,
            status="success",
            messages=request.messages,
            response_text=str(response.choices[0].message.content) if response and getattr(response, 'choices', None) else str(response)
        )
        
        logger.info(f"[{request_id}] Semantic Kernel 聊天完成成功 - 模型: {request.model}")
        
        # 將 request_id 加入回應 header 方便追蹤
        response.id = request_id
        
        return response
        
    except HTTPException:
        # 追蹤失敗的請求
        await track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="http_error",
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
            messages=request.messages
        )
        
        logger.error(f"[{request_id}] 聊天完成失敗: {e}")
        import traceback
        logger.error(f"[{request_id}] 錯誤堆疊: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@router.get("/api/chat/models")
async def get_chat_models():
    """取得支援聊天的模型列表"""
    try:
        available_models = config_manager.get_available_models()
        
        chat_models = []
        for model in available_models:
            chat_models.append({
                "id": model["name"],
                "name": model["name"],
                "provider": model.get("provider", ""),
                "description": model.get("description", ""),
                "max_tokens": model.get("max_completion_tokens") or model.get("max_tokens", 4096),
                "temperature": model.get("temperature", 0.7)
            })
        
        return {
            "object": "list",
            "data": chat_models
        }
        
    except Exception as e:
        logger.error(f"取得聊天模型失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat models: {str(e)}")

@router.get("/api/chat/health")
async def chat_health_check():
    """聊天服務健康檢查 + Token Tracking 狀態"""
    try:
        event_status = get_queue_status()
        # check postgres health (non-blocking wrapper)
        from logger_service.db_client import postgres_health
        try:
            pg_health = await postgres_health()
        except Exception:
            pg_health = {"connected": False}

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "semantic_kernel": "ready",
                "event_bus": "running" if event_status.get("running") else "stopped",
                "postgres": "connected" if pg_health.get("connected") else "disconnected",
                "token_tracking": "enabled"
            },
            "event_bus_info": event_status,
            "postgres_info": pg_health,
            "models_loaded": len(sk_service.kernels)
        }
        
    except Exception as e:
        logger.error(f"健康檢查失敗: {e}")
        raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")