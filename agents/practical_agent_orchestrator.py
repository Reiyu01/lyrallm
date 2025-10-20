"""
基於 Semantic Kernel 1.37.0 的實用 Agent 架構
使用現有功能實現智能多 Agent 協作
重構版本：使用獨立的 Thinker Agent 和 Search Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.chat_history import ChatHistory
from config.config_manager import config_manager
from .smart_parameter_manager import smart_settings

# 導入新的獨立 Agent
from .thinker_agent import ThinkerAgent
from .search_agent import SearchAgent
from .rag_agent import RAGAgent

logger = logging.getLogger(__name__)

class PracticalAgentOrchestrator:
    """實用的 Agent 協調器，基於 Semantic Kernel 基礎功能 - 重構版本"""
    
    def __init__(self, chat_service: ChatCompletionClientBase):
        self.chat_service = chat_service
        
        # 初始化獨立的 Agent
        self.thinker_agent = ThinkerAgent(chat_service)
        self.search_agent = None  # 延遲初始化
        self.rag_agent = None  # 延遲初始化
        
        # 對話歷史
        self.chat_history = ChatHistory()
        
        # 可用的專業能力
        self.available_capabilities = []
        
        # 預設啟用 RAG 搜尋能力
        rag_enabled = self.add_rag_capability()
        if not rag_enabled:
            logger.warning("⚠️ RAG 能力啟用失敗，將以基本模式運行")
        
        # 對話記錄
        self.conversation_log = []
        
        logger.info("🎭 PracticalAgentOrchestrator 重構版本初始化完成")
        if rag_enabled:
            logger.info("🧠 RAG 搜尋能力已預設啟用")
        else:
            logger.info("📝 RAG 搜尋能力未啟用，可稍後手動啟用")
    
    def add_web_search_capability(self) -> bool:
        """啟用網路搜尋能力，初始化 Search Agent"""
        try:
            if self.search_agent is None:
                self.search_agent = SearchAgent(self.chat_service)
            
            if "web_search" not in self.available_capabilities:
                self.available_capabilities.append("web_search")
                
            logger.info("🔌 WebSearch 能力已啟用 (Search Agent 模式)")
            return True
        except Exception as e:
            logger.error(f"❌ 無法啟用 WebSearch：{e}")
            return False
    
    def add_rag_capability(self) -> bool:
        """啟用 RAG 搜尋能力，初始化 RAG Agent"""
        try:
            if self.rag_agent is None:
                self.rag_agent = RAGAgent(self.chat_service)
            
            if "rag_search" not in self.available_capabilities:
                self.available_capabilities.append("rag_search")
                
            logger.info("🧠 RAG 能力已啟用 (RAG Agent 模式)")
            return True
        except Exception as e:
            logger.error(f"❌ 無法啟用 RAG：{e}")
            return False
    

    
    async def process_request(self, user_input: str, features: Dict[str, Any] = None) -> str:
        """
        處理用戶請求 - 使用 ThinkerAgent 作為主控制器
        
        新的流程：
        1. ThinkerAgent 接管主控制權
        2. 自主決定是否需要搜尋以及搜尋策略  
        3. 協調多輪搜尋任務
        4. 生成最終整合回應
        """
        try:
            logger.info(f"🎬 開始處理請求")
            logger.info(f"📋 委託 ThinkerAgent 作為主控制器")
            
            # 重置對話歷史為這次請求
            self.chat_history = ChatHistory()
            
            # 確保 Agent 可用（如果需要搜尋功能）
            if features and features.get('web_search'):
                if "web_search" not in self.available_capabilities:
                    self.add_web_search_capability()
            
            # 記錄請求
            self.conversation_log.append({
                "type": "user_request", 
                "content": user_input,
                "features": features,
                "mode": "thinker_agent_controller"
            })
            
            # 直接委託 ThinkerAgent 處理整個流程
            # ThinkerAgent 將自主決定是否需要搜尋，以及如何協調
            # 注意：即使沒有 web_search，也會傳遞 RAG agent
            final_response = await self.thinker_agent.process_user_query(
                user_query=user_input,
                search_agent=self.search_agent if (features and features.get('web_search')) else None,
                rag_agent=self.rag_agent if self.rag_agent else None
            )
            
            # 記錄最終回應
            self._log_response("thinker_agent_final", final_response)
            
            logger.info(f"✅ 請求處理完成 (ThinkerAgent 控制模式)")
            return final_response
            
        except Exception as e:
            logger.error(f"❌ 處理請求失敗: {e}")
            
            # 提供更詳細的錯誤回退
            try:
                fallback_response = await self._direct_response_fallback(user_input)
                self._log_response("error_fallback", fallback_response)
                return fallback_response
            except Exception as fallback_error:
                logger.error(f"❌ 錯誤回退也失敗: {fallback_error}")
                return f"""抱歉，處理您的請求時發生錯誤。

錯誤詳情：{str(e)}

建議：
1. 請稍後再試
2. 嘗試重新表述您的問題
3. 檢查問題是否過於複雜

