"""
Thinker Agent - 主控思考 Agent
負責任務分析、規劃和協調其他專業 Agents
"""

import logging
from typing import List, Dict, Any, Optional
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase

logger = logging.getLogger(__name__)

class ThinkerAgent:
    """
    Thinker Agent - 主控思考者
    
    職責：
    1. 分析用戶問題的複雜度和類型
    2. 判斷需要哪些專業知識來解決問題
    3. 決定是否需要專業 Agent 協助
    4. 整合所有資訊提供完整的最終回答
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase, available_agents: List[str] = None):
        """
        初始化 Thinker Agent
        
        Args:
            chat_service: 聊天完成服務
            available_agents: 可用的專業 Agent 列表
        """
        self.available_agents = available_agents or []
        self.chat_service = chat_service
        
        # 根據可用的 agents 動態生成指令
        self.instructions = self._generate_instructions()
        
        # 創建 ChatCompletionAgent
        self.agent = ChatCompletionAgent(
            name="Thinker",
            description="智能任務協調者，負責分析問題並決定需要哪些專家協助",
            instructions=self.instructions,
            service=chat_service
        )
        
        logger.info(f"🧠 ThinkerAgent 初始化完成，可用專業 Agents: {self.available_agents}")
    
    def _generate_instructions(self) -> str:
        """根據可用的 agents 動態生成指令"""
        
        base_instructions = """
你是 Thinker，一個智能思考協調者。你的職責包括：

1. **任務分析**: 仔細分析用戶問題的複雜度、類型和所需資訊
2. **資源評估**: 判斷是否需要專業 Agent 協助來獲取資訊
3. **協調決策**: 決定何時請求協助、何時提供最終答案
4. **結果整合**: 綜合所有收集的資訊提供完整回答

**工作流程:**
1. 分析用戶問題
2. 評估自己能否直接回答
3. 如需要更多資訊，請求專業 Agent 協助
4. 收到結果後評估是否足夠
5. 提供完整的最終分析

**結束對話的方式:**
當你認為已經收集足夠資訊時，提供一個完整的、綜合性的回答，
並在回答末尾明確表示分析完成，例如：
- "以上就是我的完整分析"
- "綜合以上資訊，我的結論是..."
- "基於收集的所有資料，最終建議如下..."
"""
        
        # 根據可用 agents 添加具體指令
        if self.available_agents:
            agent_instructions = "\n**可用的專業 Agents:**\n"
            
            for agent in self.available_agents:
                if agent == "WebSearchAgent":
                    agent_instructions += """
- **WebSearchAgent**: 當需要搜尋網路資訊、查找最新資料或驗證事實時使用
  請求格式: "我需要 WebSearchAgent 搜尋 [具體搜尋需求]"
"""
            
            agent_instructions += """
**請求協助的格式:**
- 明確說明需要什麼協助
- 提供具體的搜尋關鍵詞或需求
- 一次只請求一個 Agent 的協助

**重要事項:**
- 只有在確實需要額外資訊時才請求協助
- 每次收到協助結果後，評估是否需要更多資訊
- 如果資訊充足，立即提供完整分析並結束對話
"""
        else:
            agent_instructions = """
**注意**: 目前沒有可用的專業 Agents，你需要基於自己的知識來回答問題。
"""
        
        return base_instructions + agent_instructions
    
    def update_available_agents(self, agents: List[str]):
        """更新可用的 agents 列表並重新生成指令"""
        self.available_agents = agents
        self.instructions = self._generate_instructions()
        
        # 更新 agent 的指令
        self.agent.instructions = self.instructions
        
        logger.info(f"🔄 ThinkerAgent 更新可用 Agents: {self.available_agents}")
    
    def get_agent(self) -> ChatCompletionAgent:
        """返回 ChatCompletionAgent 實例"""
        return self.agent
    
    def get_agent_name(self) -> str:
        """返回 Agent 名稱"""
        return "Thinker"