#!/usr/bin/env python3
"""
測試修改後的 chat.py API 與動態參數
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.chat import Features, ChatCompletionRequest, ChatMessage
import json

def test_chat_api_with_dynamic_params():
    print("=== 測試 Chat API 動態參數 ===")
    
    # 測試 Features 類別
    print(f"可用功能: {Features.get_available_features()}")
    print(f"參數模型: {list(Features.get_param_models().keys())}")
    
    # 建立完整的聊天請求
    print("\n=== 測試完整聊天請求 ===")
    
    # 基本請求
    basic_request_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "你好"}
        ],
        "features": {
            "web_search": True
        }
    }
    
    try:
        basic_request = ChatCompletionRequest(**basic_request_data)
        print(f"✅ 基本請求解析成功")
        print(f"  - 啟用功能: {basic_request.features.get_enabled_features()}")
        print(f"  - Features: {basic_request.features}")
    except Exception as e:
        print(f"❌ 基本請求解析失敗: {e}")
    
    # 包含參數的請求
    param_request_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "搜尋最新的 AI 研究論文"}
        ],
        "features": {
            "web_search": True,
            "web_search_params": {
                "search_modes": ["academic", "news"],
                "search_recency": "week",
                "search_domain_filter": ["arxiv.org", "scholar.google.com"],
                "search_options": {
                    "max_results": 10,
                    "language": "zh-TW",
                    "sort_by": "relevance"
                }
            }
        }
    }
    
    try:
        param_request = ChatCompletionRequest(**param_request_data)
        print(f"✅ 參數請求解析成功")
        print(f"  - 啟用功能: {param_request.features.get_enabled_features()}")
        print(f"  - Web Search 參數: {param_request.features.web_search_params}")
        
        # 測試動態參數記錄邏輯
        model_data = param_request.features.model_dump(exclude_none=True)
        for field_name, value in model_data.items():
            if field_name.endswith('_params') and value is not None:
                feature_name = field_name.replace('_params', '')
                print(f"  - {feature_name.title()} 參數記錄: {value}")
                
    except Exception as e:
        print(f"❌ 參數請求解析失敗: {e}")
        import traceback
        print(f"錯誤詳情: {traceback.format_exc()}")
    
    # 測試多功能請求
    multi_request_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "分析這個文件並搜尋相關資訊"}
        ],
        "features": {
            "web_search": True,
            "document_analysis": True,
            "web_search_params": {
                "search_modes": ["web"],
                "search_recency": "month"
            }
        }
    }
    
    try:
        multi_request = ChatCompletionRequest(**multi_request_data)
        print(f"✅ 多功能請求解析成功")
        print(f"  - 啟用功能: {multi_request.features.get_enabled_features()}")
        print(f"  - Features: {multi_request.features}")
    except Exception as e:
        print(f"❌ 多功能請求解析失敗: {e}")

if __name__ == "__main__":
    test_chat_api_with_dynamic_params()