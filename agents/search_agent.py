"""
Search Agent - 純搜尋工具版本
專注於執行搜尋並返回原始資料，不做分析和整合
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions import kernel_function
from .smart_parameter_manager import smart_settings

logger = logging.getLogger(__name__)

class SearchAgentPlugin:
    """Search Agent 的核心功能插件 - 純搜尋版"""
    
    @kernel_function(
        description="優化搜尋關鍵字",
        name="optimize_search_query"
    )
    def optimize_search_query(self, search_task: str, context: str) -> str:
        """優化搜尋關鍵字以獲得更好的結果"""
        return f"""
你是一個搜尋專家，需要優化搜尋關鍵字以獲得最相關的結果。

搜尋任務: {search_task}
背景資訊: {context}

請提供：
1. **最佳關鍵字**: 最有效的搜尋關鍵字
2. **備選關鍵字**: 2-3個替代搜尋詞
3. **搜尋策略**: 如何提高搜尋效果

請按此格式回應：
PRIMARY_KEYWORDS: [主要搜尋關鍵字]
ALTERNATIVE_KEYWORDS: [備選關鍵字1 | 備選關鍵字2 | 備選關鍵字3]
SEARCH_STRATEGY: [搜尋策略說明]
"""

class SearchAgent:
    """
    純粹的搜尋工具，負責：
    1. 接收搜尋任務
    2. 優化搜尋關鍵字
    3. 執行網路搜尋
    4. 返回原始搜尋結果
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase, name: str = "SearchAgent"):
        self.name = name
        self.chat_service = chat_service
        
        # 創建 ChatCompletionAgent
        self.agent = ChatCompletionAgent(
            name=self.name,
            description="純粹的搜尋工具，專注於執行搜尋並返回原始資料",
            instructions="""
你是一個專業的搜尋工具。你的職責：

1. **關鍵字優化**: 將搜尋任務轉換為最有效的搜尋關鍵字
2. **搜尋執行**: 執行網路搜尋並獲取結果
3. **資料提取**: 從搜尋結果中提取有用的原始資料
4. **結果返回**: 將原始搜尋資料完整返回，不做分析

**工作原則**：
- 專注於獲取準確的搜尋結果
- 不進行資料分析或整合
- 提供完整的原始資料
- 包含資料來源資訊
""",
            service=chat_service,
            plugins=[SearchAgentPlugin()]
        )
        
        # MCP 客戶端（延遲初始化）
        self.mcp_client = None
        self._mcp_started = False
        
        logger.info(f"🔍 {self.name} 純搜尋工具版本初始化完成")
    
    async def execute_search(self, search_task: str, context: str = "") -> Dict[str, Any]:
        """
        執行搜尋任務的主要入口點
        
        Args:
            search_task: 搜尋任務描述
            context: 背景資訊（可選）
            
        Returns:
            {
                'success': bool,
                'query_used': str,
                'raw_results': str,
                'sources': List[str],
                'timestamp': str,
                'error': str (if failed)
            }
        """
        try:
            logger.info(f"🔍 {self.name} 開始執行搜尋任務")
            
            # 確保 MCP 客戶端可用
            await self._ensure_mcp_client()
            
            # 獲取當前時間
            current_time = await self._get_current_time()
            
            # 優化搜尋關鍵字
            optimized_query = await self._optimize_search_keywords(search_task, context)
            logger.info(f"🎯 {self.name} 使用關鍵字: {optimized_query}")
            
            # 執行搜尋
            search_results = await self._perform_search(optimized_query)
            
            # 提取和結構化結果
            structured_results = self._structure_search_results(search_results)
            
            result = {
                'success': True,
                'query_used': optimized_query,
                'raw_results': structured_results['content'],
                'sources': structured_results['sources'],
                'timestamp': current_time,
                'search_task': search_task,
                'context': context
            }
            
            logger.info(f"✅ {self.name} 搜尋完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ {self.name} 搜尋失敗: {e}")
            return {
                'success': False,
                'error': str(e),
                'query_used': search_task,
                'raw_results': '',
                'sources': [],
                'timestamp': current_time if 'current_time' in locals() else 'Unknown'
            }
    
    async def _ensure_mcp_client(self):
        """確保 MCP 客戶端已初始化並啟動"""
        if self.mcp_client is None:
            # 嘗試不同的導入路徑
            try:
                from ..mcp.web_search_mcp_client import WebSearchMCPClient
                self.mcp_client = WebSearchMCPClient()
            except ImportError:
                try:
                    # 假設從主包級別運行
                    from mcp.web_search_mcp_client import WebSearchMCPClient
                    self.mcp_client = WebSearchMCPClient()
                except ImportError:
                    # 絕對路徑導入
                    import sys
                    import os
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    parent_dir = os.path.dirname(current_dir)
                    mcp_path = os.path.join(parent_dir, 'mcp')
                    if mcp_path not in sys.path:
                        sys.path.insert(0, mcp_path)
                    from web_search_mcp_client import WebSearchMCPClient
                    self.mcp_client = WebSearchMCPClient()
        
        if not self._mcp_started:
            await self.mcp_client.start()
            self._mcp_started = True
            logger.info(f"🚀 {self.name} MCP 客戶端已啟動")
    
    async def _get_current_time(self) -> str:
        """獲取當前時間"""
        try:
            return await self.mcp_client.get_current_time("readable")
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 獲取時間失敗: {e}")
            from datetime import datetime
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    async def _optimize_search_keywords(self, search_task: str, context: str) -> str:
        """優化搜尋關鍵字"""
        try:
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個搜尋專家，需要優化搜尋關鍵字以獲得最相關的結果。

