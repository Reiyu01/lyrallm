"""
MCP Client: Web Search

提供簡單的 Python 介面以呼叫 MCP 工具：
- search(query, max_results)
- web_fetch(url)
- get_search_status()

用法：
    client = WebSearchMCPClient(cmd=["python", "-m", "lyrallm.mcp.web_search_mcp_server"])
    await client.start()
    result = await client.search("Azure OpenAI 定價")
    await client.stop()

此 Client 會以子程序啟動 MCP Server（stdio transport）。
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    # SK MCP Session 介面
    from semantic_kernel.connectors.mcp.mcp_client import IMcpClient  # type: ignore
except Exception:
    try:
        # 後備：直接嘗試 mcp SDK Session
        from mcp.client.session import Session  # type: ignore
    except Exception as e:  # pragma: no cover
        Session = None  # type: ignore
        logger.error(f"MCP Session 未安裝或無法載入: {e}")

try:
    # Semantic Kernel 1.37.0 的 MCP 支援
    from semantic_kernel.connectors.mcp import MCPStdioPlugin
    from semantic_kernel import Kernel
    mcp_available = True
except Exception as e:  # pragma: no cover
    MCPStdioPlugin = None  # type: ignore
    Kernel = None  # type: ignore
    mcp_available = False
    logger.error(f"SK MCP 連接器未安裝或無法載入: {e}")


class WebSearchMCPClient:
    def __init__(self, cmd: Optional[List[str]] = None):
        # 預設使用目前執行本程式的 Python 解譯器，避免 python/python3 差異
        try:
            from pathlib import Path
            server_path = Path(__file__).with_name("web_search_mcp_server.py").resolve()
            default_cmd = [sys.executable or "python3", str(server_path)]
        except Exception:
            # 後備：仍嘗試模組方式
            default_cmd = [sys.executable or "python3", "-m", "lyrallm.mcp.web_search_mcp_server"]
        self.cmd = cmd or default_cmd
        self._kernel: Optional['Kernel'] = None
        self._mcp_plugin: Optional['MCPStdioPlugin'] = None
        self._plugin_context = None

    async def start(self) -> None:
        """啟動 MCP 客戶端連線"""
        if not mcp_available or MCPStdioPlugin is None:
            raise RuntimeError("SK MCP 連接器未安裝")
        
        if self._mcp_plugin:
            logger.info("MCP 客戶端已經在運行中")
            return
        
        try:
            command = self.cmd[0]
            args = self.cmd[1:] if len(self.cmd) > 1 else []
            logger.info(f"啟動 MCP server: command='{command}' args={args}")
            
            # 建立 Kernel
            self._kernel = Kernel()
            
            # 使用官方推薦的 async with 方式
            self._plugin_context = MCPStdioPlugin(
                name="WebSearchMCP",
                command=command,
                args=args,
                description="WebSearch MCP Server providing search, web_fetch, and get_search_status tools",
                load_tools=True,
                load_prompts=False,  # 我們不需要 prompts
                request_timeout=30  # 30秒超時
            )
            
            # 進入異步上下文
            self._mcp_plugin = await self._plugin_context.__aenter__()
            
            # 將 MCP Plugin 加入 Kernel
            self._kernel.add_plugin(self._mcp_plugin, plugin_name="WebSearchMCP")
            
            # 等待一下讓工具載入完成
            import asyncio
            await asyncio.sleep(0.5)
            
            # 檢查工具是否成功載入
            plugins = self._kernel.plugins
            if "WebSearchMCP" in plugins:
                plugin = plugins["WebSearchMCP"]
                if hasattr(plugin, 'functions'):
                    function_count = len(plugin.functions)
                    logger.info(f"成功載入 {function_count} 個 MCP 工具")
                    if function_count > 0:
                        function_names = list(plugin.functions.keys())
                        logger.info(f"可用工具: {function_names}")
                    else:
                        logger.warning("警告：MCP 工具數量為 0，可能載入失敗")
            
            logger.info("WebSearch MCP client 啟動成功")
            
        except Exception as e:
            logger.error(f"MCP 客戶端啟動失敗: {e}")
            raise

    async def stop(self) -> None:
        if self._plugin_context and self._mcp_plugin:
            try:
                # 退出異步上下文
                await self._plugin_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"MCP client 關閉失敗: {e}")
            finally:
                self._mcp_plugin = None
                self._plugin_context = None
                self._kernel = None

    async def _invoke_tool(self, name: str, args: Dict[str, Any] | None = None) -> str:
        args = args or {}
        if not self._kernel or not self._mcp_plugin:
            raise RuntimeError("MCP client 尚未啟動，請先呼叫 start()")
        
        try:
            logger.info(f"呼叫 MCP 工具: tool='{name}' args={args}")
            
            # 使用 Kernel 執行 MCP 工具
            from semantic_kernel.functions.kernel_arguments import KernelArguments
            kernel_args = KernelArguments(**args)
            
            # 執行函式
            result = await self._kernel.invoke(
                function_name=name,
                plugin_name="WebSearchMCP",
                arguments=kernel_args
            )
            
            # 處理結果
            if hasattr(result, 'value'):
                result_str = str(result.value)
            else:
                result_str = str(result)
            
            # 如果結果是 TextContent 列表，提取文字內容
            if result_str.startswith('[TextContent('):
                import re
                # 提取 text= 的內容
                match = re.search(r"text='([^']*)'", result_str)
                if match:
                    result_str = match.group(1)
            
            return result_str
            
        except Exception as e:
            logger.error(f"MCP 工具呼叫失敗 {name}: {e}")
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    async def search(self, query: str, max_results: int = 5) -> str:
        return await self._invoke_tool("search", {"query": query, "max_results": max_results})

    async def web_fetch(self, url: str) -> str:
        return await self._invoke_tool("web_fetch", {"url": url})

    async def get_search_status(self) -> str:
        return await self._invoke_tool("get_search_status")

    async def get_current_time(self, format: str = "iso") -> str:
        return await self._invoke_tool("get_current_time", {"format": format})
