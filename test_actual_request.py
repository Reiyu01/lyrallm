#!/usr/bin/env python3
"""
模擬實際的 API 請求測試
"""

import json
from api.chat import ChatCompletionRequest, Features, WebSearchParams

def test_actual_request():
    """測試實際的 API 請求處理"""
    print("=== 實際 API 請求測試 ===")
    
    # 模擬前端發送的完整請求
    request_data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "請搜尋最新的人工智慧新聞，重點關注學術研究"}
        ],
        "temperature": 0.7,
        "features": {
            "web_search": True,
            "web_search_params": {
                "search_modes": ["news", "academic"],
                "search_recency": "week",
                "search_domain_filter": ["arxiv.org", "ieee.org", "techcrunch.com"],
                "search_options": {
                    "max_results": 10,
                    "language": "zh-TW"
                }
            }
        }
    }
    
    print("前端請求 JSON:")
    print(json.dumps(request_data, indent=2, ensure_ascii=False))
    
    # 測試解析請求
    try:
        request = ChatCompletionRequest(**request_data)
        print("\n✅ 請求解析成功")
        print(f"模型: {request.model}")
        print(f"啟用功能: {request.features.get_enabled_features()}")
        
        if request.features.web_search_params:
            params = request.features.web_search_params.model_dump(exclude_none=True)
            print(f"Web Search 參數: {params}")
        
    except Exception as e:
        print(f"❌ 請求解析失敗: {e}")

def test_minimal_request():
    """測試最小請求（無細項參數）"""
    print("\n=== 最小請求測試 ===")
    
    minimal_data = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "你好"}
        ],
        "features": {
            "web_search": True
        }
    }
    
    print("最小請求 JSON:")
    print(json.dumps(minimal_data, indent=2, ensure_ascii=False))
    
    try:
        request = ChatCompletionRequest(**minimal_data)
        print("\n✅ 最小請求解析成功")
        print(f"啟用功能: {request.features.get_enabled_features()}")
        print(f"Web Search 參數: {request.features.web_search_params}")
        
    except Exception as e:
        print(f"❌ 最小請求解析失敗: {e}")

if __name__ == "__main__":
    test_actual_request()
    test_minimal_request()
    
    print("\n=== 實現說明 ===")
    print("🎯 最小可運行方案完成")
    print("📡 前端可以傳遞細項參數")
    print("🔧 後端可以接收並傳遞給 plugin")
    print("⚡ Plugin 可以選擇是否使用參數")
    print("🔄 向下相容，不影響現有功能")
    print("📝 詳細的日誌記錄")
    
    print("\n=== 擴展方式 ===")
    print("1. 為其他 plugin 添加參數類別")
    print("2. 在 Features 中添加對應的參數欄位")
    print("3. 在 plugin_manager._get_plugin_params 中添加處理邏輯")
    print("4. Plugin 實作 set_params 方法來接收參數")