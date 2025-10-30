"""Compatibility adapter to reuse the rag_graph Retriever implementation.

This adapter wraps the sync `rag_graph` retriever so the async RAGAgent can
call it via threads. It constructs a sync Elasticsearch client and a
Neo4j driver based on the same config_manager settings used elsewhere.
"""
from typing import List, Dict, Any, Iterable, Optional
import logging
import sys
from pathlib import Path

from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


def _ensure_rag_graph_importable():
    """確保 rag_graph/sk_app/retriever 可以被 import。"""
    repo_root = Path(__file__).resolve().parents[2]
    rag_graph_pkg = repo_root / "rag_graph" / "LyraDatabase" / "neo4j"
    if str(rag_graph_pkg) not in sys.path:
        sys.path.insert(0, str(rag_graph_pkg))


class RagGraphAdapter:
    """Adapter that delegates to rag_graph.sk_app.retriever.Retriever (sync)."""

    def __init__(
        self,
        es_client_sync=None,
        neo4j_driver=None,
        index_name: Optional[str] = None,
        top_k: int = 3,
    ):
        _ensure_rag_graph_importable()

        # === 嘗試載入 retriever ===
        try:
            from sk_app.retriever import Retriever
        except Exception as e:
            logger.warning("無法透過包名匯入 sk_app.retriever: %s；嘗試從檔案路徑載入。", e)
            try:
                import importlib.util
                repo_root = Path(__file__).resolve().parents[2]
                retriever_file = (
                    repo_root / "rag_graph" / "LyraDatabase" / "neo4j" / "sk_app" / "retriever.py"
                )
                spec = importlib.util.spec_from_file_location("sk_app.retriever", str(retriever_file))
                mod = importlib.util.module_from_spec(spec)
                loader = spec.loader
                assert loader is not None
                loader.exec_module(mod)
                Retriever = getattr(mod, "Retriever")
            except Exception as ex2:
                logger.error("無法導入 rag_graph Retriever（fallback 失敗）: %s", ex2)
                raise

        # === 構建 Elasticsearch client ===
        if es_client_sync is None:
            try:
                from elasticsearch import Elasticsearch
            except Exception as e:
                logger.error("elasticsearch package is required for RagGraphAdapter: %s", e)
                raise

            es_cfg = config_manager.config.get("vectordb") or {}
            endpoint = es_cfg.get("endpoint", "http://127.0.0.1:9200")
            username = es_cfg.get("username")
            password = es_cfg.get("password")
            auth = (username, password) if username and password else None
            es_client_sync = Elasticsearch(
                hosts=[endpoint], basic_auth=auth, verify_certs=False
            )

        # === 構建 Neo4j driver ===
        if neo4j_driver is None:
            try:
                from lyrallm.graph.neo4j_client import get_neo4j_driver
                neo4j_driver = get_neo4j_driver()
            except Exception:
                pass
            if neo4j_driver is None:
                try:
                    from src.neo4j_client import create_driver as rg_create_driver
                    neo4j_driver = rg_create_driver()
                except Exception:
                    from neo4j import GraphDatabase, basic_auth
                    import os
                    uri = os.getenv("NEO4J_URI", "bolt://163.18.26.233:7687")
                    username = os.getenv("NEO4J_USERNAME", "neo4j")
                    password = os.getenv("NEO4J_PASSWORD", "secretgraph")
                    neo4j_driver = GraphDatabase.driver(uri, auth=basic_auth(username, password))

        self.top_k = top_k
        self.index_name = (
            index_name
            or (config_manager.config.get("vectordb") or {}).get("index")
            or "knowledge_documents"
        )

        # === 初始化 Retriever ===
        self.retriever = Retriever(
            es_client=es_client_sync,
            neo4j_driver=neo4j_driver,
            embedding_model="unused",
            top_k=self.top_k,
            index_name=self.index_name,
        )

    # === 包裝成 RAGAgent 可使用的格式 ===
    def search_documents(self, question: str) -> List[Dict[str, Any]]:
        """呼叫 rag_graph 的 search_documents 並轉成標準字典格式。"""
        docs = self.retriever.search_documents(question)
        out = []
        for d in docs:
            out.append(
                {
                    "id": d.doc_id,
                    "score": d.score,
                    "source": {
                        "title": d.title,
                        "text": d.body,
                        "document_type": d.document_type,
                        "visibility": d.visibility,
                        "allowed_roles": d.allowed_roles,
                        "restricted_roles": d.restricted_roles,
                    },
                    "related_nodes": d.related_nodes,
                }
            )
        return out

    def fetch_graph_facts(self, node_ids: Iterable[str]) -> List[Dict[str, Any]]:
        """呼叫 rag_graph 的 fetch_graph_facts 並轉換輸出結構。"""
        facts = self.retriever.fetch_graph_facts(node_ids)
        out = []
        for f in facts:
            out.append(
                {
                    "node_id": f.node_id,
                    "label": f.label,
                    "properties": f.properties,
                    "relationships": f.relationships,
                }
            )
        return out


# """Compatibility adapter to reuse the rag_graph Retriever implementation.

# This adapter wraps the sync `rag_graph` retriever so the async RAGAgent can
# call it via threads. It constructs a sync Elasticsearch client and a
# Neo4j driver based on the same config_manager settings used elsewhere.
# """
# from typing import List, Dict, Any, Iterable, Optional
# import logging
# import sys
# from pathlib import Path

