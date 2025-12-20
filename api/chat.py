from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Dict, Optional, Any, AsyncGenerator
import time
import logging
import json
import asyncio
import uuid
from datetime import datetime
import httpx

from lyrallm.auth.dependencies import RequestSecurityContext, get_request_security_context
from lyrallm.config.config_manager import config_manager
from lyrallm.logger_service import TokenUsage
from lyrallm.logger_service.event_bus import event_bus as global_event_bus
from lyrallm.logger_service.token_calculator import compute_token_usage
from lyrallm.services.chat_service import ChatService
from lyrallm.api.schemas import (
    ChatMessage, Features, ChatCompletionRequest, ChatCompletionResponse, 
    ChatCompletionChoice, ChatCompletionUsage, FeedbackRequest
)
from lyrallm.core.exceptions import LyraError

logger = logging.getLogger(__name__)
router = APIRouter()
chat_service = ChatService()

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
                    try:
                        data = json.loads(body_str)
                        if 'features' in data:
                            self.logger.info(f"🎯 發現 features 參數: {data['features']}")
                        else:
                            self.logger.info(f"❌ 請求中沒有 features 參數")
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ JSON 解析失敗: {e}")
            except Exception as e:
                self.logger.error(f"❌ 讀取請求內容失敗: {e}")

request_logger = RequestLoggingMiddleware()

def _extract_text_from_stream_payload(payload: Dict[str, Any]) -> str:
    """Extract text delta from streaming payload."""
    if not isinstance(payload, dict):
        return ""
    
    # Handle standard OpenAI format
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

    # Handle internal format
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

async def track_token_usage(request_id: str, model_name: str, usage: Optional[ChatCompletionUsage],
                          start_time: datetime, status: str, user_id: Optional[str] = None, messages: Optional[List[ChatMessage]] = None, response_text: Optional[str] = None):
    """
    設定的 Token Usage 追蹤
    """
    try:
        cost_usd = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        
        if usage and getattr(usage, 'total_tokens', 0) > 0:
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            
            model_config = config_manager.get_model_by_name(model_name)
            if model_config:
                input_cost_per_1k = model_config.get('input_cost_per_1k', 0.001)
                output_cost_per_1k = model_config.get('output_cost_per_1k', 0.002)
                cost_usd = (prompt_tokens / 1000) * input_cost_per_1k + (completion_tokens / 1000) * output_cost_per_1k
        else:
            model_config = config_manager.get_model_by_name(model_name)
            msgs = messages or []
            resp_text = response_text or ''
            # Convert Pydantic models to dicts if needed for calculator
            msgs_dicts = [m.model_dump() if hasattr(m, 'model_dump') else m for m in msgs]
            
            calc = compute_token_usage(None, msgs_dicts, model_name, model_config, resp_text)
            prompt_tokens = calc.get('prompt_tokens', 0)
            completion_tokens = calc.get('completion_tokens', 0)
            total_tokens = calc.get('total_tokens', prompt_tokens + completion_tokens)
            cost_usd = calc.get('cost_usd', 0.0)

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

        try:
            global_event_bus.publish(token_usage.model_dump())
            logger.debug(f"[{request_id}] Token usage published to EventBus")
        except Exception as e:
            logger.error(f"[{request_id}] Token tracking error: {e}")
    except Exception as e:
        logger.error(f"[{request_id}] Token tracking preparation error: {e}")

def get_queue_status():
    """Return EventBus status for health checks."""
    try:
        return {
            "queue_length": global_event_bus.queue_size(),
            "subscribers": global_event_bus.subscriber_count(),
            "running": global_event_bus.is_running()
        }
    except Exception as e:
        logger.error(f"Failed to get event bus status: {e}")
        return {"queue_length": -1, "subscribers": 0, "running": False}

