"""
Thinker Agent - 主控制器版本
負責任務理解、拆解、多輪查詢決策和最終整合回答
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions import kernel_function
from .smart_parameter_manager import smart_settings

if TYPE_CHECKING:
    from .search_agent import SearchAgent

logger = logging.getLogger(__name__)

class ThinkerAgentPlugin:
    """Thinker Agent 的核心功能插件 - 主控制器版本"""
    
    @kernel_function(
        description="分析用戶需求並制定查詢策略",
        name="analyze_and_plan"
    )
    def analyze_and_plan(self, user_query: str, available_tools: str) -> str:
        """分析用戶需求並制定查詢策略"""
        return f"""
你是一個智能任務分析師，需要深度理解用戶需求並制定查詢策略。

用戶問題: {user_query}
可用工具: {available_tools}

請進行以下分析：
1. **需求理解**: 用戶真正想要了解什麼？
2. **資訊需求**: 需要哪些具體資訊來完整回答？
3. **查詢策略**: 如何拆解查詢任務？
4. **優先順序**: 哪些資訊最重要？

請按此格式回應：
UNDERSTANDING: [對用戶需求的深度理解]
INFO_NEEDED: [需要的具體資訊列表]
SEARCH_TASKS: [具體的查詢任務，用 | 分隔]
PRIORITY: [HIGH|MEDIUM|LOW]
APPROACH: [處理策略：DIRECT_ANSWER 或 NEED_SEARCH]
"""

    @kernel_function(
        description="基於搜尋結果決定下一步行動",
        name="evaluate_and_decide"
    )
    def evaluate_and_decide(self, user_query: str, search_results: str, current_info: str) -> str:
        """基於搜尋結果決定下一步行動"""
        return f"""
基於當前搜尋結果，評估是否需要更多資訊。

原始問題: {user_query}
搜尋結果: {search_results}
已有資訊: {current_info}

請評估：
1. **資訊完整性**: 當前資訊是否足夠回答用戶問題？
2. **資訊品質**: 資訊是否準確、時效性如何？
3. **缺失資訊**: 還需要哪些具體資訊？
4. **下一步**: 需要進一步搜尋還是可以回答？

請按此格式回應：
COMPLETENESS: [完整性評分 1-10]
QUALITY: [品質評分 1-10]
MISSING_INFO: [缺失的資訊]
NEXT_ACTION: [SEARCH_MORE|PROVIDE_ANSWER]
NEXT_QUERY: [如果需要更多搜尋，下一個查詢]
"""

    @kernel_function(
        description="整合所有資訊並生成最終回答",
        name="synthesize_final_answer"
    )
    def synthesize_final_answer(self, user_query: str, all_search_data: str) -> str:
        """整合所有資訊並生成最終回答"""
        return f"""
基於所有搜集的資訊，為用戶提供完整、準確的回答。

用戶問題: {user_query}
所有搜尋資料: {all_search_data}

請提供：
1. **直接回答**: 針對用戶問題的明確答案
2. **詳細說明**: 支持性資訊和背景說明
3. **重要發現**: 關鍵資訊和見解
4. **資料來源**: 資訊的可靠性說明
5. **建議**: 相關的實用建議（如適用）