搜尋任務: {search_task}
背景資訊: {context}

請提供：
1. **最佳關鍵字**: 最有效的搜尋關鍵字
2. **備選關鍵字**: 2-3個替代搜尋詞
3. **搜尋策略**: 如何提高搜尋效果

請按此格式回應：
PRIMARY_KEYWORDS: [主要搜尋關鍵字]
ALTERNATIVE_KEYWORDS: [備選關鍵字1 | 備選關鍵字2 | 備選關鍵字3]
SEARCH_STRATEGY: [搜尋策略說明]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=1000,
                    temperature=0.3
                )
            )
            
            if not response or len(response) == 0:
                logger.warning(f"⚠️ {self.name} 關鍵字優化失敗，使用原始任務")
                return search_task
            
            optimization_result = response[0].content
            return self._extract_primary_keywords(optimization_result, search_task)
            
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 關鍵字優化失敗: {e}")
            return search_task
    
    def _extract_primary_keywords(self, optimization_result: str, fallback: str) -> str:
        """從優化結果中提取主要關鍵字"""
        import re
        
        try:
            # 提取 PRIMARY_KEYWORDS
            keywords_match = re.search(r'PRIMARY_KEYWORDS:\s*([^\n]+)', optimization_result, re.IGNORECASE)
            if keywords_match:
                keywords = keywords_match.group(1).strip()
                # 移除方括號和多餘空格
                keywords = re.sub(r'[\[\]]', '', keywords).strip()
                return keywords if keywords else fallback
            else:
                return fallback
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 關鍵字提取失敗: {e}")
            return fallback
    
    async def _perform_search(self, query: str) -> str:
        """執行實際的網路搜尋"""
        try:
            search_results = await self.mcp_client.search(query=query, max_results=5)
            logger.info(f"📊 {self.name} 獲得搜尋結果")
            return search_results
        except Exception as e:
            logger.error(f"❌ {self.name} 網路搜尋失敗: {e}")
            raise
    
    def _structure_search_results(self, raw_results: str) -> Dict[str, Any]:
        """結構化搜尋結果"""
        try:
            # 簡單的結果結構化
            # 這裡可以根據 MCP 返回的格式進行更精細的解析
            structured = {
                'content': raw_results,
                'sources': self._extract_sources(raw_results)
            }
            return structured
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 結果結構化失敗: {e}")
            return {
                'content': raw_results,
                'sources': []
            }
    
    def _extract_sources(self, results: str) -> List[str]:
        """從搜尋結果中提取來源 URL"""
        import re
        
        try:
            # 提取 URL 模式
            url_pattern = r'https?://[^\s<>"\']+'
            urls = re.findall(url_pattern, results)
            
            # 去重並限制數量
            unique_urls = list(dict.fromkeys(urls))[:10]
            return unique_urls
        except Exception as e:
            logger.warning(f"⚠️ {self.name} URL 提取失敗: {e}")
            return []
    
    async def test_search_capability(self) -> bool:
        """測試搜尋能力是否可用"""
        try:
            await self._ensure_mcp_client()
            # 執行簡單測試搜尋
            test_result = await self.mcp_client.search(query="test", max_results=1)
            return bool(test_result)
        except Exception as e:
            logger.error(f"❌ {self.name} 搜尋能力測試失敗: {e}")
            return False
    
    def get_agent(self) -> ChatCompletionAgent:
        """獲取底層的 ChatCompletionAgent"""
        return self.agent
    
    def get_name(self) -> str:
        """獲取代理名稱"""
        return self.name
    
    def is_available(self) -> bool:
        """檢查搜尋代理是否可用"""
        return self.mcp_client is not None and self._mcp_started
    
    async def cleanup(self):
        """清理資源"""
        if self._mcp_started and self.mcp_client:
            try:
                await self.mcp_client.stop()
                self._mcp_started = False
                logger.info(f"🛑 {self.name} MCP 客戶端已停止")
            except Exception as e:
                logger.error(f"❌ {self.name} MCP 客戶端停止失敗: {e}")
    
    async def __aenter__(self):
        """異步上下文管理器進入"""
        await self._ensure_mcp_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """異步上下文管理器退出"""
        await self.cleanup()