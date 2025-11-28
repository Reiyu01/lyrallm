import time
import logging
import asyncio
import json
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator
from lyrallm.config.config_manager import config_manager
from lyrallm.auth.dependencies import RequestSecurityContext
from .model_manager import get_model_manager_sync

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.connectors.ai import FunctionChoiceBehavior

import httpx

logger = logging.getLogger(__name__)


class ModelExecutor:
    """Enterprise-grade Model Executor with intelligent routing.
    
    Features:
    - Auto model selection via semantic routing
    - Multi-provider support (Azure OpenAI, OpenAI, Ollama)
    - Kernel caching for performance
    - Comprehensive error handling and fallback strategies
    - Token usage tracking
    """

    def __init__(self):
        # Kernel cache for performance optimization
        self._kernel_cache: Dict[str, sk.Kernel] = {}

    async def generate(self, model_name: str, messages: Optional[List[Any]] = None,
                       temperature: float = 0.7, max_tokens: Optional[int] = None,
                       features: Optional[dict] = None,
                       security_ctx: Optional[RequestSecurityContext] = None) -> Dict[str, Any]:
        """Generate response with intelligent model routing.
        
        Args:
            model_name: Target model name or 'auto' for intelligent routing
            messages: Chat message history
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            features: Feature flags for agent capabilities
            
        Returns:
            Standardized response dict with choices, usage, and metadata
        """
        start_time = time.time()
        request_id = f"req_{int(time.time() * 1000)}"
        
        try:
            # Fast path: 明確指定模型時跳過路由檢查
            if model_name != 'auto':
                # Provide basic routing info for explicit models
                routing_info = {
                    "model": model_name,
                    "routing_method": "explicit",
                }
                logger.debug(f"[{request_id}] Using explicitly specified model: {model_name}")
            else:
                # Auto routing path
                model_name, routing_info = await self._route_model(messages, request_id)
                logger.debug(f"[{request_id}] Auto-routed to: {model_name}")
                # Validate routed model exists and is enabled
                if not self._is_model_available(model_name):
                    logger.warning(f"[{request_id}] Routed model {model_name} unavailable, using fallback")
                    model_name = self._get_fallback_model()
                
                # Apply security policies only for auto-routed models
                if security_ctx and routing_info:
                    model_name, routing_info = self._enforce_security_policies(
                        model_name, routing_info, security_ctx, request_id
                    )

            # Get model configuration
            t2 = time.time()
            model_cfg = config_manager.get_model_by_name(model_name) or {}
            provider = model_cfg.get('provider', '')
            logger.info(f"[{request_id}] ⏱️ Config lookup: {(time.time()-t2)*1000:.1f}ms")

            # Handle fake/test models
            if provider == 'fake' or model_name == 'fake':
                return self._generate_fake_response(model_name, messages, start_time)

            # Validate model availability
            if not model_cfg:
                raise ValueError(f"Model '{model_name}' not found in configuration")
            
            if not model_cfg.get('enabled', False):
                raise ValueError(f"Model '{model_name}' is disabled")

            # Generate response using real model
            t3 = time.time()
            result = await self._generate_real_response(
                model_name, model_cfg, messages, temperature, max_tokens, 
                features, start_time, request_id, routing_info
            )
            logger.info(f"[{request_id}] ⏱️ Model execution: {(time.time()-t3)*1000:.1f}ms")
            
            # Record success metrics
            model_manager = get_model_manager_sync()
            if model_manager:
                latency_ms = result.get('meta', {}).get('latency_ms', 0)
                model_manager.record_request_success(model_name, latency_ms)
            
            return result
            
        except Exception as e:
            logger.error(f"[{request_id}] Generation failed for model {model_name}: {e}")
            
            # Record failure metrics
            model_manager = get_model_manager_sync()
            if model_manager:
                model_manager.record_request_failure(model_name, str(e))
            
            # Enterprise fallback strategy
            return await self._handle_generation_failure(model_name, messages, start_time, str(e))

    def _enforce_security_policies(
        self,
        model_name: str,
        routing_info: Dict[str, Any],
        security_ctx: RequestSecurityContext,
        request_id: str
    ) -> Tuple[str, Dict[str, Any]]:
        """Apply role-based routing policies (e.g. sensitive fallbacks)."""
        policies = dict(security_ctx.routing_policies or {})
        if not policies:
            return model_name, routing_info

        category = (routing_info or {}).get('category')
        if not category:
            return model_name, routing_info

        normalized_category = str(category).upper()
        raw_sensitive = policies.get('sensitive_categories') or []
        if isinstance(raw_sensitive, str):
            sensitive_categories = {raw_sensitive.upper()}
        else:
            sensitive_categories = {str(item).upper() for item in raw_sensitive}

        if normalized_category not in sensitive_categories:
            return model_name, routing_info

        fallback_model = (
            policies.get('sensitive_fallback_model')
            or policies.get('sensitive_fallback')
            or policies.get('fallback_model')
            or policies.get('fallback')
        )

        if not fallback_model or fallback_model == model_name:
            return model_name, routing_info

        if not self._is_model_available(fallback_model):
            logger.warning(
                "[%s] Sensitive fallback model '%s' unavailable; keeping routed model '%s'",
                request_id,
                fallback_model,
                model_name,
            )
            return model_name, routing_info

        updated_info = dict(routing_info or {})
        updated_info['policy_enforced_model'] = fallback_model
        actions = list(updated_info.get('policy_actions', []))
        actions.append({
            'type': 'sensitive_category_fallback',
            'category': normalized_category,
            'target_model': fallback_model,
        })
        updated_info['policy_actions'] = actions

        logger.info(
            "[%s] Applied sensitive routing policy: %s -> %s due to category %s",
            request_id,
            model_name,
            fallback_model,
            normalized_category,
        )
        return fallback_model, updated_info

    async def _route_model(self, messages: Optional[List[Any]], request_id: str) -> Tuple[str, Dict]:
        """Intelligent model routing based on message content and model health."""
        try:
            # Extract query for routing
            query = self._extract_routing_query(messages)
            if not query.strip():
                logger.warning(f"[{request_id}] Empty query for routing, using default model")
                return self._get_fallback_model(), {}

            logger.debug(f"[{request_id}] Routing query: '{query[:100]}...'")
            
            # Use RouterV1: SLM analyzer + rule engine (slm_rules strategy)
            from .router_v1 import RouterV1
            router = RouterV1()
            routing_info = await router.route(query)
            intent = routing_info.get('intent', 'qa_general')
            confidence = routing_info.get('confidence', 0.0)
            selected_model = routing_info.get('model')
            
            # Get model recommendation from health-aware manager
            model_manager = get_model_manager_sync()
            if model_manager:
                best = model_manager.get_best_model_for_intent(intent)
                if best:
                    routing_info.update({
                        'selected_model': best,
                        'selection_reason': 'health_aware_routing',
                        'intent': intent,
                        'confidence': confidence
                    })
                    return best, routing_info
            
            # Fallback to selected or traditional routing
            if not selected_model or not self._is_model_available(selected_model):
                logger.warning(f"[{request_id}] Routed model unavailable, using fallback")
                selected_model = self._get_fallback_model()
            
            return selected_model, routing_info
            
        except Exception as e:
            logger.error(f"[{request_id}] Auto routing failed: {e}")
            return self._get_fallback_model(), {'error': str(e)}

    def _extract_routing_query(self, messages: Optional[List[Any]]) -> str:
        """Extract query text for routing."""
        if not messages:
            return ""
            
        user_messages = [
            (getattr(m, 'content', None) or m.get('content', '')) 
            for m in messages 
            if (getattr(m, 'role', None) or m.get('role')) == 'user'
        ]
        return user_messages[-1] if user_messages else ""

    def _is_model_available(self, model_name: str) -> bool:
        """Check if model is available and enabled."""
        model_config = config_manager.get_model_by_name(model_name)
        return model_config and model_config.get('enabled', False)

    def _get_fallback_model(self) -> str:
        """Get fallback model with health checking."""
        model_manager = get_model_manager_sync()
        
        if model_manager:
            healthy_models = model_manager.get_healthy_models()
            if healthy_models:
                return healthy_models[0]  # Return first healthy model
        
        # Final fallback to config default
        return config_manager.get_default_model() or "gpt-4o"

    def _generate_fake_response(self, model_name: str, messages: Optional[List[Any]], start_time: float) -> Dict[str, Any]:
        """Generate fake response for testing."""
        last_msg = ""
        if messages and len(messages) > 0:
            last_msg = getattr(messages[-1], 'content', None) or messages[-1].get('content', '') if isinstance(messages[-1], dict) else str(messages[-1])
        
        text = f'[FAKE {model_name}] Response to: {last_msg}'
        usage = {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}
        
        return {
            'id': f'chatcmpl-fake-{int(time.time())}',
            'created': int(time.time()),
            'model': model_name,
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
            'usage': usage,
            'text': text,
            'meta': {'latency_ms': int((time.time() - start_time) * 1000), 'provider': 'fake'}
        }

    async def _generate_real_response(self, model_name: str, model_cfg: Dict, messages: Optional[List[Any]], 
                                    temperature: float, max_tokens: Optional[int], features: Optional[dict],
                                    start_time: float, request_id: str, routing_info: Optional[Dict]) -> Dict[str, Any]:
        """Generate response using real model providers."""
        # Build or reuse kernel
        t_kernel_start = time.time()
        kernel = await self._get_kernel_for_model(model_name)
        logger.info(f"[{request_id}] ⏱️ Kernel creation: {(time.time()-t_kernel_start)*1000:.1f}ms")
        if kernel is None:
            raise RuntimeError(f"Could not create kernel for model {model_name}")

        # Prepare chat history
        t_history = time.time()
        chat_history = ChatHistory()
        if messages:
            for m in messages:
                role = getattr(m, 'role', None) or m.get('role', 'user') if isinstance(m, dict) else 'user'
                content = getattr(m, 'content', None) or m.get('content', '') if isinstance(m, dict) else str(m)
                
                if role == 'system':
                    chat_history.add_system_message(content)
                else:
                    chat_history.add_message(ChatMessageContent(role=role, content=content))
        else:
            chat_history.add_message(ChatMessageContent(role='user', content=''))
        logger.info(f"[{request_id}] ⏱️ Chat history prep: {(time.time()-t_history)*1000:.1f}ms")

        # Get chat completion service
        try:
            chat_completion = kernel.get_service(type=ChatCompletionClientBase)
        except Exception as e:
            logger.error(f"[{request_id}] Failed to get chat completion service for {model_name}: {e}")
            raise

        # Configure execution settings
        t_exec_settings = time.time()
        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )
        
        # Apply generation parameters
        self._apply_generation_settings(execution_settings, model_cfg, temperature, max_tokens)
        
        # Configure plugins/functions if available
        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):
            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
            logger.debug(f"[{request_id}] Enabled function calling for {model_name}")
        logger.info(f"[{request_id}] ⏱️ Execution settings: {(time.time()-t_exec_settings)*1000:.1f}ms")

        # Execute model inference
        try:
            logger.debug(f"[{request_id}] Calling {model_name} (provider: {model_cfg.get('provider')})")
            
            t_api_call = time.time()
            if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):
                response = await chat_completion.get_chat_message_contents(
                    chat_history=chat_history, settings=execution_settings, kernel=kernel
                )
            else:
                response = await chat_completion.get_chat_message_contents(
                    chat_history=chat_history, settings=execution_settings
                )
            api_latency = (time.time()-t_api_call)*1000
            logger.info(f"[{request_id}] ⏱️ 🔥 ACTUAL API CALL: {api_latency:.1f}ms")

            if not response:
                raise RuntimeError('Empty response from model provider')

            # Extract and normalize response content
            response_text = str(response[0].content)
            normalized_text = response_text
            raw_payload = None
            try:
                parsed_payload = json.loads(response_text)
                if isinstance(parsed_payload, dict):
                    raw_payload = parsed_payload
                    candidate = (
                        parsed_payload.get('response')
                        or parsed_payload.get('message')
                        or parsed_payload.get('content')
                        or parsed_payload.get('text')
                    )
                    if isinstance(candidate, str) and candidate.strip():
                        normalized_text = candidate
            except json.JSONDecodeError:
                pass

            # Calculate token usage (best effort)
            usage = self._calculate_usage(messages, normalized_text)

            # Ensure routing info reflects the actual model used
            updated_routing = dict(routing_info or {})
            updated_routing['model'] = model_name

            # Build standardized response
            meta = {
                'latency_ms': int((time.time() - start_time) * 1000),
                'provider': model_cfg.get('provider'),
                'routing_info': updated_routing,
                'plugins_used': plugins_available
            }
            if raw_payload is not None:
                meta['raw_response'] = raw_payload

            result = {
                'id': f'chatcmpl-{int(time.time())}-{request_id}',
                'created': int(time.time()),
                'model': model_name,
                'choices': [{
                    'index': 0, 
                    'message': {'role': 'assistant', 'content': normalized_text}, 
                    'finish_reason': 'stop'
                }],
                'usage': usage,
                'text': normalized_text,
                'meta': meta
            }
            
            logger.debug(f"[{request_id}] Response generated successfully ({usage['total_tokens']} tokens)")
            return result

        except Exception as e:
            logger.error(f"[{request_id}] Model execution failed for {model_name}: {e}")
            raise

    def _prepare_message_payload(self, messages: Optional[List[Any]]) -> List[Dict[str, str]]:
        """Convert incoming messages to OpenAI-compatible payload."""
        payload: List[Dict[str, str]] = []
        if messages:
            for message in messages:
                if isinstance(message, dict):
                    role = str(message.get("role", "user") or "user")
                    content = str(message.get("content", "") or "")
                else:
                    role = getattr(message, "role", "user") or "user"
                    content = getattr(message, "content", None)
                    if content is None:
                        content = str(message)
                payload.append({"role": role, "content": content})
        if not payload:
            payload.append({"role": "user", "content": ""})
        return payload

    def _extract_text_from_chunk(self, payload: Dict[str, Any]) -> str:
        """Extract incremental text from provider streaming payload."""
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

    async def _stream_provider(
        self,
        model_cfg: Dict[str, Any],
        provider: str,
        messages_payload: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Provider-specific streaming yielding OpenAI-compatible chunks."""
        if provider == "azure_openai":
            async for event in self._stream_azure_openai(model_cfg, messages_payload, temperature, max_tokens):
                yield event
            return
        if provider == "openai":
            async for event in self._stream_openai(model_cfg, messages_payload, temperature, max_tokens):
                yield event
            return
        if provider == "ollama":
            async for event in self._stream_ollama(model_cfg, messages_payload, temperature, max_tokens):
                yield event
            return

        raise ValueError(f"Streaming not supported for provider: {provider}")

    async def _stream_azure_openai(
        self,
        model_cfg: Dict[str, Any],
        messages_payload: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        provider_cfg = config_manager.get_provider_config("azure_openai") or {}
        endpoint = model_cfg.get("endpoint") or provider_cfg.get("endpoint")
        api_key = model_cfg.get("api_key") or provider_cfg.get("api_key")
        api_version = model_cfg.get("api_version") or provider_cfg.get("api_version")
        deployment = model_cfg.get("deployment_name") or model_cfg.get("name")

        if not endpoint or not api_key or not deployment or not api_version:
            raise RuntimeError("Azure OpenAI streaming configuration is incomplete")

        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        params = {"api-version": api_version}
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "messages": messages_payload,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, headers=headers, params=params, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data_str = line[6:] if line.startswith("data:") else line
                    data_str = data_str.strip()
                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    yield event

    async def _stream_openai(
        self,
        model_cfg: Dict[str, Any],
        messages_payload: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        provider_cfg = config_manager.get_provider_config("openai") or {}
        base_url = (
            model_cfg.get("endpoint")
            or provider_cfg.get("base_url")
            or provider_cfg.get("endpoint")
            or "https://api.openai.com/v1"
        )
        api_key = model_cfg.get("api_key") or provider_cfg.get("api_key")
        model_name = model_cfg.get("name")

        if not api_key or not model_name:
            raise RuntimeError("OpenAI streaming configuration is incomplete")

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages_payload,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data_str = line[6:] if line.startswith("data:") else line
                    data_str = data_str.strip()
                    if not data_str:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    yield event

    async def _stream_ollama(
        self,
        model_cfg: Dict[str, Any],
        messages_payload: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        provider_cfg = config_manager.get_provider_config("ollama") or {}
        base_url = model_cfg.get("endpoint") or provider_cfg.get("base_url") or "http://127.0.0.1:11434"
        model_name = model_cfg.get("name")
        if not model_name:
            raise RuntimeError("Ollama model name missing")

        url = f"{base_url.rstrip('/')}/api/chat"
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages_payload,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data_str = line.strip()
                    if not data_str:
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if "message" in event and isinstance(event["message"], dict):
                        content = event["message"].get("content")
                        if isinstance(content, str) and content:
                            yield {
                                "choices": [
                                    {
                                        "delta": {"content": content},
                                    }
                                ],
                            }
                    if event.get("done"):
                        break

    async def stream_generate(
        self,
        model_name: str,
        messages: Optional[List[Any]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        features: Optional[dict] = None,
        security_ctx: Optional[RequestSecurityContext] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming variant of generate() yielding chunk/meta events."""
        start_time = time.time()
        request_id = f"stream_{int(time.time() * 1000)}"
        original_model = model_name
        routing_info: Optional[Dict[str, Any]] = None

        try:
            # Handle auto routing
            if model_name == "auto":
                model_name, routing_info = await self._route_model(messages, request_id)
                logger.info(f"[{request_id}] (stream) Auto-routed to: {model_name}")
                if not self._is_model_available(model_name):
                    logger.warning(f"[{request_id}] (stream) Routed model {model_name} unavailable, using fallback")
                    model_name = self._get_fallback_model()
            else:
                # Even for explicit models, provide basic routing info for frontend
                routing_info = {
                    "model": model_name,
                    "routing_method": "explicit",
                    "original_model": original_model,
                }

            if security_ctx and routing_info:
                model_name, routing_info = self._enforce_security_policies(
                    model_name, routing_info, security_ctx, request_id
                )

            model_cfg = config_manager.get_model_by_name(model_name) or {}
            provider = model_cfg.get("provider", "")
            if not model_cfg or not model_cfg.get("enabled", False):
                raise ValueError(f"Model '{model_name}' is not available for streaming")

            if provider == "fake" or model_name == "fake":
                fake_response = self._generate_fake_response(model_name, messages, start_time)
                yield {
                    "type": "delta",
                    "payload": {
                        "choices": [{"delta": {"content": fake_response["text"]}}],
                        "model": model_name,
                        "routing_info": routing_info,
                    },
                }
                yield {"type": "final", "payload": fake_response}
                return

            messages_payload = self._prepare_message_payload(messages)
            if routing_info:
                yield {
                    "type": "info",
                    "payload": {
                        "model": model_name,
                        "routing_info": routing_info,
                    },
                }

            text_buffer = ""
            usage_from_provider: Optional[Dict[str, Any]] = None

            async for raw_event in self._stream_provider(
                model_cfg=model_cfg,
                provider=provider,
                messages_payload=messages_payload,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if not isinstance(raw_event, dict):
                    continue
                chunk = dict(raw_event)
                chunk.setdefault("model", model_name)
                if routing_info and "routing_info" not in chunk:
                    chunk["routing_info"] = routing_info

                delta_text = self._extract_text_from_chunk(chunk)
                if delta_text:
                    text_buffer += delta_text

                if isinstance(chunk.get("usage"), dict):
                    usage_from_provider = chunk["usage"]

                yield {"type": "delta", "payload": chunk}

            usage = usage_from_provider if isinstance(usage_from_provider, dict) else self._calculate_usage(messages, text_buffer)

            updated_routing = dict(routing_info or {})
            updated_routing["model"] = model_name

            meta = {
                "latency_ms": int((time.time() - start_time) * 1000),
                "provider": provider,
                "routing_info": updated_routing,
                "plugins_used": False,
            }

            result = {
                "id": f"chatcmpl-{int(time.time())}-{request_id}",
                "created": int(time.time()),
                "model": model_name,
                "choices": [],
                "usage": usage,
                "text": text_buffer,
                "meta": meta,
                "routing_info": updated_routing,
                "finish_reason": "stop",
                "final_message": {
                    "role": "assistant",
                    "content": text_buffer,
                },
            }

            yield {"type": "final", "payload": result}

            model_manager = get_model_manager_sync()
            if model_manager:
                model_manager.record_request_success(model_name, meta["latency_ms"])

        except Exception as e:
            logger.error(f"[{request_id}] Streaming generation failed for model {model_name}: {e}")
            model_manager = get_model_manager_sync()
            if model_manager:
                model_manager.record_request_failure(model_name, str(e))

            # Fallback to non-streaming response
            fallback = await self.generate(
                model_name=original_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                features=features,
                security_ctx=security_ctx,
            )

            if "routing_info" not in fallback and isinstance(fallback.get("meta"), dict):
                routing_from_meta = fallback["meta"].get("routing_info")
                if routing_from_meta:
                    fallback["routing_info"] = routing_from_meta

            fallback_text = (
                fallback.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            if fallback_text:
                yield {
                    "type": "delta",
                    "payload": {
                        "choices": [{"delta": {"content": fallback_text}}],
                        "model": fallback.get("model", model_name),
                        "routing_info": fallback.get("routing_info"),
                    },
                }
            fallback_finish_reason = None
            if isinstance(fallback.get("choices"), list) and fallback["choices"]:
                fallback_finish_reason = fallback["choices"][0].get("finish_reason")

            fallback_final = dict(fallback)
            fallback_final["choices"] = []
            if fallback_text and not fallback_final.get("text"):
                fallback_final["text"] = fallback_text
            fallback_final.setdefault("routing_info", fallback.get("routing_info"))
            fallback_final["final_message"] = {
                "role": "assistant",
                "content": fallback_text or "",
            }
            fallback_final["finish_reason"] = fallback_finish_reason or fallback_final.get("finish_reason", "stop")

            yield {"type": "final", "payload": fallback_final}

    def _apply_generation_settings(self, execution_settings, model_cfg: Dict, temperature: float, max_tokens: Optional[int]):
        """Apply generation parameters to execution settings."""
        # Some reasoning / structured models (o1/o3 family) may reject temperature
        model_name = model_cfg.get('deployment_name') or model_cfg.get('name') or ''
        provider = model_cfg.get('provider', '')
        
        if provider == 'ollama':
            logger.debug(f"Skipping temperature/max_tokens for Ollama model: {model_name}")
            return
        
        if not any(x in model_name for x in ['o1', 'o3']):
            try:
                execution_settings.temperature = temperature
            except AttributeError:
                logger.debug("Temperature setting not supported by this provider")
        else:
            logger.debug(f"Skip temperature for reasoning model: {model_name}")

        max_tokens_value = max_tokens or model_cfg.get('max_completion_tokens') or model_cfg.get('max_tokens')
        if max_tokens_value:
            try:
                execution_settings.max_completion_tokens = max_tokens_value
            except AttributeError:
                try:
                    execution_settings.max_tokens = max_tokens_value
                except AttributeError:
                    logger.debug("Max tokens setting not supported by this provider")

    def _calculate_usage(self, messages: Optional[List[Any]], response_text: str) -> Dict[str, int]:
        """Calculate token usage (simplified estimation)."""
        prompt_tokens = 0
        if messages:
            for m in messages:
                content = getattr(m, 'content', None) or m.get('content', '') if isinstance(m, dict) else str(m)
                prompt_tokens += len(content.split())
        
        completion_tokens = len(response_text.split())
        return {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens
        }

    async def _handle_generation_failure(self, model_name: str, messages: Optional[List[Any]], 
                                       start_time: float, error_msg: str) -> Dict[str, Any]:
        """Enterprise fallback strategy for generation failures."""
        logger.error(f"Generation failed for {model_name}: {error_msg}")
        
        # Try fallback to default model if not already using it
        default_model = config_manager.get_default_model()
        if model_name != default_model and default_model:
            logger.info(f"Attempting fallback to default model: {default_model}")
            try:
                return await self.generate(
                    model_name=default_model,
                    messages=messages,
                    temperature=0.7
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
        
        # Return error response in standard format
        return {
            'id': f'chatcmpl-error-{int(time.time())}',
            'created': int(time.time()),
            'model': model_name,
            'choices': [{
                'index': 0,
                'message': {
                    'role': 'assistant', 
                    'content': f'I apologize, but I encountered an error processing your request. Please try again later. (Error: {error_msg})'
                },
                'finish_reason': 'error'
            }],
            'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
            'text': 'Service temporarily unavailable',
            'meta': {
                'latency_ms': int((time.time() - start_time) * 1000),
                'error': error_msg,
                'fallback_attempted': model_name != default_model
            }
        }

    async def _get_kernel_for_model(self, model_name: str) -> Optional[sk.Kernel]:
        """Get or create a Semantic Kernel instance for the specified model."""
        cache_key = f"base_{model_name}"
        
        # Return cached kernel directly (Kernel is stateless and thread-safe)
        if cache_key in self._kernel_cache:
            logger.info(f"✅ Kernel cache HIT for {model_name} (cache size: {len(self._kernel_cache)})")
            return self._kernel_cache[cache_key]

        logger.warning(f"⚠️ Kernel cache MISS for {model_name} - creating new kernel (current cache: {list(self._kernel_cache.keys())})")
        
        # Create new kernel for model
        model_config = config_manager.get_model_by_name(model_name)
        if not model_config:
            logger.error(f"Model configuration not found: {model_name}")
            return None

        provider = model_config.get('provider')
        if not provider:
            logger.error(f"No provider specified for model: {model_name}")
            return None

        kernel = sk.Kernel()
        
        try:
            # Configure provider-specific service
            if provider == 'azure_openai':
                service = AzureChatCompletion(
                    service_id=f"azure_openai_{model_name}",
                    deployment_name=model_config.get('deployment_name'),
                    endpoint=model_config.get('endpoint'),
                    api_key=model_config.get('api_key'),
                    api_version=model_config.get('api_version')
                )
                kernel.add_service(service)
                
            elif provider == 'openai':
                service = OpenAIChatCompletion(
                    service_id=f"openai_{model_name}",
                    ai_model_id=model_name,
                    api_key=model_config.get('api_key'),
                    base_url=model_config.get('endpoint')
                )
                kernel.add_service(service)
                
            elif provider == 'ollama':
                import aiohttp
                import asyncio

                base_url = model_config.get('endpoint', 'http://127.0.0.1:11434')
                model_name = model_config.get('name')
                logger.info(f"Registering Ollama provider for {model_name} at {base_url}")

                class OllamaChatCompletion(ChatCompletionClientBase):
                    """Optimized Ollama connector using native /api/chat endpoint with async HTTP."""
                    def __init__(self, base_url: str, model_name: str):
                        super().__init__(service_id=f"ollama_{model_name}",
                                         ai_model_id=model_name)
                        self._base_url = base_url
                        self._model_name = model_name

                    async def get_chat_message_contents(self, chat_history: ChatHistory, settings=None, **kwargs):
                        # 使用 Ollama 原生 Chat API 格式（異步優化）
                        messages = []
                        for msg in chat_history.messages:
                            role = getattr(msg, 'role', 'user')
                            content = getattr(msg, 'content', '')
                            messages.append({"role": role, "content": content})

                        payload = {
                            "model": self._model_name,
                            "messages": messages,  # 使用結構化消息格式
                            "stream": False
                        }

                        logger.debug(f"Calling Ollama Chat API: {self._base_url}/api/chat, model={self._model_name}")

                        try:
                            # 使用異步 HTTP 客戶端避免阻塞事件循環
                            timeout = aiohttp.ClientTimeout(total=120)
                            async with aiohttp.ClientSession(timeout=timeout) as session:
                                async with session.post(
                                    f"{self._base_url}/api/chat",
                                    json=payload
                                ) as resp:
                                    resp.raise_for_status()
                                    result = await resp.json()
                            
                            # 提取響應內容
                            output = result.get("message", {}).get("content", "")
                            if not output:
                                logger.warning(f"Empty response from Ollama chat API")
                                output = ""
                            
                            return [ChatMessageContent(role="assistant", content=output.strip())]

                        except Exception as e:
                            logger.error(f"Ollama model execution failed: {e}")
                            raise

                # ✅ 註冊自定義 Ollama connector
                ollama_service = OllamaChatCompletion(base_url=base_url, model_name=model_name)
                kernel.add_service(ollama_service)
                
            else:
                logger.error(f"Unsupported provider '{provider}' for model {model_name}")
                return None
                
            # Cache the configured kernel
            self._kernel_cache[cache_key] = kernel
            logger.debug(f"Created and cached kernel for model: {model_name} (provider: {provider})")
            
            return kernel
            
        except Exception as e:
            logger.error(f"Failed to create kernel for {model_name}: {e}")
            return None

    def clear_cache(self):
        """Clear kernel cache - useful for configuration reloads."""
        self._kernel_cache.clear()
        self._router = None
        logger.info("ModelExecutor cache cleared")

    def get_cached_models(self) -> List[str]:
        """Get list of models with cached kernels."""
        return [key.replace("base_", "") for key in self._kernel_cache.keys()]


# module-level executor
_default_executor = ModelExecutor()


def get_default_executor() -> ModelExecutor:
    return _default_executor
