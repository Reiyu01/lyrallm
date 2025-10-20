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
4. **搜尋類型選擇**: 每個任務應該用網路搜尋(WEB)還是知識庫搜尋(RAG)？
5. **優先順序**: 哪些資訊最重要？

請按此格式回應：
UNDERSTANDING: [對用戶需求的深度理解]
INFO_NEEDED: [需要的具體資訊列表]
SEARCH_TASKS: [具體的查詢任務，用 | 分隔]
SEARCH_TYPES: [對應每個任務的搜尋類型：WEB|RAG，用 | 分隔]
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
    
    def set_rag_agent(self, rag_agent: 'RAGAgent'):
        """設置 RAG 代理"""
        self.rag_agent = rag_agent
        logger.info(f"🔗 {self.name} 已連接到 RAGAgent")
    
    async def process_user_query(self, user_query: str, search_agent=None, rag_agent=None) -> str:
        """
        處理用戶查詢的主入口點
        
        Args:
            user_query: 用戶查詢內容
            search_agent: 網路搜尋代理（可選）
            rag_agent: RAG 代理（可選）
            
        Returns:
            str: 最終回應
        """
        try:
            logger.info(f"🧠 {self.name} 開始處理查詢: {user_query[:50]}...")
            
            # 設置可用的代理
            if search_agent:
                self.search_agent = search_agent
                logger.info(f"🔍 {self.name} WebSearch 代理已設定")
            if rag_agent:
                self.rag_agent = rag_agent
                logger.info(f"📚 {self.name} RAG 代理已設定")
            
            # 重置搜尋歷史
            self.search_history = []
            self.collected_info = {}
            
            # 準備可用工具列表
            available_tools = []
            if self.search_agent:
                available_tools.append("WebSearch")
            if self.rag_agent:
                available_tools.append("RAG")
            
            logger.info(f"🛠️ {self.name} 可用工具: {available_tools}")
            
            # 第一步：初始決策 - 是否需要 Agent 模式（僅當沒有明確工具需求時）
            if not available_tools:
                # 沒有任何工具可用，直接回答
                logger.info(f"📝 {self.name} 無可用工具，直接回答")
                return await self._provide_direct_answer(user_query)
            
            # 如果用戶明確提到 RAG、搜尋等關鍵詞，跳過初始決策
            if self._has_explicit_tool_request(user_query):
                logger.info(f"🎯 {self.name} 檢測到明確工具請求，跳過初始決策")
                initial_decision = {'mode': 'AGENT_MODE', 'reason': '明確工具請求', 'confidence': 10}
            else:
                initial_decision = await self._make_initial_decision(user_query, available_tools)
            
            if initial_decision['mode'] == 'DIRECT_ANSWER':
                logger.info(f"� {self.name} 決定直接回答，不使用特殊工具")
                return await self._provide_direct_answer(user_query)
            
            # 第二步：分析和制定策略
            strategy = await self._analyze_and_plan(user_query, available_tools)
            
            if strategy['approach'] == 'DIRECT_ANSWER':
                # 不需要搜尋
                logger.info("� 無需搜尋，提供直接回答")
                return await self._provide_direct_answer(user_query)
            else:
                # 需要搜尋
                logger.info("� 啟動多輪搜尋流程")
                return await self._multi_round_search_process(user_query, strategy)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 處理查詢失敗: {e}")
            return await self._handle_error(user_query, str(e))

    def _has_explicit_tool_request(self, query: str) -> bool:
        """檢測查詢是否明確要求使用特定工具"""
        query_lower = query.lower()
        explicit_keywords = [
            'rag', '查詢', '搜尋', '搜索', 'search', 
            '知識庫', '文檔', '員工手冊', '技術規範',
            '專案指南', '課程資訊', '常見問題'
        ]
        return any(keyword in query_lower for keyword in explicit_keywords)

    async def _make_initial_decision(self, user_query: str, available_tools: List[str]) -> Dict[str, Any]:
        """
        初始決策：判斷是否真正需要 Agent 模式
        這是新增的第一層決策，決定是否退出 Agent 模式
        """
        try:
            tools_str = ", ".join(available_tools) if available_tools else "無特殊工具"
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個智能決策系統，需要判斷用戶的查詢是否需要使用特殊工具（如搜尋、知識庫查詢等）。

