import asyncio
import json
import logging
from types import SimpleNamespace
from pathlib import Path
import sys

# Resilient import pattern so this script works both as a module
# (python -m lyrallm.tools.run_rag_test) and as a plain script
try:
    from lyrallm.agents.rag_agent import RAGAgent
except Exception:
    try:
        from agents.rag_agent import RAGAgent
    except Exception:
        repo_root = Path(__file__).resolve().parents[2]
        lyrallm_pkg = Path(__file__).resolve().parents[1]  # repo_root/lyrallm
        # ensure both repo root and the lyrallm package dir are on sys.path
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        if str(lyrallm_pkg) not in sys.path:
            sys.path.insert(0, str(lyrallm_pkg))
        from agents.rag_agent import RAGAgent

# Attempt to disable RagGraphAdapter for this test run so the agent uses the vector search path
try:
    import importlib
    try:
        rag_mod = importlib.import_module('lyrallm.agents.rag_agent')
    except Exception:
        rag_mod = importlib.import_module('agents.rag_agent')
    setattr(rag_mod, 'RagGraphAdapter', None)
    logging.info('Disabled RagGraphAdapter for this test run to force vector search')
except Exception:
    logging.info('Could not disable RagGraphAdapter; proceeding with default agent behavior')

logging.basicConfig(level=logging.INFO)


# Try to import the ChatCompletionClientBase used by the agent's pydantic model.
# If it's not available, fall back to a tiny base class so our stub still works.
try:
    from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
except Exception:
    class ChatCompletionClientBase:  # type: ignore
        pass


class DummyChatService(ChatCompletionClientBase):
    """Stub that mimics the minimal surface the agent expects.

    Subclassing `ChatCompletionClientBase` (when available) satisfies pydantic
    validation performed by the agent framework.
    """
    ai_model_id: str = "test-model"

    async def get_chat_message_contents(self, chat_history=None, settings=None):
        return [SimpleNamespace(content="OPTIMIZED_QUERY: test optimized query")]


async def main():
    chat_service = DummyChatService()
    agent = RAGAgent(chat_service=chat_service, name="run_rag_test")

    # Run a RAG search that uses Elasticsearch (use_graph=False)
    try:
        result = await agent.execute_rag_search(
            search_query="示例查詢: 測試向量搜尋",
            context="",
            top_k=3,
            use_graph=False,
            user_role=None,
        )

        # Ensure the result is JSON serializable for printing
        def _safe(o):
            try:
                json.dumps(o)
                return o
            except Exception:
                return repr(o)

        safe_result = json.loads(json.dumps(result, default=lambda o: _safe(o)))
        print(json.dumps(safe_result, indent=2, ensure_ascii=False))

    except Exception as e:
        logging.exception("run_rag_test failed")


if __name__ == '__main__':
    asyncio.run(main())
