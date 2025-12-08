from typing import Dict, Any, Optional
import logging
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from .thinker_agent import ThinkerAgent
from .search_agent import SearchAgent
from .rag_agent import RAGAgent

logger = logging.getLogger(__name__)

class AgentFactory:
    """
    Agent Factory - 負責創建和組裝 ThinkerAgent 及其依賴的工具 Agents
    實現高內聚、低耦合的工廠模式
    """
    
    @staticmethod
    def create_thinker_agent(
        chat_service: ChatCompletionClientBase,
        features: Dict[str, bool] = None,
        name: str = "ThinkerAgent"
    ) -> ThinkerAgent:
        """
        創建並配置 ThinkerAgent 實例 (Per-Request)
        
        Args:
            chat_service: 基礎聊天服務 (Semantic Kernel Connector)
            features: 啟用的功能列表 (web_search, rag_search 等)
            name: Agent 名稱
            
        Returns:
            配置完成的 ThinkerAgent 實例
        """
        features = features or {}
        
        # 1. 創建 ThinkerAgent (核心大腦)
        thinker = ThinkerAgent(chat_service, name=name)
        
        # 2. 根據 features 注入依賴 (工具手腳)
        # 這裡實現了依賴注入 (Dependency Injection)，ThinkerAgent 不需要知道如何創建這些工具
        
        if features.get("web_search"):
            try:
                search_agent = SearchAgent(chat_service)
                thinker.set_search_agent(search_agent)
                logger.debug(f"🔌 [Factory] 已為 {name} 啟用 WebSearch")
            except Exception as e:
                logger.error(f"❌ [Factory] 啟用 WebSearch 失敗: {e}")
                
        if features.get("rag_search"):
            try:
                rag_agent = RAGAgent(chat_service)
                thinker.set_rag_agent(rag_agent)
                logger.debug(f"🔌 [Factory] 已為 {name} 啟用 RAG")
            except Exception as e:
                logger.error(f"❌ [Factory] 啟用 RAG 失敗: {e}")
                
        # 3. 未來可擴展其他 Agent (Image, Code, etc.)
        if features.get("image_generation"):
            # TODO: Implement ImageGenerationAgent
            pass
            
        return thinker