用戶問題: {user_query}
可用工具: {tools_str}

**判斷標準**：
1. 如果問題可以直接基於常識或基礎知識回答，選擇 DIRECT_ANSWER
2. 如果需要搜尋最新資訊、特定事實、內部文檔等，選擇 AGENT_MODE
3. 如果問題涉及計算、編程、創作等複雜任務，選擇 AGENT_MODE

**特別注意**：
- 簡單的問候、基礎概念解釋 → DIRECT_ANSWER
- 需要查詢具體資料、最新資訊 → AGENT_MODE  
- 明確提到「搜尋」、「查詢」、「RAG」等 → AGENT_MODE

請按此格式回應：
MODE: [DIRECT_ANSWER 或 AGENT_MODE]
REASON: [決策理由]
CONFIDENCE: [1-10的信心分數]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=500,
                    temperature=0.1
                )
            )
            
            if not response or len(response) == 0:
                # 預設使用 Agent 模式
                return {'mode': 'AGENT_MODE', 'reason': '無法獲得決策，使用 Agent 模式', 'confidence': 5}
            
            decision_text = response[0].content
            return self._parse_initial_decision(decision_text)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 初始決策失敗: {e}")
            # 發生錯誤時預設使用 Agent 模式
            return {'mode': 'AGENT_MODE', 'reason': f'決策錯誤: {e}', 'confidence': 3}

    def _parse_initial_decision(self, decision_text: str) -> Dict[str, Any]:
        """解析初始決策結果"""
        import re
        
        decision = {
            'mode': 'AGENT_MODE',  # 預設使用 Agent 模式
            'reason': '未能解析決策',
            'confidence': 5
        }
        
        try:
            # 提取 MODE
            mode_match = re.search(r'MODE:\s*([^\n]+)', decision_text, re.IGNORECASE)
            if mode_match:
                mode = mode_match.group(1).strip().upper()
                if 'DIRECT' in mode:
                    decision['mode'] = 'DIRECT_ANSWER'
                else:
                    decision['mode'] = 'AGENT_MODE'
            
            # 提取 REASON
            reason_match = re.search(r'REASON:\s*([^\n]+)', decision_text, re.IGNORECASE)
            if reason_match:
                decision['reason'] = reason_match.group(1).strip()
            
            # 提取 CONFIDENCE
            confidence_match = re.search(r'CONFIDENCE:\s*([^\n]+)', decision_text, re.IGNORECASE)
            if confidence_match:
                try:
                    decision['confidence'] = int(confidence_match.group(1).strip())
                except:
                    decision['confidence'] = 5
            
            logger.info(f"🎯 {self.name} 初始決策: {decision['mode']} (信心: {decision['confidence']}) - {decision['reason']}")
            
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 決策解析錯誤: {e}")
        
        return decision
    
    async def _analyze_and_plan(self, user_query: str, available_tools: List[str]) -> Dict[str, Any]:
        """分析用戶需求並制定策略"""
        try:
            tools_str = ", ".join(available_tools) if available_tools else "無特殊工具"
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個智能任務分析師，需要深度理解用戶需求並制定查詢策略。

用戶問題: {user_query}
可用工具: {tools_str}

**重要：選擇搜尋類型的指導原則**
- 如果用戶明確提到「RAG」、「知識庫」、「文檔」、「內部資料」、「員工手冊」、「技術規範」、「專案指南」、「課程資訊」、「FAQ」等關鍵詞，應優先使用 RAG 搜尋
- 如果問題涉及公司內部政策、流程、技術標準、員工培訓等內容，應使用 RAG 搜尋
- 如果需要最新資訊、新聞、實時數據、網路資源，應使用 WEB 搜尋
- 當不確定時，如果有 RAG 工具可用，優先嘗試 RAG 搜尋

請進行以下分析：
1. **需求理解**: 用戶真正想要了解什麼？
2. **資訊來源判斷**: 這個問題更可能在內部文檔還是網路上找到答案？
3. **查詢策略**: 如何拆解查詢任務？
4. **搜尋類型選擇**: 每個任務應該用網路搜尋(WEB)還是知識庫搜尋(RAG)？

