#!/usr/bin/env python3
"""
測試實際的 API 請求處理（模擬完整流程）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from semantic_kernel.config.plugin_manager import plugin_manager
from config.dynamic_features import DynamicFeaturesFactory
import json

def test_api_flow():
    print("=== 測試 API 請求流程 ===")
    
    # 1. 動態生成 Features 模型（模擬 chat.py 載入）
    Features = DynamicFeaturesFactory.create_features_model(plugin_manager)
    print(f"✅ Features 模型生成成功")
    
    # 2. 模擬 API 請求數據
    api_request_data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "請搜尋 2024 年最新的機器學習論文，特別是關於 Transformer 架構的研究"}
        ],
        "features": {
            "web_search": True,
            "web_search_params": {
                "search_modes": ["academic", "news"],
                "search_recency": "week",
                "search_domain_filter": ["arxiv.org", "scholar.google.com", "openreview.net"],
                "search_options": {
                    "max_results": 15,
                    "language": "en",
                    "sort_by": "relevance",
                    "include_abstracts": True
                }
            }
        }
    }
    
    # 3. 解析請求
    try:
        features = Features(**api_request_data["features"])
        print(f"✅ 請求解析成功")
        
        # 模擬 chat.py 中的記錄邏輯
        request_id = "test_req_001"
        enabled_features = features.get_enabled_features()
        print(f"[{request_id}] 前端啟用功能: {enabled_features if enabled_features else '無'}")
        
        # 動態記錄細項參數
        model_data = features.model_dump(exclude_none=True)
        for field_name, value in model_data.items():
            if field_name.endswith('_params') and value is not None:
                feature_name = field_name.replace('_params', '')
                print(f"[{request_id}] {feature_name.title()} 參數: {value}")
        
        # 4. 驗證參數模型
        if features.web_search_params:
            params = features.web_search_params
            print(f"\n=== Web Search 參數詳情 ===")
            print(f"  - 搜尋模式: {params.search_modes}")
            print(f"  - 時間範圍: {params.search_recency}")
            print(f"  - 網域過濾: {params.search_domain_filter}")
            print(f"  - 進階選項: {params.search_options}")
            
            # 模擬 plugin_manager 中的參數提取邏輯
            plugin_params = {}
            if params.search_modes:
                plugin_params['search_modes'] = params.search_modes
            if params.search_recency:
                plugin_params['search_recency'] = params.search_recency
            if params.search_domain_filter:
                plugin_params['search_domain_filter'] = params.search_domain_filter
            if params.search_options:
                plugin_params.update(params.search_options)
            
            print(f"\n=== 傳遞給 Plugin 的參數 ===")
            print(json.dumps(plugin_params, indent=2, ensure_ascii=False))
        
        # 5. 測試最小請求
        print(f"\n=== 測試最小請求（無參數）===")
        minimal_data = {
            "web_search": True
        }
        
        minimal_features = Features(**minimal_data)
        print(f"✅ 最小請求解析成功: 啟用功能 {minimal_features.get_enabled_features()}")
        print(f"   參數: {minimal_features.web_search_params}")
        
    except Exception as e:
        print(f"❌ 請求處理失敗: {e}")
        import traceback
        print(f"錯誤詳情: {traceback.format_exc()}")

if __name__ == "__main__":
    test_api_flow()