@router.post("/api/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    raw_request: Request,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """
    創建聊天完成 - 使用 ChatService 統一處理
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()
    await request_logger.log_request_body(raw_request)

    # 預設插入繁體中文 system message
    if not any(msg.role == "system" for msg in request.messages):
        request.messages.insert(0, ChatMessage(role="system", content="你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"))

    try:
        logger.info(f"[{request_id}] 收到用戶請求 - 模型: {request.model}")

        # 串流處理
        if request.stream:
            async def stream_generator():
                full_text = ""
                final_model = request.model
                
                try:
                    async for event in chat_service.process_agent_stream(
                        request.messages, request.model, request.features, security_ctx, request_id
                    ):
                        event_type = event.get("type")
                        
                        if event_type == "info":
                            final_model = event.get("model", final_model)
                            yield _format_sse(event)
                        
                        elif event_type == "response_chunk" or event_type == "delta":
                            text = event.get("content") or event.get("text") or ""
                            full_text += text
                            payload = {
                                "type": "delta",
                                "model": final_model,
                                "text": text,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None
                                }]
                            }
                            yield _format_sse(payload)
                            
                        elif event_type in ["thought", "tool_start", "tool_end"]:
                            yield _format_sse(event)
                            
                        elif event_type == "error":
                            yield _format_sse({"error": event.get("content")})
                            
                    yield b"data: [DONE]\n\n"
                    
                    # Track usage after stream ends
                    asyncio.create_task(track_token_usage(
                        request_id=request_id,
                        model_name=final_model,
                        usage=None, # Will be calculated from text
                        start_time=start_time,
                        status="success",
                        user_id=security_ctx.user_id,
                        messages=request.messages,
                        response_text=full_text
                    ))
                    
                except Exception as e:
                    logger.error(f"[{request_id}] Streaming error: {e}")
                    yield _format_sse({"error": str(e)})
                    yield b"data: [DONE]\n\n"
                    
                    asyncio.create_task(track_token_usage(
                        request_id=request_id,
                        model_name=final_model,
                        usage=None,
                        start_time=start_time,
                        status="error",
                        user_id=security_ctx.user_id,
                        messages=request.messages
                    ))

            headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
            return StreamingResponse(stream_generator(), media_type="text/event-stream", headers=headers)

        # 非串流處理
        else:
            response_text = await chat_service.process_agent_request(
                request.messages, request.model, request.features, security_ctx, request_id
            )
            
            prompt_tokens = sum(len(msg.content.split()) for msg in request.messages)
            completion_tokens = len(response_text.split())
            
            usage = ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
            
            choice = ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=response_text),
                finish_reason="stop"
            )
            
            response = ChatCompletionResponse(
                id=request_id,
                created=int(time.time()),
                model=request.model,
                choices=[choice],
                usage=usage
            )
            
            asyncio.create_task(track_token_usage(
                request_id=request_id,
                model_name=request.model,
                usage=usage,
                start_time=start_time,
                status="success",
                user_id=security_ctx.user_id,
                messages=request.messages,
                response_text=response_text
            ))
            
            return response

    except LyraError as e:
        # Business logic errors
        logger.warning(f"[{request_id}] Business error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[{request_id}] System error: {e}")
        asyncio.create_task(track_token_usage(
            request_id=request_id,
            model_name=request.model,
            usage=None,
            start_time=start_time,
            status="system_error",
            user_id=security_ctx.user_id,
            messages=request.messages
        ))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/chat/models")
async def get_chat_models(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """獲取支援聊天的模型列表"""
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
        return {
            "object": "list",
            "data": chat_models
        }
    except Exception as e:
        logger.error(f"獲取支援聊天的模型列表失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get chat models: {str(e)}")

@router.post("/api/chat/feedback")
async def submit_chat_feedback(
    payload: FeedbackRequest,
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """Record lightweight chat feedback."""
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
async def chat_health_check(
    security_ctx: RequestSecurityContext = Depends(get_request_security_context),
):
    """獲取聊天服務的健康檢查"""
    try:
        event_status = get_queue_status()
        
        # Check postgres
        from lyrallm.logger_service.db_client import postgres_health
        try:
            pg_health = await postgres_health()
        except Exception:
            pg_health = {"connected": False}

        available_models = config_manager.get_available_models()
        models_count = len([m for m in available_models if m.get('enabled', False)])
        
        services = {
            "semantic_kernel": "ready",
            "event_bus": "running" if event_status.get("running") else "stopped",
            "postgres": "connected" if pg_health.get("connected") else "disconnected",
            "token_tracking": "enabled",
        }

        # Ollama check
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

@router.get("/api/chat/features")
async def get_available_features():
    """獲取所有可用功能列表"""
    try:
        available_features = ["web_search", "image_generation"]
        feature_details = [
            {
                "name": "web_search",
                "description": "Web Search Plugin - 提供網路搜尋功能",
                "require_config": True,
                "plugin_id": "web_search"
            },
            {
                "name": "image_generation",
                "description": "Image Generation Plugin - 提供圖像生成能力",
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
        logger.error(f"獲取可用功能失敗: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get available features: {str(e)}")