請按此格式回應：
UNDERSTANDING: [對用戶需求的深度理解]
INFO_SOURCE: [資訊來源判斷：INTERNAL_DOCS|EXTERNAL_WEB|MIXED]
SEARCH_TASKS: [具體的查詢任務，用 | 分隔]
SEARCH_TYPES: [對應每個任務的搜尋類型：WEB|RAG，用 | 分隔]
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
            # 智能預設搜尋類型
            default_search_types = []
            for task in search_tasks:
                # 檢查任務內容，智能選擇搜尋類型
                if self._should_use_rag(task):
                    default_search_types.append('RAG')
                else:
                    default_search_types.append('RAG' if self.rag_agent else 'WEB')
            
            search_types = strategy.get('search_types', default_search_types)
            
            for round_num in range(max_rounds):
                logger.info(f"🔄 {self.name} 第 {round_num + 1} 輪搜尋")
                
                # 執行當前輪次的搜尋
                current_task = search_tasks[0] if search_tasks else user_query
                current_type = search_types[0] if search_types else ('RAG' if self.rag_agent else 'WEB')
                search_result = await self._execute_search(current_task, current_type)
                
                # 記錄搜尋結果
                self.search_history.append({
                    'round': round_num + 1,
                    'query': current_task,
                    'result': search_result
                })
                
                # 簡化評估：對於明確的工具請求，一次搜尋通常足夠
                if self._has_explicit_tool_request(user_query) and round_num == 0:
                    logger.info(f"✅ {self.name} 明確工具請求完成，跳過多輪評估")
                    break
                
                # 評估是否需要更多搜尋（僅對複雜查詢且非最後一輪）
                if round_num < max_rounds - 1 and len(search_tasks) > 1:
                    try:
                        need_more = await self._evaluate_completeness(user_query, search_result)
                        
                        if not need_more['need_more']:
                            logger.info(f"✅ {self.name} 資訊收集完成")
                            break
                            
                        # 準備下一輪搜尋
                        if need_more.get('next_query'):
                            search_tasks = [need_more['next_query']]
                            search_types = [search_types[0] if search_types else ('RAG' if self.rag_agent else 'WEB')]
                        elif search_tasks and search_types:
                            # 移除已完成的任務
                            search_tasks.pop(0)
                            search_types.pop(0)
                            
                            if not search_tasks:
                                break
                        else:
                            break
                    except Exception as e:
                        logger.warning(f"⚠️ {self.name} 完整性評估失敗，繼續處理: {e}")
                        break
                else:
                    # 單次搜尋或達到最大輪數
                    break
            
            # 整合所有資訊並生成最終回答
            return await self._generate_final_answer(user_query)
            
        except Exception as e:
            logger.error(f"❌ {self.name} 多輪搜尋失敗: {e}")
            return await self._handle_error(user_query, str(e))
    
    async def _execute_search(self, query: str, search_type: str = "WEB") -> Dict[str, Any]:
        """執行搜尋任務"""
        search_type = search_type.upper()
        
        if search_type == "RAG" and self.rag_agent:
            logger.info(f"🧠 執行 RAG 搜尋: {query}")
            search_result = await self.rag_agent.execute_rag_search(query)
        elif search_type == "WEB" and self.search_agent:
            logger.info(f"🔍 執行網路搜尋: {query}")
            search_result = await self.search_agent.execute_search(query)
        else:
            # 智能降級處理
            if search_type == "RAG" and not self.rag_agent and self.search_agent:
                logger.warning(f"⚠️ RAG 不可用，降級為網路搜尋: {query}")
                search_result = await self.search_agent.execute_search(query)
            elif search_type == "WEB" and not self.search_agent and self.rag_agent:
                logger.warning(f"⚠️ 網路搜尋不可用，降級為 RAG 搜尋: {query}")
                search_result = await self.rag_agent.execute_rag_search(query)
            elif self.rag_agent:
                logger.info(f"🧠 使用 RAG 搜尋: {query}")
                search_result = await self.rag_agent.execute_rag_search(query)
            elif self.search_agent:
                logger.warning(f"⚠️ RAG 不可用，使用網路搜尋: {query}")
                search_result = await self.search_agent.execute_search(query)
            else:
                raise ValueError("沒有可用的搜尋代理")
        
        # 記錄到收集的資訊中
        timestamp = len(self.search_history) + 1
        search_result['search_type'] = search_type
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
            # 整理所有搜尋資料（優化 RAG 結果處理）
            all_data = []
            total_length = 0
            max_context_length = 8000  # 限制 context 大小
            
            for i, search_record in enumerate(self.search_history):
                # 智能提取搜尋結果中的有用資訊
                result_data = search_record.get('result', {})
                
                # 提取實際的搜尋內容
                extracted_content = self._extract_search_content(result_data)
                
                data_chunk = f"搜尋 {i+1}: {search_record['query']}\n內容: {extracted_content}\n"
                
                if total_length + len(data_chunk) > max_context_length:
                    break
                    
                all_data.append(data_chunk)
                total_length += len(data_chunk)
            
            all_search_data = "\n".join(all_data)
            
            # 如果沒有搜尋資料，直接使用基礎回答
            if not all_search_data.strip():
                logger.warning(f"⚠️ {self.name} 沒有有效的搜尋資料，使用直接回答")
                return await self._provide_direct_answer(user_query)
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個專業的助理，根據搜集到的資料直接回答用戶問題。

