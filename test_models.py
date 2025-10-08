#!/usr/bin/env python3
"""
測試 API 請求中的 features 參數解析
"""

import json
from pydantic import ValidationError

# 直接導入我們修改的模型
import sys
import os
sys.path.append(os.path.dirname(__file__))

try:
    from api.chat import ChatCompletionRequest, ChatMessage, Features
    
    print("=== 測試 Features 模型 ===")
    
    # 測試 1: 模擬前端送來的完整請求
    frontend_request = {
        "stream": True,
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "你好"}],
        "params": {},
        "tool_servers": [],
        "features": {
            "image_generation": False,
            "code_interpreter": False,
            "web_search": True
        },
        "variables": {},
        "model_item": {},
        "session_id": "test",
        "chat_id": "test",
        "id": "test",
        "background_tasks": {}
    }
    
    try:
        request = ChatCompletionRequest(**frontend_request)
        print("✅ 成功解析前端請求")
        print(f"模型: {request.model}")
        print(f"Features: {request.features}")
        if request.features:
            print(f"  - Web Search: {request.features.web_search}")
            print(f"  - Image Generation: {request.features.image_generation}")
            print(f"  - Code Interpreter: {request.features.code_interpreter}")
    except ValidationError as e:
        print(f"❌ 請求解析失敗: {e}")
    
    # 測試 2: 沒有 features 的請求
    simple_request = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "你好"}]
    }
    
    try:
        request2 = ChatCompletionRequest(**simple_request)
        print("\n✅ 成功解析簡單請求")
        print(f"Features: {request2.features}")
    except ValidationError as e:
        print(f"❌ 簡單請求解析失敗: {e}")
        
    # 測試 3: 只有部分 features 的請求
    partial_request = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "你好"}],
        "features": {"web_search": True}
    }
    
    try:
        request3 = ChatCompletionRequest(**partial_request)
        print("\n✅ 成功解析部分 features 請求")
        print(f"Features: {request3.features}")
        if request3.features:
            print(f"  - Web Search: {request3.features.web_search}")
    except ValidationError as e:
        print(f"❌ 部分 features 請求解析失敗: {e}")
    
    print("\n=== 測試完成 ===")
    
except ImportError as e:
    print(f"無法導入模組: {e}")
    print("請確保在正確的環境中執行")