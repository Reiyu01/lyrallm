"""
Ollama Web Search Plugin for Semantic Kernel
基於 Ollama Web Search API 實作的 Semantic Kernel Plugin
遵循官方 Semantic Kernel Python 實現標準
"""

import asyncio
import aiohttp
import json
import logging
from typing import List, Dict, Any, Optional

from semantic_kernel.functions import kernel_function

logger = logging.getLogger(__name__)

class OllamaWebSearchPlugin:
    """
    Ollama Web Search Plugin for Semantic Kernel
    
    提供以下功能：
    1. web_search: 網路搜尋功能
    2. web_fetch: 網頁內容抓取功能
    3. get_search_status: 檢查服務狀態
    """
    
    def __init__(self, api_key: str = None, base_url: str = None, timeout: int = None):
        """
        初始化 Ollama Web Search Plugin
        
        Args:
            api_key: Ollama API Key (可選，會從環境變數讀取)
            base_url: Ollama API 基礎 URL (可選，會從環境變數讀取)
            timeout: 請求超時時間 (可選，會從環境變數讀取)
        """
        from .ollama_config import ollama_config
        
        # 使用提供的參數或從配置讀取
        self.api_key = api_key or ollama_config.api_key
        self.base_url = base_url or ollama_config.base_url
        self.timeout = timeout or ollama_config.timeout
        
        if not self.api_key:
            raise ValueError(
                "Ollama API Key is required. Please set OLLAMA_API_KEY environment variable "
                "or provide it as a parameter."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    @kernel_function(
        description="Search the web for current information using Ollama Web Search API. Returns relevant web search results including titles, URLs, and content snippets.",
        name="search"
    )
    async def search(self, query: str, max_results: int = 5) -> str:
        """
        使用 Ollama Web Search API 進行網路搜尋
        
        Args:
            query: 搜尋查詢字串
            max_results: 最大結果數量 (1-10)
            
        Returns:
            格式化的搜尋結果 JSON 字串
        """
        try:
            logger.info(f"[OllamaWebSearch] 執行搜尋: {query}")
            
            # 限制 max_results 範圍
            max_results = max(1, min(max_results, 10))
            
            payload = {
                "query": query,
                "max_results": max_results
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/web_search",
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[OllamaWebSearch] API 錯誤 {response.status}: {error_text}")
                        return json.dumps({
                            "error": f"Web search failed with status {response.status}",
                            "details": error_text
                        }, ensure_ascii=False, indent=2)
                    
                    result = await response.json()
                    
                    # 轉換為標準化格式
                    search_results = []
                    for item in result.get("results", []):
                        search_results.append({
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "content": item.get("content", "")[:500] + "..." if len(item.get("content", "")) > 500 else item.get("content", "")
                        })
                    
                    formatted_result = {
                        "query": query,
                        "total_results": len(search_results),
                        "results": search_results
                    }
                    
                    logger.info(f"[OllamaWebSearch] 搜尋成功，找到 {len(search_results)} 個結果")
                    return json.dumps(formatted_result, ensure_ascii=False, indent=2)
                    
        except asyncio.TimeoutError:
            logger.error(f"[OllamaWebSearch] 搜尋超時: {query}")
            return json.dumps({
                "error": "Web search timeout",
                "query": query
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"[OllamaWebSearch] 搜尋失敗: {e}")
            return json.dumps({
                "error": f"Web search failed: {str(e)}",
                "query": query
            }, ensure_ascii=False, indent=2)
    
    @kernel_function(
        description="Fetch content from a specific web page URL using Ollama Web Fetch API. Returns the page title, main content, and extracted links.",
        name="web_fetch"
    )
    async def web_fetch(self, url: str) -> str:
        """
        使用 Ollama Web Fetch API 抓取指定網頁內容
        
        Args:
            url: 要抓取的網頁 URL
            
        Returns:
            格式化的網頁內容 JSON 字串
        """
        try:
            logger.info(f"[OllamaWebFetch] 抓取網頁: {url}")
            
            # 確保 URL 有協議前綴
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            
            payload = {
                "url": url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/web_fetch",
                    headers=self.headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"[OllamaWebFetch] API 錯誤 {response.status}: {error_text}")
                        return json.dumps({
                            "error": f"Web fetch failed with status {response.status}",
                            "details": error_text,
                            "url": url
                        }, ensure_ascii=False, indent=2)
                    
                    result = await response.json()
                    
                    # 格式化結果
                    formatted_result = {
                        "url": url,
                        "title": result.get("title", ""),
                        "content": result.get("content", "")[:2000] + "..." if len(result.get("content", "")) > 2000 else result.get("content", ""),
                        "links": result.get("links", [])[:10],  # 限制連結數量
                        "content_length": len(result.get("content", ""))
                    }
                    
                    logger.info(f"[OllamaWebFetch] 抓取成功: {url}")
                    return json.dumps(formatted_result, ensure_ascii=False, indent=2)
                    
        except asyncio.TimeoutError:
            logger.error(f"[OllamaWebFetch] 抓取超時: {url}")
            return json.dumps({
                "error": "Web fetch timeout",
                "url": url
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"[OllamaWebFetch] 抓取失敗: {e}")
            return json.dumps({
                "error": f"Web fetch failed: {str(e)}",
                "url": url
            }, ensure_ascii=False, indent=2)

    @kernel_function(
        description="Get the status and capabilities of the Ollama Web Search service",
        name="get_search_status"
    )
    async def get_search_status(self) -> str:
        """
        檢查 Ollama Web Search 服務狀態
        
        Returns:
            服務狀態資訊 JSON 字串
        """
        try:
            # 簡單的測試搜尋來檢查服務狀態
            test_result = await self.web_search("test", max_results=1)
            result_data = json.loads(test_result)
            
            if "error" in result_data:
                status = "error"
                message = result_data["error"]
            else:
                status = "healthy"
                message = "Ollama Web Search service is operational"
            
            return json.dumps({
                "service": "Ollama Web Search",
                "status": status,
                "message": message,
                "capabilities": [
                    "web_search - Search the web for information",
                    "web_fetch - Fetch content from specific URLs",
                    "get_search_status - Check service status"
                ]
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            return json.dumps({
                "service": "Ollama Web Search", 
                "status": "error",
                "message": f"Service check failed: {str(e)}"
            }, ensure_ascii=False, indent=2)