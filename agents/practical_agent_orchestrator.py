"""
基於 Semantic Kernel 1.37.0 的實用 Agent 架構
使用現有功能實現智能多 Agent 協作
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion
from semantic_kernel.functions import kernel_function
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.chat_history import ChatHistory
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)

class PracticalAgentOrchestrator:
    """實用的 Agent 協調器，基於 Semantic Kernel 基礎功能"""
    
    def __init__(self, chat_service):
        self.chat_service = chat_service
        self.kernel = Kernel()
        self.kernel.add_service(chat_service)
        
        # 對話歷史
        self.chat_history = ChatHistory()
        
        # 可用的專業能力
        self.available_capabilities = []
        
        # 對話記錄
        self.conversation_log = []
        
        logger.info("🎭 PracticalAgentOrchestrator 初始化完成")
    
    def add_web_search_capability(self) -> bool:
        """添加網路搜尋能力"""
        try:
            from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin
            
            # 初始化 Web Search Plugin
            web_search_plugin = OllamaWebSearchPlugin()
            
            # 將 plugin 添加到 kernel
            self.kernel.add_plugin(web_search_plugin, plugin_name="WebSearch")
            
            self.available_capabilities.append("web_search")
            logger.info("🔍 WebSearch 能力已添加")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ WebSearch 能力添加失敗: {e}")
            return False
    
    @kernel_function(
        description="智能任務分析和決策",
        name="analyze_and_decide"
    )
    def analyze_and_decide(self, user_input: str, capabilities: str) -> str:
        """智能分析用戶請求並決定處理策略"""
        
        prompt = f"""
你是一個智能任務協調者 (Thinker Agent)，需要分析用戶請求並選擇最佳的處理方式。

可用能力: {capabilities}

用戶請求: {user_input}

分析任務並決定：
1. 這個請求是否需要使用特殊能力？
2. 如果需要，應該使用哪種能力？
3. 如何最好地回應用戶？

請按此格式回應：
ANALYSIS: [對請求的分析]
DECISION: [DIRECT|WEB_SEARCH]
REASON: [決策理由]
APPROACH: [具體處理方法]
"""
        return prompt
    
    async def process_request(self, user_input: str, features: Dict[str, Any] = None) -> str:
        """處理用戶請求，智能選擇處理方式"""
        try:
            # 重置對話歷史為這次請求
            self.chat_history = ChatHistory()
            
            # 根據功能參數確定可用能力
            active_capabilities = []
            if features and features.get('web_search') and "web_search" in self.available_capabilities:
                active_capabilities.append("web_search")
            
            # 記錄請求
            self.conversation_log.append({
                "type": "user_request",
                "content": user_input,
                "features": features,
                "capabilities": active_capabilities
            })
            
            # 如果沒有特殊能力，直接處理
            if not active_capabilities:
                logger.info("📝 Thinker 直接處理請求")
                result = await self._direct_response(user_input)
                self._log_response("thinker_direct", result)
                return result
            
            # 使用 Thinker 分析並決策
            logger.info(f"🧠 Thinker 分析請求，可用能力: {active_capabilities}")
            
            decision_prompt = self.analyze_and_decide(
                user_input=user_input,
                capabilities=", ".join(active_capabilities)
            )
            
            decision_result = await self._invoke_with_prompt(decision_prompt)
            self._log_response("thinker_analysis", decision_result)
            
            logger.info(f"🤔 Thinker 決策: {decision_result[:150]}...")
            
            # 根據決策選擇處理方式
            if "DECISION: WEB_SEARCH" in decision_result and "web_search" in active_capabilities:
                logger.info("🔍 使用 WebSearch 能力")
                result = await self._use_web_search(user_input, decision_result)
                self._log_response("web_search_agent", result)
                return result
            else:
                logger.info("📝 Thinker 提供直接回應")
                result = await self._extract_or_generate_response(decision_result, user_input)
                self._log_response("thinker_response", result)
                return result
                
        except Exception as e:
            logger.error(f"❌ 處理請求失敗: {e}")
            error_response = f"抱歉，處理您的請求時發生錯誤。我會嘗試基於現有知識回答您的問題。\n\n{await self._direct_response(user_input)}"
            self._log_response("error_fallback", error_response)
            return error_response
    
    async def _direct_response(self, user_input: str) -> str:
        """直接回應用戶請求"""
        prompt = f"""
