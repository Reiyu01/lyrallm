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
from .rate_limiter import safe_chat_completion

# 導入 embedding 和 ES 相關模組
from config.config_manager import config_manager
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
    def _ensure_neo4j_driver(self):
        if hasattr(self, 'neo4j_driver') and self.neo4j_driver is not None:
            return
        import os
        from neo4j import GraphDatabase, basic_auth
        uri = os.getenv("NEO4J_URI", "bolt://163.18.26.233:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "secretgraph")
        self.neo4j_driver = GraphDatabase.driver(uri, auth=basic_auth(username, password))
        logger.info(f"[RAGAgent] Neo4j driver 已初始化: {uri}")

    def fetch_graph_facts(self, node_ids):
        self._ensure_neo4j_driver()
        filtered_ids = [node_id for node_id in node_ids if node_id]
        if not filtered_ids:
            logger.info("未提供節點 ID，略過圖譜查詢")
            return []
        with self.neo4j_driver.session() as session:
            nodes = session.run(
                "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id, labels(n) AS labels, properties(n) AS props",
                ids=filtered_ids,
            ).data()
            relationships = session.run(
                "MATCH (n)-[r]->(m) WHERE n.id IN $ids RETURN n.id AS start_id, type(r) AS type, m.id AS end_id, properties(r) AS props",
                ids=filtered_ids,
            ).data()
        rel_map = {}
        for rel in relationships:
            rel_map.setdefault(rel["start_id"], []).append({
                "type": rel["type"],
                "target": rel["end_id"],
                "properties": rel["props"],
            })
        graph_facts = []
        for node in nodes:
            graph_facts.append({
                "node_id": node["id"],
                "label": ":".join(node["labels"]),
                "properties": node["props"],
                "relationships": rel_map.get(node["id"], []),
            })
        logger.info(f"取得 {len(graph_facts)} 個圖譜節點")
        return graph_facts
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
    
    async def execute_rag_search(self, search_query: str, context: str = "", top_k: int = 5, node_ids: list = None, use_graph: bool = True, user_role: Optional[str] = None) -> Dict[str, Any]:
        """
        執行 RAG 搜尋的主要入口點
        Args:
            search_query: 搜尋查詢
            context: 背景資訊（可選）
            top_k: 返回結果數量
            node_ids: (list) 若指定則查詢 Neo4j 圖譜
            use_graph: (bool) 若 True 則強制查詢 Neo4j
        Returns:
            dict: 查詢結果，包含 success, query_used, optimized_query, embedding_vector, search_results, analyzed_results, relevance_scores, metadata, timestamp, error 等欄位。
        """
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        try:
            logger.info(f"🧠 {self.name} 開始執行 RAG 搜尋任務")
            # 若指定 node_ids 或 use_graph，則查詢 Neo4j
            if use_graph or (node_ids is not None and len(node_ids) > 0):
                if node_ids is not None and len(node_ids) > 0:
                    graph_facts = self.fetch_graph_facts(node_ids or [])
                else:
                    # 若沒有指定 node_ids，但前端要求使用圖譜，則以文字查詢圖譜
                    graph_facts = await self._search_graph_by_text(search_query, top_k, user_role=user_role)
                result = {
                    'success': True,
                    'query_used': search_query,
                    'optimized_query': '',
                    'embedding_vector': [],
                    'search_results': graph_facts,
                    'analyzed_results': {},
                    'relevance_scores': [],
                    'metadata': {
                        'source': 'neo4j',
                        'total_results': len(graph_facts),
                        'node_ids': node_ids,
                        'user_role': user_role,
                    },
                    'timestamp': timestamp
                }
                logger.info(f"✅ {self.name} Neo4j 圖譜查詢完成")
                return result
            # 否則預設走 ES 向量搜尋
            await self._ensure_components_initialized()
            optimized_query = await self._optimize_search_query(search_query, context)
            logger.info(f"🎯 {self.name} 優化查詢: {optimized_query}")
            embedding_vector = await self._generate_embedding(optimized_query)
            logger.info(f"🔢 {self.name} 生成 embedding 向量，維度: {len(embedding_vector)}")
            search_results = await self._perform_vector_search(embedding_vector, top_k)
            logger.info(f"🔍 {self.name} 找到 {len(search_results)} 個相關結果")
            analyzed_results = await self._analyze_search_results(search_results, search_query)
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
                'timestamp': timestamp
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
        except Exception as e:
            logger.error(f"❌ {self.name} 組件初始化失敗: {e}")
            raise

    async def _optimize_search_query(self, search_query: str, context: str = "") -> str:
        """使用 chat service 對查詢進行優化，返回優化後的查詢字串。

        嘗試呼叫語言模型以產生一個適合向量搜尋的簡潔查詢（或關鍵字序列）。
        若優化失敗或回應不可解析，會 fallback 回原始 search_query。
        """
        try:
            chat_history = ChatHistory()
            chat_history.add_user_message(f"""
你是一個 RAG 搜尋優化器，請將用戶查詢轉換為最適合向量搜尋的查詢或關鍵字序列。

用戶查詢: {search_query}
背景資訊: {context}

請回傳一個標籤行：OPTIMIZED_QUERY: <優化後的查詢或關鍵字>
如果無法優化，請回傳 OPTIMIZED_QUERY: <原始查詢>
""")

            response = await safe_chat_completion(
                self.chat_service,
                chat_history,
                smart_settings(self.chat_service, max_completion_tokens=200, temperature=0.0)
            )

            if response and len(response) > 0:
                text = response[0].content or ""
                # 嘗試解析 OPTIMIZED_QUERY 標籤
                for line in text.splitlines():
                    if 'OPTIMIZED_QUERY:' in line:
                        return line.split('OPTIMIZED_QUERY:')[1].strip()
                # 嘗試解析 SEARCH_KEYWORDS
                for line in text.splitlines():
                    if 'SEARCH_KEYWORDS:' in line:
                        return line.split('SEARCH_KEYWORDS:')[1].strip()
                # 否則回傳整段文字作為優化結果
                return text.strip()

        except Exception as e:
            logger.warning(f"⚠️ {self.name} 查詢優化失敗，使用原始查詢: {e}")

        return search_query

    async def _search_graph_by_text(self, text_query: str, top_k: int = 5, user_role: Optional[str] = None) -> List[Dict[str, Any]]:
        """在 Neo4j 中以文字搜尋節點。

        此方法會嘗試搜尋節點的各個字串屬性（不使用全文索引時的 fallback），
        並回傳與節點相關的結構化資訊（properties, labels, relationships）。
        若 Neo4j 未設定或查詢失敗，回傳空列表。
        """
        try:
            self._ensure_neo4j_driver()
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 無法初始化 Neo4j driver: {e}")
            return []

        # 根據查詢內容決定查詢策略：
        # - 如果查詢與權限 (permission/權限/role) 相關，優先搜尋 Permission 標籤的節點或常用欄位
        # - 否則使用較寬鬆的屬性包含檢查作為 fallback
        q_lower = (text_query or "").lower()

        # 若傳入 user_role，先檢查該角色是否允許使用 rag_search（防止前端傳入身分但無權限存取圖譜）
        try:
            if user_role:
                role_cfg = config_manager.get_role_config(user_role)
                if role_cfg is None:
                    logger.warning(f"⚠️ {self.name} 未找到角色設定: {user_role}，拒絕圖譜查詢")
                    return []
                flags = [f.lower() for f in role_cfg.get('feature_flags', []) or []]
                # 支援多種命名（rag_search / use:rag_search / web_search）以兼容現有 config
                if 'rag_search' not in flags and 'web_search' not in flags and 'use:rag_search' not in flags:
                    logger.info(f"🔒 {self.name} 角色 '{user_role}' 未啟用 rag_search 功能，拒絕圖譜查詢")
                    return []
        except Exception as e:
            logger.warning(f"⚠️ {self.name} 檢查角色許可時發生錯誤: {e}")

        # 建立權限/角色關鍵字清單，優先使用 config.yaml 中定義的 role 名稱與 permission
        permission_keywords = ['權限', 'permission', 'role', '角色']
        try:
            roles_conf = config_manager.get_roles_config() or {}
            # 角色名稱（如 admin, security_officer 等）
            role_names = [r.lower() for r in roles_conf.keys()]
            # 權限字串（如 manage:roles, view:audit_logs 等）
            perm_values = []
            for r in roles_conf.values():
                for p in r.get('permissions', []) or []:
                    if isinstance(p, str):
                        perm_values.append(p.lower())
            permission_keywords.extend(role_names)
            permission_keywords.extend(perm_values)
        except Exception:
            # 若讀取配置失敗，保留基本關鍵字
            role_names = []

        # 如果查詢看起來與權限或角色相關，優先搜尋 Permission/Role 節點與常見欄位
        if any(k in q_lower for k in permission_keywords if k):
            cypher = (
                "MATCH (n) WHERE ( 'Permission' IN labels(n) OR 'Role' IN labels(n) "
                "OR toLower(coalesce(n.role, '')) <> '' OR toLower(coalesce(n.name, '')) <> '') AND ("
                "toLower(coalesce(n.name, '')) CONTAINS toLower($q) "
                "OR toLower(coalesce(n.role, '')) CONTAINS toLower($q) "
                "OR toLower(coalesce(n.description, '')) CONTAINS toLower($q) ) "
                "RETURN n.id AS id, labels(n) AS labels, properties(n) AS props LIMIT $limit"
            )
        else:
            # 通用 fallback（更安全）：只搜尋常見的字串屬性，並安全處理陣列屬性
            # 設定要搜尋的字串欄位（可按需擴充）
            string_props = ['name','title','description','content','role','visibility','summary']
            prop_checks = [f"toLower(coalesce(n.{p}, '')) CONTAINS toLower($q)" for p in string_props]

            # 對於可能為陣列的欄位，使用 any(...) 逐項比較（避免直接對整個陣列呼叫 toString())
            # Neo4j 4.x+ 已廢棄 exists(variable.property) 語法，改用 `variable.property IS NOT NULL`
            list_checks = [
                "(n.allowed_roles IS NOT NULL AND any(x IN n.allowed_roles WHERE toLower(toString(x)) CONTAINS toLower($q)))",
                "(n.effective_allowed_roles IS NOT NULL AND any(x IN n.effective_allowed_roles WHERE toLower(toString(x)) CONTAINS toLower($q)))",
                "(n.restricted_roles IS NOT NULL AND any(x IN n.restricted_roles WHERE toLower(toString(x)) CONTAINS toLower($q)))"
            ]

            where_clause = " OR ".join(prop_checks + list_checks)
            cypher = (
                "MATCH (n) WHERE " + where_clause + " RETURN n.id AS id, labels(n) AS labels, properties(n) AS props LIMIT $limit"
            )

        results = []
        try:
            with self.neo4j_driver.session() as session:
                records = session.run(cypher, q=text_query, limit=top_k).data()
            if not records:
                return []

            # 為每個節點抓取關係（最多 top_k 節點）
            node_ids = [r['id'] for r in records if r.get('id')]
            rels = []
            if node_ids:
                with self.neo4j_driver.session() as session:
                    rels = session.run(
                        "MATCH (n)-[r]->(m) WHERE n.id IN $ids RETURN n.id AS start_id, type(r) AS type, m.id AS end_id, properties(r) AS props",
                        ids=node_ids
                    ).data()

            rel_map = {}
            for rel in rels:
                rel_map.setdefault(rel['start_id'], []).append({
                    'type': rel['type'],
                    'target': rel['end_id'],
                    'properties': rel.get('props', {})
                })

            for rec in records:
                nid = rec.get('id')
                results.append({
                    'node_id': nid,
                    'label': ':'.join(rec.get('labels', [])),
                    'properties': rec.get('props', {}),
                    'relationships': rel_map.get(nid, [])
                })

            # 若前端提供了 user_role，根據常見欄位做 RBAC 過濾（參考 rag_graph 範例）
            if user_role:
                filtered: list[Dict[str, Any]] = []
                ur = str(user_role).lower()
                for node in results:
                    props = node.get('properties') or {}
                    # 常見欄位名稱：allowed_roles / effective_allowed_roles /restricted_roles / visibility
                    allowed = []
                    restricted = []
                    # 支援多種存放格式：字串、list、JSON 字串
                    def _normalize_roles(value):
                        if value is None:
                            return []
                        if isinstance(value, str):
                            try:
                                # 可能是 JSON 陣列字串
                                parsed = json.loads(value)
                                if isinstance(parsed, list):
                                    return [str(x).lower() for x in parsed]
                            except Exception:
                                # 逗號分隔或單一字串
                                return [s.strip().lower() for s in value.split(',') if s.strip()]
                        if isinstance(value, (list, tuple, set)):
                            return [str(x).lower() for x in value]
                        return [str(value).lower()]

                    for k in ('effective_allowed_roles', 'allowed_roles', 'allowed', 'visible_to'):
                        if k in props:
                            allowed.extend(_normalize_roles(props.get(k)))

                    for k in ('restricted_roles', 'restricted', 'blocked_roles'):
                        if k in props:
                            restricted.extend(_normalize_roles(props.get(k)))

                    # visibility 處理（例如 'public' / 'private'）
                    visibility = str(props.get('visibility', '')).lower()

                    # 判斷邏輯：若在 restricted 則排除；若 allowed 非空則必須在 allowed 內；若 allowed 為空且 visibility=='private' 並且非 admin，則排除
                    if ur in restricted:
                        continue

                    if allowed:
                        if ur not in allowed:
                            continue
                    else:
                        if visibility == 'private' and ur != 'admin':
                            # 非 admin 無法看到 private 節點
                            continue

                    # 針對關係也做相同過濾（若關係上標註了 allowed/restricted）
                    rels = []
                    for r in node.get('relationships', []):
                        rprops = r.get('properties', {}) or {}
                        r_allowed = []
                        r_restricted = []
                        for k in ('allowed_roles', 'effective_allowed_roles', 'allowed'):
                            if k in rprops:
                                r_allowed.extend(_normalize_roles(rprops.get(k)))
                        for k in ('restricted_roles', 'restricted'):
                            if k in rprops:
                                r_restricted.extend(_normalize_roles(rprops.get(k)))

                        if ur in r_restricted:
                            # skip this relationship
                            continue
                        if r_allowed and ur not in r_allowed:
                            continue
                        rels.append(r)

                    node['relationships'] = rels
                    filtered.append(node)

                results = filtered

            logger.info(f"🔎 {self.name} 在圖譜中找到 {len(results)} 個節點與查詢: {text_query}")
            return results

        except Exception as e:
            logger.error(f"❌ {self.name} 圖譜文字搜尋失敗: {e}")
            return []
    
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
            
            response = await safe_chat_completion(
                self.chat_service,
                chat_history,
                smart_settings(
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