# from lyrallm.config.config_manager import config_manager

# logger = logging.getLogger(__name__)


# def _ensure_rag_graph_importable():
#     # rag_graph lives under rag_graph/LyraDatabase/neo4j; ensure its package dir is on sys.path
#     repo_root = Path(__file__).resolve().parents[2]
#     # the retriever package lives under rag_graph/LyraDatabase/neo4j/sk_app
#     rag_graph_pkg = repo_root / 'rag_graph' / 'LyraDatabase' / 'neo4j'
#     if str(rag_graph_pkg) not in sys.path:
#         sys.path.insert(0, str(rag_graph_pkg))


# class RagGraphAdapter:
#     """Adapter that delegates to rag_graph.sk_app.retriever.Retriever (sync)."""

#     def __init__(self, es_client_sync=None, neo4j_driver=None, index_name: Optional[str] = None, top_k: int = 3):
#         _ensure_rag_graph_importable()
#             try:
#                 from sk_app.retriever import Retriever
#             except Exception as e:
#                 logger.warning("无法透過包名匯入 sk_app.retriever: %s；嘗試從檔案路徑載入。", e)
#                 # fallback: load retriever.py by path to be robust to package layout
#                 try:
#                     import importlib.util
#                     repo_root = Path(__file__).resolve().parents[2]
#                     retriever_file = repo_root / 'rag_graph' / 'LyraDatabase' / 'neo4j' / 'sk_app' / 'retriever.py'
#                     spec = importlib.util.spec_from_file_location('sk_app.retriever', str(retriever_file))
#                     mod = importlib.util.module_from_spec(spec)
#                     loader = spec.loader
#                     assert loader is not None
#                     loader.exec_module(mod)
#                     Retriever = getattr(mod, 'Retriever')
#                 except Exception as ex2:
#                     logger.error("无法导入 rag_graph Retriever（fallback 失敗）: %s", ex2)
#                     raise

#         # Build or reuse ES sync client and neo4j driver if provided; rag_graph expects sync clients
#         if es_client_sync is None:
#             # lazy import to avoid hard dependency at module import time
#             try:
#                 from elasticsearch import Elasticsearch
#             except Exception as e:
#                 logger.error("elasticsearch package is required for RagGraphAdapter: %s", e)
#                 raise
#             es_cfg = config_manager.config.get('vectordb') or {}
#             endpoint = es_cfg.get('endpoint') or 'http://127.0.0.1:9200'
#             username = es_cfg.get('username')
#             password = es_cfg.get('password')
#             auth = (username, password) if username and password else None
#             es_client_sync = Elasticsearch(hosts=[endpoint], basic_auth=auth, verify_certs=False)

#         if neo4j_driver is None:
#             # First, try project's shared client that reads from config/env
#             try:
#                 from lyrallm.graph.neo4j_client import get_neo4j_driver
#                 neo4j_driver = get_neo4j_driver()
#             except Exception:
#                 pass
#             # use the project's neo4j simple loader if available
#             try:
#                 from src.neo4j_client import create_driver as rg_create_driver
#                 neo4j_driver = rg_create_driver()
#             except Exception:
#                 # fallback to constructing from env via neo4j package
#                 try:
#                     from neo4j import GraphDatabase, basic_auth
#                     import os
#                     uri = os.getenv('NEO4J_URI', 'bolt://163.18.26.233:7687')
#                     username = os.getenv('NEO4J_USERNAME', 'neo4j')
#                     password = os.getenv('NEO4J_PASSWORD', 'secretgraph')
#                     neo4j_driver = GraphDatabase.driver(uri, auth=basic_auth(username, password))
#                 except Exception as e:
#                     logger.error("无法创建 Neo4j driver for RagGraphAdapter: %s", e)
#                     raise

#         self.top_k = top_k
#         self.index_name = index_name or (config_manager.config.get('vectordb') or {}).get('index') or 'knowledge_documents'
#         # instantiate Retriever
#         self.retriever = Retriever(es_client=es_client_sync, neo4j_driver=neo4j_driver, embedding_model='unused', top_k=self.top_k, index_name=self.index_name)

#     def search_documents(self, question: str) -> List[Dict[str, Any]]:
#         """Run rag_graph's search_documents and return a list of dicts compatible with RAGAgent."""
#         docs = self.retriever.search_documents(question)
#         # convert RetrievedDocument dataclass -> dict shape expected by RAGAgent
#         out = []
#         for d in docs:
#             out.append({
#                 'id': d.doc_id,
#                 'score': d.score,
#                 'source': {
#                     'title': d.title,
#                     'text': d.body,
#                     'document_type': d.document_type,
#                     'visibility': d.visibility,
#                     'allowed_roles': d.allowed_roles,
#                     'restricted_roles': d.restricted_roles,
#                 },
#                 'related_nodes': d.related_nodes,
#             })
#         return out

#     def fetch_graph_facts(self, node_ids: Iterable[str]) -> List[Dict[str, Any]]:
#         facts = self.retriever.fetch_graph_facts(node_ids)
#         # GraphFact dataclass -> dict
#         out = []
#         for f in facts:
#             out.append({
#                 'node_id': f.node_id,
#                 'label': f.label,
#                 'properties': f.properties,
#                 'relationships': f.relationships,
#             })
#         return out