請確保回答：
- 完整且準確
- 結構清晰
- 基於最新資訊
- 直接回應用戶需求
"""

class ThinkerAgent:
    """
    智能主控制器，負責：
    1. 深度理解用戶需求
    2. 任務拆解和查詢策略制定
    3. 多輪查詢決策
    4. 資訊整合和最終回答生成
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase, name: str = "ThinkerAgent"):
        self.name = name
        self.chat_service = chat_service
        self.search_agent: Optional['SearchAgent'] = None
        
        # 創建 ChatCompletionAgent
        self.agent = ChatCompletionAgent(
            name=self.name,
            description="智能主控制器，負責任務分析、查詢策略制定和最終整合",
            instructions="""
你是一個智能主控制器 (Master Thinker Agent)。你的核心職責：

1. **深度理解**: 理解用戶的真實需求和意圖
2. **任務拆解**: 將複雜問題分解為具體的查詢任務
3. **策略制定**: 決定最佳的資訊收集策略
4. **多輪決策**: 基於已有資訊決定是否需要更多查詢
5. **最終整合**: 將所有資訊整合為完整的回答

**工作原則**：
- 優先考慮用戶的真實需求
- 制定高效的查詢策略
- 持續評估資訊的完整性和品質
- 提供準確、完整、有用的最終回答
- 明確引用資料來源
""",
            service=chat_service,
            plugins=[ThinkerAgentPlugin()]
        )
        
        # 工作狀態
        self.current_task = None
        self.search_history = []
        self.collected_info = {}
        
        logger.info(f"🧠 {self.name} 主控制器版本初始化完成")
    
    def set_search_agent(self, search_agent: 'SearchAgent'):
        """設置搜尋代理"""
        self.search_agent = search_agent
        logger.info(f"🔗 {self.name} 已連接到 SearchAgent")
    
    async def process_user_query(self, user_query: str, search_agent=None) -> str:
        """
        處理用戶查詢的主要入口點
        
        Args:
            user_query: 用戶的問題
            search_agent: 搜尋代理（可選）
            
        Returns:
            完整的回答
        """
        try:
            logger.info(f"🎯 {self.name} 開始處理用戶查詢")
            
            # 重置工作狀態
            self._reset_task_state()
            self.current_task = user_query
            
            # 設置搜尋代理
            self.search_agent = search_agent
            
            # 確定可用工具
            available_tools = []
            if search_agent:
                available_tools.append("web_search")
            
            # 第一步：分析需求並制定策略
            strategy = await self._analyze_and_plan(user_query, available_tools)
            logger.info(f"📋 {self.name} 策略制定完成")
            
            # 根據策略決定處理方式
            if strategy.get('approach') == 'DIRECT_ANSWER':
                # 直接回答
                logger.info("💭 直接基於現有知識回答")
                return await self._provide_direct_answer(user_query)
            
            elif strategy.get('approach') == 'NEED_SEARCH' and self.search_agent:
                # 需要搜尋
                logger.info("🔍 啟動多輪搜尋流程")
                return await self._multi_round_search_process(user_query, strategy)
            
            else:
                # 無搜尋工具可用，直接回答
                logger.info("📝 無搜尋工具，提供基礎回答")
                return await self._provide_direct_answer(user_query)
                
        except Exception as e:
            logger.error(f"❌ {self.name} 處理查詢失敗: {e}")
            return await self._handle_error(user_query, str(e))
    
    async def _analyze_and_plan(self, user_query: str, available_tools: List[str]) -> Dict[str, Any]:
        """分析用戶需求並制定策略"""
        try:
            tools_str = ", ".join(available_tools) if available_tools else "無特殊工具"
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個智能任務分析師，需要深度理解用戶需求並制定查詢策略。

用戶問題: {user_query}
可用工具: {tools_str}

請進行以下分析：
1. **需求理解**: 用戶真正想要了解什麼？
2. **資訊需求**: 需要哪些具體資訊來完整回答？
3. **查詢策略**: 如何拆解查詢任務？
4. **優先順序**: 哪些資訊最重要？

請按此格式回應：
UNDERSTANDING: [對用戶需求的深度理解]
INFO_NEEDED: [需要的具體資訊列表]
SEARCH_TASKS: [具體的查詢任務，用 | 分隔]
PRIORITY: [HIGH|MEDIUM|LOW]
APPROACH: [處理策略：DIRECT_ANSWER 或 NEED_SEARCH]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=2000,
                    temperature=0.3
                )
            )
            
            if not response or len(response) == 0:
                raise ValueError("未能獲得策略分析")
            
            strategy_text = response[0].content
            return self._parse_strategy(strategy_text)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 策略分析失敗: {e}")
            return {'approach': 'DIRECT_ANSWER', 'tasks': [], 'priority': 'LOW'}
    
    async def _multi_round_search_process(self, user_query: str, strategy: Dict[str, Any]) -> str:
        """多輪搜尋流程"""
        try:
            max_rounds = 5  # 最多搜尋輪數
            search_tasks = strategy.get('tasks', [user_query])
            
            for round_num in range(max_rounds):
                logger.info(f"� {self.name} 第 {round_num + 1} 輪搜尋")
                
                # 執行當前輪次的搜尋
                current_task = search_tasks[0] if search_tasks else user_query
                search_result = await self._execute_search(current_task)
                
                # 記錄搜尋結果
                self.search_history.append({
                    'round': round_num + 1,
                    'query': current_task,
                    'result': search_result
                })
                
                # 評估是否需要更多搜尋
                need_more = await self._evaluate_completeness(user_query, search_result)
                
                if not need_more['need_more']:
                    logger.info(f"✅ {self.name} 資訊收集完成")
                    break
                    
                # 準備下一輪搜尋
                if need_more.get('next_query'):
                    search_tasks = [need_more['next_query']]
                else:
                    break
            
            # 整合所有資訊並生成最終回答
            return await self._generate_final_answer(user_query)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 多輪搜尋失敗: {e}")
            return await self._handle_error(user_query, str(e))
    
    async def _execute_search(self, query: str) -> Dict[str, Any]:
        """執行搜尋任務"""
        if not self.search_agent:
            raise ValueError("Search Agent 不可用")
        
        logger.info(f"🔍 執行搜尋: {query}")
        search_result = await self.search_agent.execute_search(query)
        
        # 記錄到收集的資訊中
        timestamp = len(self.search_history) + 1
        self.collected_info[f"search_{timestamp}"] = search_result
        
        return search_result
    
    async def _evaluate_completeness(self, user_query: str, latest_result: Dict[str, Any]) -> Dict[str, Any]:
        """評估資訊完整性"""
        try:
            # 整理當前已有的所有資訊
            all_info = "\n\n".join([
                f"搜尋 {i+1}: {result['result']}" 
                for i, result in enumerate(self.search_history)
            ])
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
基於當前搜尋結果，評估是否需要更多資訊。

