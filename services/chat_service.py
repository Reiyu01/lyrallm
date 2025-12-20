import logging
import uuid
import asyncio
from typing import Dict, Any, AsyncGenerator, List, Optional
from datetime import datetime

from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent

from lyrallm.config.config_manager import config_manager
from lyrallm.auth.dependencies import RequestSecurityContext
from lyrallm.core.exceptions import ModelNotFoundError, ModelNotAllowedError, FeatureNotAllowedError, AgentExecutionError
from lyrallm.core.router_service import RouterService
from agents.agent_factory import AgentFactory

logger = logging.getLogger(__name__)

class ChatService:
    """
    Chat Service Layer
    Handles business logic for chat completions, including agent orchestration and routing.
    """

    def __init__(self):
        self.router_service = RouterService()

    async def create_chat_service_for_model(self, model_name: str) -> ChatCompletionClientBase:
        """Creates the SK chat service for a given model."""
        model_config = config_manager.get_model_by_name(model_name)
        if not model_config:
            raise ModelNotFoundError(model_name)

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
            # Fallback or other providers could be added here
            # For now, assuming config is valid if get_model_by_name returns it, 
            # but good to have a check.
            raise ValueError(f"Unsupported provider: {provider}")

    def _convert_to_chat_history(self, messages: List[Any]) -> ChatHistory:
        """Converts Pydantic/Dict messages to SK ChatHistory."""
        history = ChatHistory()
        for msg in messages:
            # Handle both Pydantic objects and dicts
            role = getattr(msg, 'role', None) or msg.get('role')
            content = getattr(msg, 'content', None) or msg.get('content')
            
            if role == "user":
                history.add_user_message(content)
            elif role == "assistant":
                history.add_assistant_message(content)
            elif role == "system":
                history.add_system_message(content)
            else:
                history.add_message(ChatMessageContent(role=role, content=content))
        return history

    def validate_request(self, model: str, features: Any, security_ctx: RequestSecurityContext):
        """Validates permissions for model and features."""
        # 1. Model Permission
        if not security_ctx.allows_model(model):
            raise ModelNotAllowedError(model, security_ctx.role.name)

        # 2. Feature Permission
        if features:
            feature_payload = features.model_dump(exclude_none=True) if hasattr(features, 'model_dump') else features
            requested_features = [k for k, v in feature_payload.items() if isinstance(v, bool) and v]
            disallowed = [f for f in requested_features if not security_ctx.allows_feature(f)]
            
            if disallowed:
                raise FeatureNotAllowedError(disallowed, security_ctx.role.name)

    async def process_agent_stream(
        self, 
        messages: List[Any], 
        model: str, 
        features: Any, 
        security_ctx: RequestSecurityContext,
        request_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Processes a streaming agent request.
        """
        try:
            # 1. Routing
            final_model, routing_info = await self.router_service.route_model(messages, request_id, model)
            
            # Yield routing info immediately
            yield {
                "type": "info",
                "model": final_model,
                "routing_info": routing_info
            }

            # 2. Validation (on the resolved model)
            self.validate_request(final_model, features, security_ctx)

            # 3. Prepare Context
            chat_history = self._convert_to_chat_history(messages)
            if not chat_history.messages:
                raise ValueError("No messages found")

            # 4. Create Service & Agent
            chat_service = await self.create_chat_service_for_model(final_model)
            
            features_dict = {}
            if features:
                features_dict = features.model_dump(exclude_none=True) if hasattr(features, 'model_dump') else features

            thinker_agent = AgentFactory.create_thinker_agent(
                chat_service, 
                features=features_dict, 
                name="ThinkerAgent"
            )

            # 5. Execute Stream
            async for event in thinker_agent.process_stream(chat_history, security_ctx=security_ctx):
                yield event

        except Exception as e:
            logger.error(f"[{request_id}] Agent stream failed: {e}")
            # If it's a known business exception, re-raise it so the API layer can handle it (or let global handler catch it)
            # But since this is a generator, we usually yield an error event for SSE.
            yield {"type": "error", "content": str(e)}
            # We might also want to raise if we want to abort the connection cleanly with an HTTP error 
            # BEFORE the stream starts, but once streaming starts, we must yield errors.

    async def process_agent_request(
        self,
        messages: List[Any],
        model: str,
        features: Any,
        security_ctx: RequestSecurityContext,
        request_id: str
    ) -> str:
        """
        Processes a non-streaming agent request.
        """
        # 1. Routing
        final_model, _ = await self.router_service.route_model(messages, request_id, model)
        
        # 2. Validation
        self.validate_request(final_model, features, security_ctx)

        # 3. Prepare Context
        chat_history = self._convert_to_chat_history(messages)
        
        # 4. Create Service & Agent
        chat_service = await self.create_chat_service_for_model(final_model)
        
        features_dict = {}
        if features:
            features_dict = features.model_dump(exclude_none=True) if hasattr(features, 'model_dump') else features

        thinker_agent = AgentFactory.create_thinker_agent(
            chat_service, 
            features=features_dict, 
            name="ThinkerAgent"
        )

        # 5. Execute (Synchronous wait for result)
        # Note: ThinkerAgent.process is the sync-wait version we added earlier
        return await thinker_agent.process(chat_history, security_ctx=security_ctx)