如果問題持續存在，請聯繫技術支援。"""
    
    async def _direct_response_fallback(self, user_input: str) -> str:
        """錯誤時的回退回應方法"""
        try:
            # 嘗試使用基本的聊天服務直接回應
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""請基於您的知識回答以下問題：

{user_input}

如果您不確定某些資訊，請說明哪些部分可能需要最新的網路搜尋來確認。""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service, 
                    max_completion_tokens=2000,
                    temperature=0.7
                )
            )
            
            if response and len(response) > 0:
                return f"⚠️ 系統暫時無法進行完整分析，以下是基於現有知識的回答：\n\n{response[0].content}"
            else:
                return "抱歉，系統暫時無法回應您的請求，請稍後再試。"
                
        except Exception as e:
            logger.error(f"❌ 回退回應失敗: {e}")
            return "抱歉，系統暫時不可用，請稍後再試或聯繫技術支援。"
    
    async def _direct_response(self, user_input: str) -> str:
        """直接回應用戶請求 - 使用 Thinker Agent"""
        decision_info = await self.thinker_agent.process_request(user_input, [])
        return decision_info['response']
    
    async def _use_search_agent(self, user_input: str, analysis: str) -> str:
        """
        流程編號 #014: WebSearch處理流程入口
        使用 Search Agent 處理請求
        """
        try:
            if self.search_agent is None:
                raise RuntimeError("Search Agent 未初始化")
            
            # 使用 Search Agent 執行搜尋和分析
            result = await self.search_agent.search_and_analyze(user_input, analysis)
            return result
                
        except Exception as e:
            logger.error(f"❌ Search Agent 處理失敗: {e}")
            return await self._direct_response(user_input)
    
    async def _extract_or_generate_response(self, decision_result: str, original_request: str) -> str:
        """從決策結果中提取回應或生成新回應 - 使用 Thinker Agent"""
        try:
            decision_info = await self.thinker_agent.process_request(original_request, [])
            return decision_info['response']
        except Exception as e:
            logger.error(f"❌ 回應生成失敗: {e}")
            return await self._direct_response(original_request)
    

    
    def _log_response(self, agent_type: str, content: str):
        """記錄 Agent 回應"""
        self.conversation_log.append({
            "type": agent_type,
            "content": content[:200] + ("..." if len(content) > 200 else ""),
            "full_length": len(content)
        })
    
    def get_available_features(self) -> List[str]:
        """獲取可用功能列表"""
        return self.available_capabilities.copy()
    
    def get_conversation_log(self) -> List[Dict[str, Any]]:
        """獲取對話記錄"""
        return self.conversation_log.copy()
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """獲取對話歷史（別名方法）"""
        return self.get_conversation_log()
    
    def clear_conversation_log(self):
        """清空對話記錄"""
        self.conversation_log = []

    async def __aexit__(self, exc_type, exc, tb):
        # 清理資源
        try:
            if self.search_agent:
                await self.search_agent.cleanup()
        except Exception as e:
            logger.error(f"❌ 清理 Search Agent 時發生錯誤: {e}")
    
    async def cleanup(self):
        """手動清理資源"""
        if self.search_agent:
            await self.search_agent.cleanup()
        if self.rag_agent:
            await self.rag_agent.cleanup()

async def create_practical_agent_orchestrator(chat_service=None) -> Optional[PracticalAgentOrchestrator]:
    """創建實用的 Agent 協調器"""
    try:
        # 如果沒有提供 chat_service，則創建預設的
        if chat_service is None:
            # 獲取可用模型
            available_models = config_manager.get_available_models()
            supported_models = [m for m in available_models 
                              if m.get('provider') in ['azure_openai', 'openai']]
            
            if not supported_models:
                logger.error("❌ 沒有可用的支援模型")
                return None
            
            model_config = supported_models[0]
            provider = model_config.get('provider')
            
            # 創建聊天服務
            if provider == 'azure_openai':
                chat_service = AzureChatCompletion(
                    service_id=f"agent_{model_config['name']}",
                    deployment_name=model_config.get('deployment_name'),
                    endpoint=model_config.get('endpoint'),
                    api_key=model_config.get('api_key'),
                    api_version=model_config.get('api_version')
                )
            elif provider == 'openai':
                chat_service = OpenAIChatCompletion(
                    service_id=f"agent_{model_config['name']}",
                    ai_model_id=model_config['name'],
                    api_key=model_config.get('api_key'),
                    base_url=model_config.get('endpoint')
                )
            else:
                logger.error(f"❌ 不支援的提供者: {provider}")
                return None
            
            logger.info(f"✅ 使用預設模型創建 Agent 協調器: {model_config['name']}")
        else:
            # 使用提供的 chat_service
            service_id = getattr(chat_service, 'service_id', 'unknown')
            logger.info(f"✅ 使用指定模型創建 Agent 協調器: {service_id}")
        
        # 創建協調器
        orchestrator = PracticalAgentOrchestrator(chat_service)
        
        # RAG 能力已在協調器初始化時自動啟用
        # 不自動添加 web search 能力，由調用方根據需求添加
        # orchestrator.add_web_search_capability()  # 移除自動添加
        
        return orchestrator
        
    except Exception as e:
        logger.error(f"❌ 創建 Agent 協調器失敗: {e}")
        return None