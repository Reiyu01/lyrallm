"""
Agent Orchestrator - 多 Agent 協調器
基於 Semantic Kernel HandoffOrchestration 實現智能 Agent 協作
"""

import logging
from typing import List, Dict, Any, Optional, Union
from semantic_kernel.agents.agent_orchestration import HandoffOrchestration, Handoffs
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.contents import ChatMessageContent, AuthorRole
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatMessageContent

from .thinker_agent import ThinkerAgent
from .web_search_agent import WebSearchAgent

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Agent 協調器 - 管理多 Agent 協作
    
    基於 Semantic Kernel HandoffOrchestration 實現：
    1. Thinker Agent 負責主控思考和協調
    2. 專業 Agents 根據需求動態加入
    3. 智能交接和自然對話終止
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase):
        """
        初始化 Agent 協調器
        
        Args:
            chat_service: 聊天完成服務
        """
        self.chat_service = chat_service
        self.runtime = None
        self.orchestration = None
        
        # 初始化 Agents
        self.thinker_agent = ThinkerAgent(chat_service)
        self.web_search_agent = WebSearchAgent(chat_service)
        
        # 記錄對話歷史用於除錯
        self.conversation_history = []
        
        logger.info("🎭 AgentOrchestrator 初始化完成")
    
    async def setup_orchestration(self, features: Dict[str, Any] = None) -> bool:
        """
        根據前端 features 參數設置協調流程
        
        Args:
            features: 前端傳入的功能參數
            
        Returns:
            bool: 是否成功設置協調流程
        """
        try:
            # 確定可用的專業 Agents
            available_agents = []
            agents_list = [self.thinker_agent.get_agent()]
            
            # 檢查是否啟用 web_search 功能
            if features and features.get('web_search', False):
                if self.web_search_agent.is_available():
                    available_agents.append("WebSearchAgent")
                    agents_list.append(self.web_search_agent.get_agent())
                    logger.info("🔍 WebSearchAgent 已加入協調流程")
                else:
                    logger.warning("⚠️  web_search 功能已啟用但 WebSearchAgent 不可用")
            
            # 更新 Thinker Agent 的可用 agents 列表
            self.thinker_agent.update_available_agents(available_agents)
            
            # 設置交接關係
            handoffs = self._create_handoffs(available_agents)
            
            # 創建協調流程
            self.orchestration = HandoffOrchestration(
                members=agents_list,
                handoffs=handoffs,
                agent_response_callback=self._agent_response_callback
            )
            
            logger.info(f"✅ 協調流程設置完成，參與 Agents: Thinker + {available_agents}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 協調流程設置失敗: {e}")
            return False
    
    def _create_handoffs(self, available_agents: List[str]) -> OrchestrationHandoffs:
        """
        創建交接關係
        
        Args:
            available_agents: 可用的專業 Agent 列表
            
        Returns:
            OrchestrationHandoffs: 交接關係配置
        """
        handoffs = OrchestrationHandoffs()
        
        # Thinker 可以交接給所有可用的專業 Agents
        if available_agents:
            target_agents = {}
            
            for agent in available_agents:
                if agent == "WebSearchAgent":
                    target_agents["WebSearchAgent"] = "當需要搜尋網路資訊、查找最新資料或驗證事實時轉交"
            
            if target_agents:
                handoffs.add_many(
                    source_agent="Thinker",
                    target_agents=target_agents
                )
        
        # 所有專業 Agents 完成任務後回到 Thinker
        for agent in available_agents:
            handoffs.add(
                source_agent=agent,
                target_agent="Thinker",
                description=f"{agent} 任務完成，回到主控思考者進行分析"
            )
        
        logger.info(f"🔄 交接關係已設置，支持 {len(available_agents)} 個專業 Agents")
        return handoffs
    
    async def _setup_runtime_and_orchestration(self, features: Dict[str, Any] = None) -> None:
        """
        設置運行時環境和協調流程
        
        Args:
            features: 前端功能參數
        """
        # 創建交接關係
        handoffs = self._create_handoffs(features)
        
        # 如果沒有專業 Agent，創建一個 self-loop 以滿足 HandoffOrchestration 要求
        if not handoffs:
            handoffs = Handoffs(
                source_agent="Thinker",
                target_agent="Thinker", 
                description="Thinker 處理所有任務"
            )
        
        # 設置協調流程（HandoffOrchestration 不需要 runtime 參數）
        self.orchestration = HandoffOrchestration(handoffs=handoffs)
        
        # 添加 Agents 到協調流程
        await self.orchestration.add_agent(agent=self.thinker_agent)
        
        # 根據功能添加對應的 Agents
        if features and features.get('web_search'):
            await self.orchestration.add_agent(agent=self.web_search_agent)
    
    def _agent_response_callback(self, message: ChatMessageContent) -> None:
        """
        Agent 回應回調函數，用於記錄對話歷史
        
        Args:
            message: Agent 的回應訊息
        """
        agent_name = getattr(message, 'name', 'Unknown')
        content = getattr(message, 'content', str(message))
        
        # 記錄到對話歷史
        self.conversation_history.append({
            "agent": agent_name,
            "content": content,
            "timestamp": str(message.metadata.get('timestamp')) if hasattr(message, 'metadata') and message.metadata else None
        })
        
        # 記錄到 log
        logger.info(f"🗣️  [{agent_name}]: {content[:100]}{'...' if len(content) > 100 else ''}")
    
    async def process_request(self, user_input: str, features: Dict[str, Any] = None) -> str:
        """
        處理用戶請求，使用多 Agent 協作
        
        Args:
            user_input: 用戶輸入
            features: 前端功能參數
            
        Returns:
            str: 最終回應
        """
        try:
            # 清空對話歷史
            self.conversation_history = []
            
            # 設置協調流程
            if not await self.setup_orchestration(features):
                return "抱歉，Agent 協調系統初始化失敗，請稍後重試。"
            
            # 創建新的運行時環境
            self.runtime = InProcessRuntime()
            
            # 重新設置協調流程
            await self._setup_runtime_and_orchestration(features)
            
            # 啟動運行時
            await self.runtime.start()
            
            try:
                logger.info(f"🚀 開始處理用戶請求: {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
                
                # 使用 runtime 執行協調流程
                async for message in self.runtime.send_message(
                    message=ChatMessageContent(
                        role=AuthorRole.USER,
                        content=user_input
                    ),
                    agent_ids=["Thinker"],  # 從 Thinker 開始
                    orchestration=self.orchestration
                ):
                    if message.role == AuthorRole.ASSISTANT:
                        # 記錄 Agent 回應
                        self._agent_response_callback(message)
                        final_result = message.content
                
                logger.info("✅ 多 Agent 協作完成")
                return final_result if 'final_result' in locals() else "對話完成，但未獲得回應"
                
            finally:
                # 停止運行時
                await self.runtime.stop_when_idle()
                self.runtime = None
                
        except Exception as e:
            logger.error(f"❌ 處理請求失敗: {e}")
            import traceback
            logger.error(f"❌ 錯誤堆疊: {traceback.format_exc()}")
            return f"抱歉，處理您的請求時發生錯誤：{str(e)}"
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        獲取對話歷史
        
        Returns:
            List[Dict]: 對話歷史記錄
        """
        return self.conversation_history.copy()
    
    def get_available_features(self) -> List[str]:
        """
        獲取當前可用的功能列表
        
        Returns:
            List[str]: 可用功能列表
        """
        features = []
        
        if self.web_search_agent.is_available():
            features.append("web_search")
        
        return features