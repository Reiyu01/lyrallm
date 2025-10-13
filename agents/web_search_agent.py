"""
WebSearch Agent - 網路搜尋專業 Agent
負責執行網路搜尋任務並提供結構化結果
"""

import logging
from typing import List, Dict, Any, Optional
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin

logger = logging.getLogger(__name__)

class WebSearchAgent:
    """
    流程編號 #040: WebSearch Agent定義 - 專業網路搜尋執行者
    WebSearch Agent - 網路搜尋專家
    
    職責：
    1. 接收搜尋請求並理解搜尋需求
    2. 執行精準的網路搜尋
    3. 整理和篩選搜尋結果
    4. 提供結構化的搜尋報告
    
    注意：在MCP架構下，WebSearchAgent主要提供指令模板，
    實際搜尋功能由MCP Server(#027-#029)執行
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase):
        """
        初始化 WebSearch Agent
        
        Args:
            chat_service: 聊天完成服務
        """
        self.chat_service = chat_service
        
        # 嘗試初始化 Web Search Plugin
        try:
            self.web_search_plugin = OllamaWebSearchPlugin()
            plugin_available = True
            logger.info("✅ WebSearchAgent: OllamaWebSearchPlugin 初始化成功")
        except Exception as e:
            self.web_search_plugin = None
            plugin_available = False
            logger.warning(f"⚠️  WebSearchAgent: OllamaWebSearchPlugin 初始化失敗: {e}")
        
        # 根據 plugin 可用性生成指令
        self.instructions = self._generate_instructions(plugin_available)
        
        # 創建 ChatCompletionAgent
        plugins = [self.web_search_plugin] if plugin_available else []
        
        self.agent = ChatCompletionAgent(
            name="WebSearchAgent",
            description="專業網路搜尋助手，負責執行網路搜尋並提供結構化結果",
            instructions=self.instructions,
            service=chat_service,
            plugins=plugins
        )
        
        logger.info(f"🔍 WebSearchAgent 初始化完成，Plugin 狀態: {'可用' if plugin_available else '不可用'}")
    
    def _generate_instructions(self, plugin_available: bool) -> str:
        """根據 plugin 可用性生成指令"""
        
        if plugin_available:
            return """
你是 WebSearchAgent，專業的網路搜尋助手。當 Thinker 需要搜尋資訊時：

**可用工具:**
1. **search(query, max_results)** - 執行網路搜尋
2. **web_fetch(url)** - 抓取特定網頁內容  
3. **get_search_status()** - 檢查搜尋服務狀態
4. **get_current_time(format)** - 獲取當前時間
   - format可選: "iso"、"readable"、"timestamp"

**你的職責:**
1. 理解 Thinker 的搜尋需求
2. **若需要最新資訊，先使用 get_current_time 獲取當前時間**
3. 根據時間資訊優化搜尋關鍵詞
4. 使用 search 功能執行精準搜尋
5. 分析和整理搜尋結果
6. 提供結構化的搜尋報告
7. 完成後明確告知 Thinker 任務已完成

**搜尋策略:**
- **對於今日新聞、最新事件等請求，先獲取當前時間**
- 在搜尋關鍵詞中包含時間相關資訊（如"2025年10月"、"今日"）
- 根據需求選擇最合適的搜尋關鍵詞
- 優先搜尋最新、最相關的資訊
- 如果初次搜尋結果不理想，可以調整關鍵詞重新搜尋

**報告格式:**
搜尋完成後，請按以下格式提供報告：

**搜尋主題**: [搜尋的主題]
**當前時間**: [如有獲取，顯示當前時間]
**搜尋關鍵詞**: [使用的關鍵詞]
**主要發現**: 
- [重點1]
- [重點2]
- [重點3]

**詳細資料**: 
[詳細的搜尋結果內容和分析]

**資料來源**: [來源網站和連結]

**任務狀態**: 搜尋任務完成，已回到 Thinker 進行分析。

**重要提醒:**
- 專注於提供準確、相關的資訊
- 對於時效性要求高的搜尋，一定要先獲取時間
- 如果搜尋結果有限，明確說明
- 完成搜尋後不要主動提供建議，讓 Thinker 進行分析
"""
        else:
            return """
你是 WebSearchAgent，但目前網路搜尋功能不可用。

當 Thinker 請求搜尋時，請回覆：
"很抱歉，目前網路搜尋功能暫時不可用。請 Thinker 基於現有知識來回答問題，或稍後重試。"

並立即回到 Thinker 繼續處理。
"""
    
    def is_available(self) -> bool:
        """檢查 WebSearch Agent 是否可用"""
        return self.web_search_plugin is not None
    
    def get_agent(self) -> ChatCompletionAgent:
        """返回 ChatCompletionAgent 實例"""
        return self.agent
    
    def get_agent_name(self) -> str:
        """返回 Agent 名稱"""
        return "WebSearchAgent"