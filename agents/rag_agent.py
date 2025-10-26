"""
RAG Agent - 負責 Elasticsearch RAG 搜尋
專注於執行向量搜尋、檢索相關文檔並返回結構化資料
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions import kernel_function
from .smart_parameter_manager import smart_settings

# 導入 embedding 和 ES 相關模組
from lyrallm.config.config_manager import config_manager
from adapters.elasticsearch_adapter import ElasticsearchAdapter
from embedding_provider import get_default_provider

logger = logging.getLogger(__name__)

class RAGAgentPlugin:
    """RAG Agent 的核心功能插件 - RAG 搜尋版本"""
    
    @kernel_function(
        description="優化 RAG 查詢並提取關鍵資訊",
        name="optimize_rag_query"
    )
    def optimize_rag_query(self, user_query: str, context: str) -> str:
        """優化 RAG 查詢以獲得更相關的向量搜尋結果"""
        return f"""
你是一個 RAG 搜尋專家，需要優化查詢以獲得最相關的知識庫結果。

用戶查詢: {user_query}
背景資訊: {context}

請分析並提供：
1. **核心概念**: 提取查詢中的關鍵概念和實體
2. **搜尋關鍵字**: 最適合向量搜尋的關鍵字組合
3. **相關主題**: 可能相關的主題或概念
4. **查詢意圖**: 用戶想要獲得的資訊類型

請按此格式回應：
CORE_CONCEPTS: [核心概念1, 概念2, 概念3]
SEARCH_KEYWORDS: [優化後的搜尋關鍵字]
RELATED_TOPICS: [相關主題1, 主題2, 主題3]
QUERY_INTENT: [資訊檢索意圖說明]
SEARCH_STRATEGY: [向量搜尋策略]
"""

    @kernel_function(
        description="分析和整理 RAG 搜尋結果",
        name="analyze_rag_results"
    )
    def analyze_rag_results(self, search_results: str, user_query: str) -> str:
        """分析 RAG 搜尋結果並提取關鍵資訊"""
        return f"""
你是一個資訊分析專家，需要分析 RAG 搜尋結果並提取最相關的資訊。

原始查詢: {user_query}
搜尋結果: {search_results}

請進行以下分析：
1. **相關性評估**: 評估每個結果與查詢的相關性
2. **關鍵資訊提取**: 提取回答查詢所需的關鍵資訊
3. **資訊品質**: 評估資訊的可靠性和完整性
4. **缺失資訊**: 識別可能缺失的重要資訊

請按此格式回應：
RELEVANCE_SCORE: [1-10分]
KEY_INFORMATION: [提取的關鍵資訊]
QUALITY_ASSESSMENT: [資訊品質評估]
MISSING_INFO: [可能缺失的資訊]
SUMMARY: [搜尋結果摘要]
"""


class RAGAgent:
    """
    RAG 搜尋代理，負責：
    1. 接收搜尋任務和查詢優化
    2. 使用 embedding 模型將查詢轉為向量
    3. 執行 Elasticsearch 向量搜尋
    4. 整理和分析搜尋結果
    5. 返回結構化的知識庫資料
    """
    
    def __init__(self, chat_service: ChatCompletionClientBase, name: str = "RAGAgent"):
        self.name = name
        self.chat_service = chat_service
        
        # 創建 ChatCompletionAgent
        self.agent = ChatCompletionAgent(
            name=self.name,
            description="RAG 搜尋代理，專注於知識庫檢索和相關文檔分析",
            instructions="""
你是一個專業的 RAG 搜尋代理。你的職責：

1. **查詢優化**: 將用戶查詢轉換為最適合向量搜尋的形式
2. **向量檢索**: 使用 embedding 模型執行語意搜尋
3. **結果分析**: 分析檢索結果的相關性和品質
4. **資料整理**: 將搜尋結果整理為結構化格式
5. **品質評估**: 評估檢索資訊的完整性和可靠性

