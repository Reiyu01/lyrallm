"""
MCP Server: Web Search

將現有的 OllamaWebSearchPlugin 以 MCP 工具形式暴露：
- tools.search(query: str, max_results: int = 5)
- tools.web_fetch(url: str)
- tools.get_search_status()

參考（MCP 實作範例）:
https://devblogs.microsoft.com/semantic-kernel/building-a-model-context-protocol-server-with-semantic-kernel/

注意：此伺服器以 stdio 方式啟動，供 MCP Client 子程序連線使用。
以模組方式啟動時，請確保工作目錄在專案根目錄或已將專案根加入 PYTHONPATH：
    python3 -m lyrallm.mcp.web_search_mcp_server
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    # 官方 MCP Python 套件（Anthropic 提供）- 使用 FastMCP
    from mcp.server import FastMCP  # type: ignore
    from mcp.server.stdio import stdio_server  # type: ignore
except Exception as e:  # pragma: no cover - 若未安裝 mcp 套件
    FastMCP = None  # type: ignore
    stdio_server = None  # type: ignore
    logger.error(f"MCP 套件未安裝或無法載入: {e}")


# 延用現有的 Plugin 實作
try:
    from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin
except Exception as e:
    # 若以絕對路徑執行，嘗試將專案根加入 sys.path 以便匯入 plugins
    try:
        # MCP server 在 lyrallm/mcp/ 中，需要回到 lyrallm/ 根目錄
        project_root = Path(__file__).resolve().parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin  # type: ignore
    except Exception as e2:
        OllamaWebSearchPlugin = None  # type: ignore
        logger.error(f"無法載入 OllamaWebSearchPlugin：{e} / fallback: {e2}")
        logger.error(f"嘗試的路徑: {Path(__file__).resolve().parent.parent}")
        logger.error(f"sys.path: {sys.path[:3]}...")  # 只顯示前3個路徑


def _ensure_plugin() -> OllamaWebSearchPlugin:
    if OllamaWebSearchPlugin is None:
        raise RuntimeError("OllamaWebSearchPlugin 未可用。請確認套件與環境變數設定。")
    return OllamaWebSearchPlugin()


def create_server() -> "FastMCP":
    if FastMCP is None:
        raise RuntimeError("MCP Server 初始化失敗：未安裝 mcp 套件。請先安裝 'mcp'。")

    server = FastMCP("web-search-mcp")
    plugin = _ensure_plugin()

    @server.tool()
    async def search(query: str, max_results: int = 5) -> str:
        """使用 Ollama Web Search 進行網路搜尋，回傳 JSON 字串。"""
        try:
            return await plugin.search(query=query, max_results=max_results)  # type: ignore
        except Exception as e:
            logger.error(f"[MCP] search 失敗: {e}")
            return json.dumps({"error": f"search failed: {str(e)}"}, ensure_ascii=False)

    @server.tool()
    async def web_fetch(url: str) -> str:
        """抓取指定 URL 的內容，回傳 JSON 字串。"""
        try:
            return await plugin.web_fetch(url=url)  # type: ignore
        except Exception as e:
            logger.error(f"[MCP] web_fetch 失敗: {e}")
            return json.dumps({"error": f"web_fetch failed: {str(e)}"}, ensure_ascii=False)

    @server.tool()
    async def get_search_status() -> str:
        """回傳服務狀態 JSON 字串。"""
        try:
            # 若 plugin 內部提供了狀態查詢，直接呼叫
            if hasattr(plugin, "get_search_status"):
                return await plugin.get_search_status()  # type: ignore
            # 否則回傳基本狀態
            return json.dumps({
                "service": "Ollama Web Search",
                "status": "unknown",
                "message": "Plugin does not implement get_search_status"
            }, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[MCP] get_search_status 失敗: {e}")
            return json.dumps({"error": f"status failed: {str(e)}"}, ensure_ascii=False)

    @server.tool()
    async def get_current_time(format: str = "iso") -> str:
        """
        取得目前時間
        
        Args:
            format: 時間格式，可選值：
                   - "iso": ISO 8601 格式 (預設)
                   - "readable": 可讀格式
                   - "timestamp": Unix 時間戳
        """
        try:
            now = datetime.now()
            
            if format == "iso":
                time_str = now.isoformat()
            elif format == "readable":
                time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
            elif format == "timestamp":
                time_str = str(int(now.timestamp()))
            else:
                # 預設使用 ISO 格式
                time_str = now.isoformat()
            
            return json.dumps({
                "current_time": time_str,
                "timezone": "local",
                "format": format
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"[MCP] get_current_time 失敗: {e}")
            return json.dumps({"error": f"get_current_time failed: {str(e)}"}, ensure_ascii=False)

    return server


async def main():
    server = create_server()
    
    # 使用 FastMCP 的 stdio 運行方式
    await server.run_stdio_async()


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
