import logging
from typing import Tuple, Dict, Any, List, Optional
from lyrallm.core.model_executor import ModelExecutor
from lyrallm.config.config_manager import config_manager
from .exceptions import RoutingError

logger = logging.getLogger(__name__)

class RouterService:
    """
    Centralized Routing Service
    Encapsulates logic for model selection and routing.
    """
    
    def __init__(self):
        self.executor = ModelExecutor()

    async def route_model(self, messages: List[Any], request_id: str, requested_model: str) -> Tuple[str, Dict[str, Any]]:
        """
        Determine the best model to use based on the request.
        
        Args:
            messages: The chat history/messages.
            request_id: Unique request identifier.
            requested_model: The model requested by the user (e.g., 'auto', 'gpt-4').
            
        Returns:
            Tuple[str, Dict[str, Any]]: (selected_model_name, routing_info)
        """
        if requested_model != 'auto':
            return requested_model, {}

        try:
            routed_model, routing_info = await self.executor._route_model(messages, request_id)
            final_model = routed_model or config_manager.get_default_model()
            logger.info(f"[{request_id}] Auto-routed to: {final_model}")
            return final_model, routing_info or {}
        except Exception as e:
            logger.warning(f"[{request_id}] Auto routing failed: {e}")
            # Fallback to default if routing fails
            default_model = config_manager.get_default_model()
            return default_model, {"error": str(e), "fallback": True}