請針對以下問題提供清晰、準確且有幫助的回答：

{user_input}

請確保回答：
- 基於可靠的知識
- 結構清晰
- 實用且具體
"""
        return await self._invoke_with_prompt(prompt)
    
    async def _use_web_search(self, user_input: str, analysis: str) -> str:
        """使用 WebSearch 能力處理請求"""
        try:
            # 準備搜尋查詢
            search_preparation_prompt = f"""
基於以下分析和用戶請求，準備進行網路搜尋：

用戶請求: {user_input}
分析結果: {analysis}

請提供：
1. 最佳的搜尋關鍵字
2. 搜尋後需要重點關注的資訊

格式：
KEYWORDS: [搜尋關鍵字]
FOCUS: [重點關注的資訊類型]
"""
            
            search_plan = await self._invoke_with_prompt(search_preparation_prompt)
            logger.info(f"🎯 搜尋計劃: {search_plan[:100]}...")
            
            # 執行網路搜尋
            try:
                from lyrallm.functions.kernel_arguments import KernelArguments
                
                search_args = KernelArguments(query=user_input)
                search_result = await self.kernel.invoke(
                    plugin_name="WebSearch",
                    function_name="search",
                    arguments=search_args
                )
                
                logger.info("✅ 網路搜尋完成")
                
                # 分析和總結搜尋結果
                synthesis_prompt = f"""
基於網路搜尋結果，為用戶提供綜合性回答：

原始請求: {user_input}
搜尋結果: {str(search_result)}

請提供：
1. 清晰的總結
2. 重要發現
3. 相關建議或見解
4. 如果適用，提及資訊來源的時效性

請確保回答結構清晰、資訊準確且對用戶有價值。
"""
                
                final_response = await self._invoke_with_prompt(synthesis_prompt)
                return final_response
                
            except Exception as search_error:
                logger.error(f"❌ 網路搜尋失敗: {search_error}")
                # 回退到直接回答
                fallback_prompt = f"""
無法進行網路搜尋，請基於現有知識盡可能回答：

{user_input}

請說明：
1. 基於已知資訊的回答
2. 哪些資訊可能需要最新的網路搜尋
3. 建議用戶如何獲取最新資訊
"""
                return await self._invoke_with_prompt(fallback_prompt)
                
        except Exception as e:
            logger.error(f"❌ WebSearch 流程失敗: {e}")
            return await self._direct_response(user_input)
    
    async def _extract_or_generate_response(self, decision_result: str, original_request: str) -> str:
        """從決策結果中提取回應或生成新回應"""
        try:
            # 如果決策結果中包含了回應，嘗試提取
            if "APPROACH:" in decision_result:
                approach_section = decision_result.split("APPROACH:")[1].strip()
                if len(approach_section) > 50:  # 如果有足夠的內容
                    return approach_section
            
            # 否則生成新的回應
            response_prompt = f"""
基於以下分析，為用戶提供最終回答：

分析結果: {decision_result}

原始請求: {original_request}

請提供清晰、完整的回答。
"""
            return await self._invoke_with_prompt(response_prompt)
            
        except Exception as e:
            logger.error(f"❌ 回應生成失敗: {e}")
            return await self._direct_response(original_request)
    
    async def _invoke_with_prompt(self, prompt: str) -> str:
        """使用 prompt 調用語言模型"""
        try:
            # 添加用戶訊息
            self.chat_history.add_user_message(prompt)
            
            # 獲取回應
            response = await self.chat_service.get_chat_message_contents(
                chat_history=self.chat_history,
                settings=self.chat_service.get_prompt_execution_settings_class()(
                    max_tokens=2000,
                    temperature=0.7
                )
            )
            
            if response and len(response) > 0:
                content = response[0].content
                # 添加回應到歷史
                self.chat_history.add_assistant_message(content)
                return content
            else:
                return "未能獲得有效回應"
                
        except Exception as e:
            logger.error(f"❌ 模型調用失敗: {e}")
            return f"語言模型調用失敗：{str(e)}"
    
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
        
        # 不自動添加能力，由調用方根據需求添加
        # orchestrator.add_web_search_capability()  # 移除自動添加
        
        return orchestrator
        
    except Exception as e:
        logger.error(f"❌ 創建 Agent 協調器失敗: {e}")
        return None