用戶問題: {user_query}

搜尋到的相關資料:
{all_search_data}

請根據上述資料回答用戶的問題：

**如果資料來自網路搜尋：**
- 整理和總結搜尋到的最新資訊
- 提供具體的新聞、數據或事實
- 以清晰的結構呈現信息
- 注明資訊的時效性和來源可靠性

**如果資料來自企業知識庫：**
- 直接引用相關的政策、規範或指引
- 提供具體的內部流程或標準
- 如果資料中包含具體的步驟，請詳細說明

**通用要求：**
- 以友好自然的語調回應
- 提供具體實用的資訊
- 基於搜尋到的實際資料給出準確的回答
- 如果搜尋結果不夠完整，請如實說明

重要：請確保回答內容來自於提供的搜尋資料，不要編造資訊。
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=2000,
                    temperature=0.7
                )
            )
            
            # 添加短暫延遲以避免 API 速率限制
            await asyncio.sleep(0.5)
            
            if not response or len(response) == 0:
                raise ValueError("未能生成最終回答")
            
            final_answer = response[0].content
            logger.info(f"✅ {self.name} 最終回答生成完成")
            return final_answer
            
        except Exception as e:
            logger.error(f"❌ {self.name} 最終回答生成失敗: {e}")
            return await self._handle_error(user_query, str(e))
    
    def _extract_search_content(self, result_data: Dict[str, Any]) -> str:
        """智能提取搜尋結果中的有用內容"""
        try:
            if isinstance(result_data, dict):
                # 1. 檢查是否是 Web Search 結果格式
                if result_data.get('success') is not None and 'raw_results' in result_data:
                    # Web Search Agent 的返回格式
                    if result_data.get('success'):
                        raw_results = result_data.get('raw_results', '')
                        sources = result_data.get('sources', [])
                        query_used = result_data.get('query_used', '')
                        
                        content_parts = []
                        if query_used:
                            content_parts.append(f"搜索關鍵字: {query_used}")
                        
                        if raw_results:
                            # 限制內容長度避免過長
                            if len(raw_results) > 2000:
                                raw_results = raw_results[:2000] + "...[內容截斷]"
                            content_parts.append(f"搜索結果:\n{raw_results}")
                        
                        if sources:
                            sources_str = "\n".join(sources[:5])  # 最多顯示5個來源
                            content_parts.append(f"資料來源:\n{sources_str}")
                        
                        return "\n\n".join(content_parts)
                    else:
                        # Web Search 失敗
                        error_msg = result_data.get('error', '未知錯誤')
                        return f"網路搜索失敗: {error_msg}"
                
                # 2. 檢查是否是 RAG 搜尋結果格式
                elif 'analyzed_results' in result_data or 'search_results' in result_data:
                    # RAG Agent 的返回格式
                    # 優先嘗試提取 analyzed_results 中的關鍵資訊
                    analyzed_results = result_data.get('analyzed_results', {})
                    if analyzed_results and isinstance(analyzed_results, dict):
                        key_info = analyzed_results.get('key_information', '')
                        summary = analyzed_results.get('summary', '')
                        if key_info and key_info != '':
                            content = f"關鍵資訊: {key_info}"
                            if summary and summary != '':
                                content += f"\n摘要: {summary}"
                            return content
                    
                    # 嘗試提取搜尋結果中的文本內容
                    search_results = result_data.get('search_results', [])
                    if search_results and isinstance(search_results, list):
                        extracted_texts = []
                        for i, result in enumerate(search_results[:3]):  # 只取前3個結果
                            if isinstance(result, dict):
                                text = result.get('text', '')
                                if text:
                                    # 截斷過長的文本
                                    if len(text) > 500:
                                        text = text[:500] + "..."
                                    extracted_texts.append(f"文檔 {i+1}: {text}")
                        
                        if extracted_texts:
                            return "\n".join(extracted_texts)
                    
                    # RAG 的成功/失敗資訊
                    if result_data.get('success'):
                        return f"RAG 搜尋成功，找到 {len(search_results)} 個相關文檔"
                    elif result_data.get('error'):
                        return f"RAG 搜尋遇到問題: {result_data.get('error')}"
                
                # 3. 其他格式的字典，嘗試提取有用信息
                else:
                    # 嘗試找到包含實際內容的字段
                    content_fields = ['content', 'result', 'text', 'data', 'response']
                    for field in content_fields:
                        if field in result_data and result_data[field]:
                            content = str(result_data[field])
                            if len(content) > 1000:
                                content = content[:1000] + "...[內容截斷]"
                            return content
            
            # 如果是其他格式，轉為字符串並截斷
            result_str = str(result_data)
            if len(result_str) > 1000:
                result_str = result_str[:1000] + "...[內容截斷]"
            return result_str
            
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 提取搜尋內容失敗: {e}")
            # 降級處理
            result_str = str(result_data)
            if len(result_str) > 500:
                result_str = result_str[:500] + "...[提取失敗]"
            return result_str

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

    def _should_use_rag(self, query: str) -> bool:
        """智能判斷是否應該使用 RAG 搜尋"""
        if not self.rag_agent:
            return False
            
        # RAG 關鍵詞
        rag_keywords = [
            'rag', '知識庫', '文檔', '內部資料', '員工手冊', '技術規範', 
            '專案指南', '課程資訊', 'faq', '常見問題', '公司政策', 
            '流程', '標準', '培訓', '規範', '指南', '手冊', '政策',
            '內部', '公司', '組織', '部門', '員工', '工作'
        ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in rag_keywords)
    
    def _parse_strategy(self, strategy_text: str) -> Dict[str, Any]:
        """解析策略分析結果"""
        import re
        
        strategy = {
            'approach': 'DIRECT_ANSWER',
            'tasks': [],
            'search_types': [],
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
            
            # 提取 SEARCH_TYPES
            types_match = re.search(r'SEARCH_TYPES:\s*([^\n]+)', strategy_text, re.IGNORECASE)
            if types_match:
                types_str = types_match.group(1).strip()
                strategy['search_types'] = [t.strip().upper() for t in types_str.split('|') if t.strip()]
                # 確保搜尋類型數量與任務數量一致
                while len(strategy['search_types']) < len(strategy['tasks']):
                    # 智能預設：如果有 RAG 可用，優先使用 RAG，否則使用 WEB
                    default_type = 'RAG' if self.rag_agent else 'WEB'
                    strategy['search_types'].append(default_type)
            else:
                # 如果沒有明確指定搜尋類型，根據可用工具智能選擇
                strategy['search_types'] = []
                for _ in strategy['tasks']:
                    # 預設策略：有 RAG 優先用 RAG，沒有才用 WEB
                    default_type = 'RAG' if self.rag_agent else 'WEB'
                    strategy['search_types'].append(default_type)
            
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