原始問題: {user_query}
最新搜尋結果: {latest_result}
已有全部資訊: {all_info}

請評估：
1. **資訊完整性**: 當前資訊是否足夠回答用戶問題？
2. **資訊品質**: 資訊是否準確、時效性如何？
3. **缺失資訊**: 還需要哪些具體資訊？
4. **下一步**: 需要進一步搜尋還是可以回答？

請按此格式回應：
COMPLETENESS: [完整性評分 1-10]
QUALITY: [品質評分 1-10]
MISSING_INFO: [缺失的資訊]
NEXT_ACTION: [SEARCH_MORE|PROVIDE_ANSWER]
NEXT_QUERY: [如果需要更多搜尋，下一個查詢]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=1500,
                    temperature=0.5
                )
            )
            
            if not response or len(response) == 0:
                return {'need_more': False}
            
            evaluation_text = response[0].content
            return self._parse_evaluation(evaluation_text)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 完整性評估失敗: {e}")
            return {'need_more': False}
    
    async def _generate_final_answer(self, user_query: str) -> str:
        """生成最終整合回答"""
        try:
            # 整理所有搜尋資料
            all_data = []
            for i, search_record in enumerate(self.search_history):
                all_data.append(f"""
搜尋 {i+1} - 查詢: {search_record['query']}
結果: {search_record['result']}
""")
            
            all_search_data = "\n".join(all_data)
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個專業的資訊助理，需要根據搜集到的資料，直接回答用戶的問題。

用戶原始問題: {user_query}
搜集到的相關資料: {all_search_data}

請直接針對用戶的問題提供有用的回答：

**重要指導原則：**
1. 針對用戶的需求來回應，不要說明你是如何分析的
2. 以自然、友好的語調回應，就像一個知識豐富的朋友在回答
3. 重點提供實用資訊，而不是分析過程
4. 如果是新聞查詢，提供具體的新聞內容和重點
5. 如果是資訊查詢，提供準確的事實和有用的建議
6. 若有參考資訊，如網址或是文件時，請附上資料來源
7. 避免使用「根據搜尋結果」、「資料顯示」等分析性語言
8. 讓回答看起來像是你本身就知道這些資訊

**回答格式：**
- 針對使用者需求回答主要問題
- 提供相關的詳細資訊
- 給出實用的建議或下一步行動（如適用）

請以自然、直接的方式回答，讓用戶感覺得到了有價值的幫助。
- 基於最新資訊
- 直接回應用戶需求
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=3000,
                    temperature=0.7
                )
            )
            
            if not response or len(response) == 0:
                raise ValueError("未能生成最終回答")
            
            final_answer = response[0].content
            logger.info(f"✅ {self.name} 最終回答生成完成")
            return final_answer
            
        except Exception as e:
            logger.error(f"❌ {self.name} 最終回答生成失敗: {e}")
            return await self._handle_error(user_query, str(e))
    
    async def _provide_direct_answer(self, user_query: str) -> str:
        """提供直接回答（無需搜尋）"""
        try:
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個知識豐富、友善的助理。請直接回答用戶的問題：

