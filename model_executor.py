import time
import logging
import asyncio
from typing import Optional, List, Dict, Any
from config.config_manager import config_manager

import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.connectors.ai import FunctionChoiceBehavior

logger = logging.getLogger(__name__)


class ModelExecutor:
    """Minimal Model Executor abstraction.

    - Supports 'fake' provider (deterministic fake reply)
    - For real providers, it builds a Semantic Kernel kernel per-model and calls
      the configured chat completion service (reuses existing SK connectors).
    This keeps provider handling centralized and returns a normalized dict.
    """

    def __init__(self):
        # small cache for base kernels keyed by model name
        self._kernel_cache: Dict[str, sk.Kernel] = {}

    async def generate(self, model_name: str, messages: Optional[List[Any]] = None,
                       temperature: float = 0.7, max_tokens: Optional[int] = None,
                       features: Optional[dict] = None) -> Dict[str, Any]:
        start = time.time()
        # support fake model by name or provider
        model_cfg = config_manager.get_model_by_name(model_name) or {}
        provider = model_cfg.get('provider', '')

        # If provider explicitly 'fake' or model_name == 'fake', return deterministic fake
        if provider == 'fake' or model_name == 'fake':
            text = f'[FAKE {model_name}] 回應：{(messages[-1].content if messages and len(messages)>0 else "(no input)")}'
            usage = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
            return {
                'id': f'chatcmpl-{int(time.time())}',
                'created': int(time.time()),
                'model': model_name,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                'usage': usage,
                'text': text,
                'meta': {'latency_ms': int((time.time()-start)*1000)}
            }

        # Build or reuse a kernel for this model
        kernel = await self._get_kernel_for_model(model_name)
        if kernel is None:
            raise RuntimeError(f"Could not create kernel for model {model_name}")

        # prepare chat history
        chat_history = ChatHistory()
        if messages:
            for m in messages:
                # messages may be pydantic objects or dict-like
                role = getattr(m, 'role', None) or m.get('role') if isinstance(m, dict) else 'user'
                content = getattr(m, 'content', None) or m.get('content') if isinstance(m, dict) else str(m)
                if role == 'system':
                    chat_history.add_system_message(content)
                else:
                    chat_history.add_message(ChatMessageContent(role=role, content=content))
        else:
            # if no messages provided, nothing to ask
            chat_history.add_message(ChatMessageContent(role='user', content=''))

        # get the chat completion service
        try:
            chat_completion = kernel.get_service(type=ChatCompletionClientBase)
        except Exception as e:
            logger.error(f"Failed to get chat completion service for {model_name}: {e}")
            raise

        execution_settings = kernel.get_prompt_execution_settings_from_service_id(
            service_id=chat_completion.service_id
        )

        # set temperature when supported
        try:
            execution_settings.temperature = temperature
        except Exception:
            pass

        # set token limit when supported
        max_tokens_value = max_tokens or model_cfg.get('max_completion_tokens') or model_cfg.get('max_tokens')
        if max_tokens_value:
            try:
                execution_settings.max_completion_tokens = max_tokens_value
            except Exception:
                pass

        # enable function choice if available
        plugins_available = len(list(kernel.plugins)) > 0
        if plugins_available and hasattr(execution_settings, 'function_choice_behavior'):
            execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

        # call the provider
        try:
            if plugins_available and hasattr(execution_settings, 'function_choice_behavior') and execution_settings.function_choice_behavior:
                response = await chat_completion.get_chat_message_contents(chat_history=chat_history, settings=execution_settings, kernel=kernel)
            else:
                response = await chat_completion.get_chat_message_contents(chat_history=chat_history, settings=execution_settings)

            if not response:
                raise RuntimeError('No response from provider')

            text = str(response[0].content)
            # best-effort usage: SK may not provide usage; estimate token counts by simple split fallback
            prompt_tokens = sum(len((getattr(m, 'content', None) or m.get('content') if isinstance(m, dict) else '').split()) for m in (messages or []))
            completion_tokens = len(text.split())
            usage = {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens}

            return {
                'id': f'chatcmpl-{int(time.time())}',
                'created': int(time.time()),
                'model': model_name,
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                'usage': usage,
                'text': text,
                'meta': {'latency_ms': int((time.time()-start)*1000)}
            }

        except Exception as e:
            logger.error(f"ModelExecutor.generate failed for {model_name}: {e}")
            raise

    async def _get_kernel_for_model(self, model_name: str) -> Optional[sk.Kernel]:
        cache_key = f"base_{model_name}"
        if cache_key in self._kernel_cache:
            # return a fresh kernel instance copying services
            base = self._kernel_cache[cache_key]
            new_kernel = sk.Kernel()
            for s in base.services.values():
                new_kernel.add_service(s)
            return new_kernel

        model_config = config_manager.get_model_by_name(model_name)
        if not model_config:
            return None

        provider = model_config.get('provider')
        kernel = sk.Kernel()

        if provider == 'azure_openai':
            kernel.add_service(
                AzureChatCompletion(
                    service_id=f"azure_openai_{model_name}",
                    deployment_name=model_config.get('deployment_name'),
                    endpoint=model_config.get('endpoint'),
                    api_key=model_config.get('api_key'),
                    api_version=model_config.get('api_version')
                )
            )
        elif provider == 'openai':
            kernel.add_service(
                OpenAIChatCompletion(
                    service_id=f"openai_{model_name}",
                    ai_model_id=model_name,
                    api_key=model_config.get('api_key'),
                    base_url=model_config.get('endpoint')
                )
            )
        else:
            # unsupported provider for now
            logger.warning(f"Provider {provider} for model {model_name} is not explicitly supported by ModelExecutor")
            # still cache an empty kernel to avoid repeated lookups

        # cache base kernel
        self._kernel_cache[cache_key] = kernel

        # return a fresh copy
        new_kernel = sk.Kernel()
        for s in kernel.services.values():
            new_kernel.add_service(s)
        return new_kernel


# module-level executor
_default_executor = ModelExecutor()


def get_default_executor() -> ModelExecutor:
    return _default_executor