**工作原則**：
- 專注於語意相關性而非關鍵字匹配
- 提供詳細的相關性評分和品質評估
- 保留原始資料來源和元數據
- 識別資訊缺口和建議補充查詢
""",
            service=chat_service,
            plugins=[RAGAgentPlugin()]
        )
        
        # RAG 相關組件（延遲初始化）
        self.embedding_provider = None
        self.elasticsearch_adapter = None
        self._initialized = False
        
        logger.info(f"🧠 {self.name} RAG 搜尋代理初始化完成")
    
    async def execute_rag_search(self, search_query: str, context: str = "", top_k: int = 5) -> Dict[str, Any]:
        """
        執行 RAG 搜尋的主要入口點
        
        Args:
            search_query: 搜尋查詢
            context: 背景資訊（可選）
            top_k: 返回結果數量
            
        Returns:
            {
                'success': bool,
                'query_used': str,
                'optimized_query': str,
                'embedding_vector': List[float],
                'search_results': List[Dict],
                'analyzed_results': Dict,
                'relevance_scores': List[float],
                'metadata': Dict,
                'timestamp': str,
                'error': str (if failed)
            }
        """
        try:
            logger.info(f"🧠 {self.name} 開始執行 RAG 搜尋任務")
            
            # 確保組件初始化
            await self._ensure_components_initialized()
            
            # 獲取當前時間
            from datetime import datetime
            timestamp = datetime.now().isoformat()
            
            # 第一步：優化查詢
            optimized_query = await self._optimize_search_query(search_query, context)
            logger.info(f"🎯 {self.name} 優化查詢: {optimized_query}")
            
            # 第二步：生成 embedding
            embedding_vector = await self._generate_embedding(optimized_query)
            logger.info(f"🔢 {self.name} 生成 embedding 向量，維度: {len(embedding_vector)}")
            
            # 第三步：執行向量搜尋
            search_results = await self._perform_vector_search(embedding_vector, top_k)
            logger.info(f"🔍 {self.name} 找到 {len(search_results)} 個相關結果")
            
            # 第四步：分析搜尋結果
            analyzed_results = await self._analyze_search_results(search_results, search_query)
            
            # 第五步：提取相關性評分
            relevance_scores = self._extract_relevance_scores(search_results)
            
            result = {
                'success': True,
                'query_used': search_query,
                'optimized_query': optimized_query,
                'embedding_vector': embedding_vector,
                'search_results': search_results,
                'analyzed_results': analyzed_results,
                'relevance_scores': relevance_scores,
                'metadata': {
                    'total_results': len(search_results),
                    'embedding_model': self._get_embedding_model_name(),
                    'elasticsearch_index': self.elasticsearch_adapter.index,
                    'search_params': {
                        'top_k': top_k,
                        'context_provided': bool(context)
                    }
                },
                'timestamp': timestamp
            }
            
            logger.info(f"✅ {self.name} RAG 搜尋完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ {self.name} RAG 搜尋失敗: {e}")
            return {
                'success': False,
                'error': str(e),
                'query_used': search_query,
                'optimized_query': '',
                'embedding_vector': [],
                'search_results': [],
                'analyzed_results': {},
                'relevance_scores': [],
                'metadata': {},
                'timestamp': timestamp if 'timestamp' in locals() else 'Unknown'
            }
    
    async def _ensure_components_initialized(self):
        """確保 embedding provider 和 ES adapter 已初始化"""
        if self._initialized:
            return
        
        try:
            # 初始化 embedding provider
            if self.embedding_provider is None:
                self.embedding_provider = get_default_provider()
                logger.info(f"🔤 {self.name} Embedding provider 已初始化")
            
            # 初始化 Elasticsearch adapter
            if self.elasticsearch_adapter is None:
                self.elasticsearch_adapter = ElasticsearchAdapter()
                await self.elasticsearch_adapter.ensure_index()
                logger.info(f"🗄️ {self.name} Elasticsearch adapter 已初始化")
            
            self._initialized = True
            logger.info(f"✅ {self.name} 所有組件初始化完成")
            
        except Exception as e:
            logger.error(f"❌ {self.name} 組件初始化失敗: {e}")
            raise
    
    async def _optimize_search_query(self, search_query: str, context: str) -> str:
        """優化搜尋查詢"""
        try:
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個 RAG 搜尋專家，需要優化查詢以獲得最相關的知識庫結果。

用戶查詢: {search_query}
背景資訊: {context}

請分析並提供：
1. **核心概念**: 提取查詢中的關鍵概念和實體
2. **搜尋關鍵字**: 最適合向量搜尋的關鍵字組合
3. **相關主題**: 可能相關的主題或概念
4. **查詢意圖**: 用戶想要獲得的資訊類型

請按此格式回應：
CORE_CONCEPTS: [核心概念1, 概念2, 概念3]
SEARCH_KEYWORDS: [優化後的搜尋關鍵字]
RELATED_TOPICS: [相關主題1, 主題2, 主題3]
QUERY_INTENT: [資訊檢索意圖說明]
SEARCH_STRATEGY: [向量搜尋策略]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service,
                    max_completion_tokens=500,
                    temperature=0.3
                )
            )
            
            if response and len(response) > 0:
                optimization_result = response[0].content
                return self._extract_search_keywords(optimization_result, search_query)
            else:
                logger.warning(f"⚠️ {self.name} 查詢優化回應為空，使用原始查詢")
                return search_query
                
        except Exception as e:
            logger.error(f"❌ {self.name} 查詢優化失敗: {e}")
            return search_query
    
    def _extract_search_keywords(self, optimization_result: str, fallback: str) -> str:
        """從優化結果中提取搜尋關鍵字"""
        try:
            lines = optimization_result.split('\n')
            for line in lines:
                if 'SEARCH_KEYWORDS:' in line:
                    keywords = line.split('SEARCH_KEYWORDS:')[1].strip()
                    if keywords and keywords != '[優化後的搜尋關鍵字]':
                        return keywords
            
            logger.warning(f"⚠️ {self.name} 無法提取優化關鍵字，使用原始查詢")
            return fallback
            
        except Exception as e:
            logger.error(f"❌ {self.name} 提取關鍵字失敗: {e}")
            return fallback
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """生成文本的 embedding 向量"""
        try:
            if not self.embedding_provider:
                raise RuntimeError("Embedding provider 未初始化")
            
            embedding = await self.embedding_provider.embed(text)
            
            if embedding:
                return embedding
            else:
                raise RuntimeError("Embedding 生成失敗：返回空結果")
                
        except Exception as e:
            logger.error(f"❌ {self.name} 生成 embedding 失敗: {e}")
            raise
    
    async def _perform_vector_search(self, embedding_vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        """執行向量搜尋"""
        try:
            if not self.elasticsearch_adapter:
                raise RuntimeError("Elasticsearch adapter 未初始化")
            
            search_results = await self.elasticsearch_adapter.search_by_vector(
                vector=embedding_vector, 
                k=top_k
            )
            
            # 轉換 ES 結果格式為標準格式
            formatted_results = []
            for hit in search_results:
                formatted_result = {
                    'id': hit.get('_id', ''),
                    'score': hit.get('_score', 0.0),
                    'source': hit.get('_source', {}),
                    'text': hit.get('_source', {}).get('text', ''),
                    'intent': hit.get('_source', {}).get('intent', ''),
                    'metadata': hit.get('_source', {}).get('metadata', {})
                }
                formatted_results.append(formatted_result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ {self.name} 向量搜尋失敗: {e}")
            raise
    
    async def _analyze_search_results(self, search_results: List[Dict], original_query: str) -> Dict[str, Any]:
        """分析搜尋結果"""
        try:
            if not search_results:
                return {
                    'relevance_score': 0,
                    'key_information': '未找到相關資訊',
                    'quality_assessment': '無搜尋結果',
                    'missing_info': '完全缺失相關資料',
                    'summary': '知識庫中未找到相關文檔'
                }
            
            # 準備結果文本用於分析
            results_text = self._format_results_for_analysis(search_results)
            
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個資訊分析專家，需要分析 RAG 搜尋結果並提取最相關的資訊。

原始查詢: {original_query}
搜尋結果: {results_text}

請進行以下分析：
1. **相關性評估**: 評估每個結果與查詢的相關性
2. **關鍵資訊提取**: 提取回答查詢所需的關鍵資訊
3. **資訊品質**: 評估資訊的可靠性和完整性
4. **缺失資訊**: 識別可能缺失的重要資訊

請按此格式回應：
RELEVANCE_SCORE: [1-10分]
KEY_INFORMATION: [提取的關鍵資訊]
QUALITY_ASSESSMENT: [資訊品質評估]
MISSING_INFO: [可能缺失的資訊]
SUMMARY: [搜尋結果摘要]
""")
            
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=smart_settings(
                    self.chat_service,
                    max_completion_tokens=800,
                    temperature=0.2
                )
            )
            
            if response and len(response) > 0:
                analysis_result = response[0].content
                return self._parse_analysis_result(analysis_result)
            else:
                logger.warning(f"⚠️ {self.name} 結果分析回應為空")
                return self._create_default_analysis(search_results)
                
        except Exception as e:
            logger.error(f"❌ {self.name} 結果分析失敗: {e}")
            return self._create_default_analysis(search_results)
    
    def _format_results_for_analysis(self, search_results: List[Dict]) -> str:
        """格式化搜尋結果用於分析"""
        formatted_results = []
        for i, result in enumerate(search_results[:5], 1):  # 只分析前5個結果
            formatted_result = f"""
結果 {i}:
- ID: {result.get('id', 'N/A')}
- 相關性分數: {result.get('score', 0.0):.4f}
- 文本內容: {result.get('text', '')[:200]}...
- 意圖標籤: {result.get('intent', 'N/A')}
- 元數據: {result.get('metadata', {})}
"""
            formatted_results.append(formatted_result)
        
        return '\n'.join(formatted_results)
    
    def _parse_analysis_result(self, analysis_text: str) -> Dict[str, Any]:
        """解析分析結果"""
        result = {
            'relevance_score': 5,
            'key_information': '',
            'quality_assessment': '',
            'missing_info': '',
            'summary': ''
        }
        
        try:
            lines = analysis_text.split('\n')
            for line in lines:
                line = line.strip()
                if 'RELEVANCE_SCORE:' in line:
                    score_text = line.split('RELEVANCE_SCORE:')[1].strip()
                    try:
                        result['relevance_score'] = int(score_text.split('/')[0].split('分')[0])
                    except:
                        pass
                elif 'KEY_INFORMATION:' in line:
                    result['key_information'] = line.split('KEY_INFORMATION:')[1].strip()
                elif 'QUALITY_ASSESSMENT:' in line:
                    result['quality_assessment'] = line.split('QUALITY_ASSESSMENT:')[1].strip()
                elif 'MISSING_INFO:' in line:
                    result['missing_info'] = line.split('MISSING_INFO:')[1].strip()
                elif 'SUMMARY:' in line:
                    result['summary'] = line.split('SUMMARY:')[1].strip()
            
        except Exception as e:
            logger.error(f"❌ {self.name} 解析分析結果失敗: {e}")
        
        return result
    
    def _create_default_analysis(self, search_results: List[Dict]) -> Dict[str, Any]:
        """創建預設分析結果"""
        if not search_results:
            return {
                'relevance_score': 0,
                'key_information': '未找到相關資訊',
                'quality_assessment': '無搜尋結果',
                'missing_info': '完全缺失相關資料',
                'summary': '知識庫中未找到相關文檔'
            }
        
        avg_score = sum(result.get('score', 0) for result in search_results) / len(search_results)
        
        return {
            'relevance_score': min(10, max(1, int(avg_score * 10))),
            'key_information': f"找到 {len(search_results)} 個相關文檔",
            'quality_assessment': f"平均相關性分數: {avg_score:.3f}",
            'missing_info': '需要進一步分析確定缺失資訊',
            'summary': f"從知識庫檢索到 {len(search_results)} 個相關文檔，平均相關性為 {avg_score:.3f}"
        }
    
    def _extract_relevance_scores(self, search_results: List[Dict]) -> List[float]:
        """提取相關性評分"""
        return [result.get('score', 0.0) for result in search_results]
    
    def _get_embedding_model_name(self) -> str:
        """獲取 embedding 模型名稱"""
        try:
            embeddings_config = config_manager.config.get('embeddings', {})
            return f"{embeddings_config.get('provider', 'unknown')}/{embeddings_config.get('model', 'unknown')}"
        except:
            return "unknown"
    
    async def test_rag_capability(self) -> bool:
        """測試 RAG 能力是否可用"""
        try:
            await self._ensure_components_initialized()
            
            # 測試查詢
            test_result = await self.execute_rag_search("測試查詢", top_k=1)
            return test_result['success']
            
        except Exception as e:
            logger.error(f"❌ {self.name} RAG 能力測試失敗: {e}")
            return False
    
    def get_agent(self) -> ChatCompletionAgent:
        """獲取底層的 ChatCompletionAgent"""
        return self.agent
    
    def get_name(self) -> str:
        """獲取代理名稱"""
        return self.name
    
    def is_available(self) -> bool:
        """檢查 RAG 代理是否可用"""
        return self._initialized and self.embedding_provider is not None and self.elasticsearch_adapter is not None
    
    async def cleanup(self):
        """清理資源"""
        try:
            if self.elasticsearch_adapter:
                # ES adapter 使用共享客戶端，不需要手動關閉
                pass
            
            if self.embedding_provider:
                # 如果 embedding provider 有清理方法，在這裡調用
                if hasattr(self.embedding_provider, 'cleanup'):
                    await self.embedding_provider.cleanup()
            
            self._initialized = False
            logger.info(f"🧹 {self.name} 資源清理完成")
            
        except Exception as e:
            logger.error(f"❌ {self.name} 清理失敗: {e}")
    
    async def __aenter__(self):
        """異步上下文管理器進入"""
        await self._ensure_components_initialized()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """異步上下文管理器退出"""
        await self.cleanup()