{user_query}

**回答指導：**
- 以自然、友好的語調回應
- 提供準確且實用的資訊
- 如果問題涉及即時資訊（如今天的新聞、股價等），請說明你的知識有時間限制
- 給出具體、可行的建議
- 保持回答簡潔而完整

請直接回答，不需要說明你的思考過程。
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=2000,
                    temperature=0.7
                )
            )
            
            if not response or len(response) == 0:
                return "抱歉，我無法為您提供回應。"
            
            return response[0].content
            
        except Exception as e:
            logger.error(f"❌ {self.name} 直接回答失敗: {e}")
            return f"抱歉，處理您的請求時發生錯誤：{str(e)}"
    
    def _parse_strategy(self, strategy_text: str) -> Dict[str, Any]:
        """解析策略分析結果"""
        import re
        
        strategy = {
            'approach': 'DIRECT_ANSWER',
            'tasks': [],
            'priority': 'MEDIUM',
            'understanding': '',
            'info_needed': ''
        }
        
        try:
            # 提取 APPROACH
            approach_match = re.search(r'APPROACH:\s*([^\n]+)', strategy_text, re.IGNORECASE)
            if approach_match:
                approach = approach_match.group(1).strip()
                strategy['approach'] = 'NEED_SEARCH' if 'NEED_SEARCH' in approach.upper() else 'DIRECT_ANSWER'
            
            # 提取 SEARCH_TASKS
            tasks_match = re.search(r'SEARCH_TASKS:\s*([^\n]+)', strategy_text, re.IGNORECASE)
            if tasks_match:
                tasks_str = tasks_match.group(1).strip()
                strategy['tasks'] = [task.strip() for task in tasks_str.split('|') if task.strip()]
            
            # 提取其他資訊
            priority_match = re.search(r'PRIORITY:\s*([^\n]+)', strategy_text, re.IGNORECASE)
            if priority_match:
                strategy['priority'] = priority_match.group(1).strip()
                
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 策略解析錯誤: {e}")
        
        return strategy
    
    def _parse_evaluation(self, evaluation_text: str) -> Dict[str, Any]:
        """解析完整性評估結果"""
        import re
        
        evaluation = {
            'need_more': False,
            'completeness': 5,
            'quality': 5,
            'next_query': None
        }
        
        try:
            # 提取 NEXT_ACTION
            action_match = re.search(r'NEXT_ACTION:\s*([^\n]+)', evaluation_text, re.IGNORECASE)
            if action_match:
                action = action_match.group(1).strip().upper()
                evaluation['need_more'] = 'SEARCH_MORE' in action
            
            # 提取 NEXT_QUERY
            query_match = re.search(r'NEXT_QUERY:\s*([^\n]+)', evaluation_text, re.IGNORECASE)
            if query_match:
                evaluation['next_query'] = query_match.group(1).strip()
                
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 評估解析錯誤: {e}")
        
        return evaluation
    
    def _reset_task_state(self):
        """重置任務狀態"""
        self.current_task = None
        self.search_history = []
        self.collected_info = {}
    
    async def _handle_error(self, user_query: str, error_msg: str) -> str:
        """處理錯誤情況"""
        return f"""抱歉，處理您的問題時遇到了技術問題。

您的問題：{user_query}

我會嘗試基於現有知識為您提供基本回答，但可能不夠完整。建議您稍後重試或重新表述問題。

錯誤詳情：{error_msg}"""
    
    async def analyze_and_plan(self, user_query: str) -> str:
        """
        為測試提供的簡化分析方法
        """
        try:
            available_tools = ["web_search"] if self.search_agent else []
            strategy = await self._analyze_and_plan(user_query, available_tools)
            return strategy.get('analysis', f"已分析查詢: {user_query}")
        except Exception as e:
            logger.error(f"❌ {self.name} 分析失敗: {e}")
            return f"分析失敗: {e}"
    
    def get_agent(self) -> ChatCompletionAgent:
        """獲取底層的 ChatCompletionAgent"""
        return self.agent
    
    def get_name(self) -> str:
        """獲取代理名稱"""
        return self.name
    
    def get_search_history(self) -> List[Dict[str, Any]]:
        """獲取搜尋歷史"""
        return self.search_history.copy()
    
    def get_collected_info(self) -> Dict[str, Any]:
        """獲取收集的資訊"""
        return self.collected_info.copy()