import time
import logging
import asyncio
from typing import Optional, List, Dict, Any, Tuple
from config.config_manager import config_manager
from .model_manager import get_model_manager_sync

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.connectors.ai import FunctionChoiceBehavior

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
                       features: Optional[dict] = None) -> Dict[str, Any]:
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
            # Handle auto routing
            if model_name == 'auto':
                model_name, routing_info = await self._route_model(messages, request_id)
                logger.info(f"[{request_id}] Auto-routed to: {model_name}")
                # Validate routed model exists and is enabled
                if not self._is_model_available(model_name):
                    logger.warning(f"[{request_id}] Routed model {model_name} unavailable, using fallback")
                    model_name = self._get_fallback_model()
            else:
                routing_info = None

            # Get model configuration
            model_cfg = config_manager.get_model_by_name(model_name) or {}
            provider = model_cfg.get('provider', '')

            # Handle fake/test models
            if provider == 'fake' or model_name == 'fake':
                return self._generate_fake_response(model_name, messages, start_time)

            # Validate model availability
            if not model_cfg:
                raise ValueError(f"Model '{model_name}' not found in configuration")
            
            if not model_cfg.get('enabled', False):
                raise ValueError(f"Model '{model_name}' is disabled")

            # Generate response using real model
            result = await self._generate_real_response(
                model_name, model_cfg, messages, temperature, max_tokens, 
                features, start_time, request_id, routing_info
            )
            
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

    async def _route_model(self, messages: Optional[List[Any]], request_id: str) -> Tuple[str, Dict]:
        """Intelligent model routing based on message content and model health."""
        try:
            # Extract query for routing
            query = self._extract_routing_query(messages)
            if not query.strip():
                logger.warning(f"[{request_id}] Empty query for routing, using default model")
                return self._get_fallback_model(), {}

            logger.info(f"[{request_id}] Routing query: '{query[:100]}...'")
            
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

        kernel = await self._get_kernel_for_model(model_name)
        if kernel is None:
            raise RuntimeError(f"Could not create kernel for model {model_name}")

        # Prepare chat history
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

        # Get chat completion service
        try:
            chat_completion = kernel.get_service(type=ChatCompletionClientBase)
        except Exception as e:
            logger.error(f"[{request_id}] Failed to get chat completion service for {model_name}: {e}")
            raise

        # Configure execution settings
        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )
        
        # Apply generation parameters
        self._apply_generation_settings(execution_settings, model_cfg, temperature, max_tokens)
        
        # Configure plugins/functions if available
        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):
            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
            logger.info(f"[{request_id}] Enabled function calling for {model_name}")

        # Execute model inference
        try:
            logger.info(f"[{request_id}] Calling {model_name} (provider: {model_cfg.get('provider')})")
            
            if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):
                response = await chat_completion.get_chat_message_contents(
                    chat_history=chat_history, settings=execution_settings, kernel=kernel
                )
            else:
                response = await chat_completion.get_chat_message_contents(
                    chat_history=chat_history, settings=execution_settings
                )

            if not response:
                raise RuntimeError('Empty response from model provider')

            # Extract response content
            response_text = str(response[0].content)
            
            # Calculate token usage (best effort)
            usage = self._calculate_usage(messages, response_text)
            
            # Build standardized response
            result = {
                'id': f'chatcmpl-{int(time.time())}-{request_id}',
                'created': int(time.time()),
                'model': model_name,
                'choices': [{
                    'index': 0, 
                    'message': {'role': 'assistant', 'content': response_text}, 
                    'finish_reason': 'stop'
                }],
                'usage': usage,
                'text': response_text,
                'meta': {
                    'latency_ms': int((time.time() - start_time) * 1000),
                    'provider': model_cfg.get('provider'),
                    'routing_info': routing_info,
                    'plugins_used': plugins_available
                }
            }
            
            logger.info(f"[{request_id}] Response generated successfully ({usage['total_tokens']} tokens)")
            return result

        except Exception as e:
            logger.error(f"[{request_id}] Model execution failed for {model_name}: {e}")
            raise

    def _apply_generation_settings(self, execution_settings, model_cfg: Dict, temperature: float, max_tokens: Optional[int]):
        """Apply generation parameters to execution settings."""
        # Some reasoning / structured models (o1/o3 family) may reject temperature
        model_name = model_cfg.get('deployment_name') or model_cfg.get('name') or ''
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
        
        # Return cached kernel copy if available
        if cache_key in self._kernel_cache:
            base_kernel = self._kernel_cache[cache_key]
            return self._copy_kernel(base_kernel)

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
                # TODO: Add Ollama connector when available
                logger.warning(f"Ollama provider support not yet implemented for {model_name}")
                return None
                
            else:
                logger.error(f"Unsupported provider '{provider}' for model {model_name}")
                return None
                
            # Cache the configured kernel
            self._kernel_cache[cache_key] = kernel
            logger.info(f"Created and cached kernel for model: {model_name} (provider: {provider})")
            
            # Return fresh copy
            return self._copy_kernel(kernel)
            
        except Exception as e:
            logger.error(f"Failed to create kernel for {model_name}: {e}")
            return None

    def _copy_kernel(self, base_kernel: sk.Kernel) -> sk.Kernel:
        """Create a fresh copy of a kernel with the same services."""
        new_kernel = sk.Kernel()
        for service in base_kernel.services.values():
            new_kernel.add_service(service)
        return new_kernel

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
