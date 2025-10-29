import asyncio
import json
import logging
from types import SimpleNamespace
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from pathlib import Path
import sys

# Resilient import pattern so this script works when run both as a module
# (python -m lyrallm.tools.run_rag_test) and as a plain script
try:
    from lyrallm.agents.rag_agent import RAGAgent
except Exception:
    try:
        # try importing as a top-level package inside the repo
        from agents.rag_agent import RAGAgent
    except Exception:
        # add repo root to sys.path and retry
        repo_root = Path(__file__).resolve().parents[2]
        lyrallm_pkg = Path(__file__).resolve().parents[1]  # repo_root/lyrallm
        # ensure both repo root and the lyrallm package dir are on sys.path
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        if str(lyrallm_pkg) not in sys.path:
            sys.path.insert(0, str(lyrallm_pkg))
        from agents.rag_agent import RAGAgent

logging.basicConfig(level=logging.INFO)


class DummyChatService(ChatCompletionClientBase):
    """Minimal stub implementing ChatCompletionClientBase for testing.

    Provide minimal required model fields so pydantic validation succeeds.
    """
    # ChatCompletionClientBase is a pydantic model in semantic-kernel; set
    # a minimal required field so validation passes.
    ai_model_id: str = "test-model"

    async def get_chat_message_contents(self, chat_history=None, settings=None):
        # Return an object with a .content attribute as expected by the agent
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
