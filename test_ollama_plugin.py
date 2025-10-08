"""
Ollama Web Search Plugin 測試檔案
"""

import asyncio
import json
import logging
import os
import sys

# 添加專案路徑
sys.path.append('/home/b225nkust/open_web_ui_nkust/semantic_kernel')

from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin
from plugins.ollama_config import ollama_config

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_ollama_web_search():
    """測試 Ollama Web Search Plugin"""
    
    print("=== Ollama Web Search Plugin 測試 ===\n")
    
    # 檢查配置
    print("1. 檢查配置狀態:")
    config_dict = ollama_config.get_config_dict()
    print(json.dumps(config_dict, indent=2, ensure_ascii=False))
    
    if not ollama_config.is_configured():
        print("\n❌ Ollama API Key 未配置!")
        print("請設定環境變數: export OLLAMA_API_KEY='your_api_key'")
        return
    
    # 創建 Plugin 實例
    try:
        plugin = OllamaWebSearchPlugin()  # 現在會自動從環境變數讀取配置
        print("\n✅ Plugin 初始化成功")
    except Exception as e:
        print(f"\n❌ Plugin 初始化失敗: {e}")
        return
    
    # 測試服務狀態
    print("\n2. 測試服務狀態:")
    try:
        status_result = await plugin.get_search_status()
        print(status_result)
    except Exception as e:
        print(f"❌ 服務狀態檢查失敗: {e}")
    
    # 測試網路搜尋
    print("\n3. 測試網路搜尋:")
    test_queries = [
        "What is Semantic Kernel?",
        "Ollama web search API",
        "Python async programming"
    ]
    
    for query in test_queries:
        print(f"\n搜尋查詢: '{query}'")
        try:
            search_result = await plugin.web_search(query=query, max_results=3)
            result_data = json.loads(search_result)
            
            if "error" in result_data:
                print(f"❌ 搜尋失敗: {result_data['error']}")
            else:
                print(f"✅ 找到 {result_data['total_results']} 個結果")
                for i, result in enumerate(result_data['results'][:2], 1):
                    print(f"  {i}. {result['title']}")
                    print(f"     URL: {result['url']}")
                    print(f"     內容: {result['content'][:100]}...")
                    
        except Exception as e:
            print(f"❌ 搜尋異常: {e}")
    
    # 測試網頁抓取
    print("\n4. 測試網頁抓取:")
    test_urls = [
        "https://ollama.com",
        "https://github.com/microsoft/semantic-kernel"
    ]
    
    for url in test_urls:
        print(f"\n抓取網頁: '{url}'")
        try:
            fetch_result = await plugin.web_fetch(url=url)
            result_data = json.loads(fetch_result)
            
            if "error" in result_data:
                print(f"❌ 抓取失敗: {result_data['error']}")
            else:
                print(f"✅ 抓取成功")
                print(f"  標題: {result_data['title']}")
                print(f"  內容長度: {result_data['content_length']}")
                print(f"  連結數量: {len(result_data['links'])}")
                print(f"  內容預覽: {result_data['content'][:150]}...")
                
        except Exception as e:
            print(f"❌ 抓取異常: {e}")

async def test_semantic_kernel_integration():
    """測試與 Semantic Kernel 的整合"""
    print("\n\n=== Semantic Kernel 整合測試 ===\n")
    
    try:
        import semantic_kernel as sk
        from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
        
        # 創建 Kernel
        kernel = sk.Kernel()
        
        # 檢查是否有可用的 LLM 配置
        print("注意: 此測試需要有效的 LLM 配置")
        print("如果沒有 LLM 配置，僅測試 Plugin 添加功能\n")
        
        # 添加 Ollama Web Search Plugin
        if ollama_config.is_configured():
            plugin = OllamaWebSearchPlugin()  # 自動從環境變數讀取配置
            kernel.add_plugin(plugin, plugin_name="ollama_web_search")
            print("✅ Plugin 已成功添加到 Semantic Kernel")
            
            # 列出可用函數
            functions = kernel.get_function_from_plugin("ollama_web_search")
            print(f"✅ 可用函數數量: {len(kernel.plugins)}")
            
        else:
            print("❌ Ollama 未配置，跳過整合測試")
            
    except ImportError as e:
        print(f"❌ Semantic Kernel 導入失敗: {e}")
    except Exception as e:
        print(f"❌ 整合測試失敗: {e}")

async def main():
    """主測試函數"""
    await test_ollama_web_search()
    await test_semantic_kernel_integration()
    print("\n=== 測試完成 ===")

if __name__ == "__main__":
    # 設定測試用的 API Key (如果環境變數未設定)
    if not os.getenv("OLLAMA_API_KEY"):
        print("警告: 未找到 OLLAMA_API_KEY 環境變數")
        print("請執行: export OLLAMA_API_KEY='your_api_key'")
        print("或在此處暫時設定測試用 API Key\n")
        
        # 取消註解並設定您的 API Key 進行測試
        # os.environ["OLLAMA_API_KEY"] = "your_test_api_key_here"
    
    asyncio.run(main())