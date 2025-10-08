#!/usr/bin/env python3
"""
測試 Agent 模式觸發機制
"""

import asyncio
import json
import aiohttp
import sys
import os

async def test_agent_trigger():
    """測試 Agent 模式觸發"""
    
    base_url = "http://127.0.0.1:8081"
    
    # 測試場景 1: 無 features 參數（應該使用傳統模式）
    print("🧪 測試場景 1: 無 features 參數")
    print("-" * 40)
    
    payload_1 = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "你好"}
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/api/chat/completions", json=payload_1) as response:
            if response.status == 200:
                result = await response.json()
                print(f"✅ 回應成功: {result['choices'][0]['message']['content'][:50]}...")
            else:
                error = await response.text()
                print(f"❌ 請求失敗: {response.status} - {error}")
    
    # 測試場景 2: 有 features 參數但為空（應該使用傳統模式）
    print(f"\n🧪 測試場景 2: 有空的 features 參數")
    print("-" * 40)
    
    payload_2 = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "你好"}
        ],
        "features": {}
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/api/chat/completions", json=payload_2) as response:
            if response.status == 200:
                result = await response.json()
                print(f"✅ 回應成功: {result['choices'][0]['message']['content'][:50]}...")
            else:
                error = await response.text()
                print(f"❌ 請求失敗: {response.status} - {error}")
    
    # 測試場景 3: 啟用 web_search feature（應該使用 Agent 模式）
    print(f"\n🧪 測試場景 3: 啟用 web_search feature")
    print("-" * 40)
    
    payload_3 = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "請搜尋最新的台灣AI政策"}
        ],
        "features": {
            "web_search": True
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/api/chat/completions", json=payload_3) as response:
            if response.status == 200:
                result = await response.json()
                print(f"✅ 回應成功: {result['choices'][0]['message']['content'][:50]}...")
            else:
                error = await response.text()
                print(f"❌ 請求失敗: {response.status} - {error}")
    
    # 測試場景 4: 檢查可用的 features
    print(f"\n🧪 測試場景 4: 檢查可用的 features")
    print("-" * 40)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{base_url}/api/chat/features") as response:
            if response.status == 200:
                features = await response.json()
                print(f"✅ 可用 features: {json.dumps(features, indent=2, ensure_ascii=False)}")
            else:
                error = await response.text()
                print(f"❌ 獲取 features 失敗: {response.status} - {error}")

if __name__ == "__main__":
    print("🚀 Agent 模式觸發測試")
    print("="*50)
    
    try:
        asyncio.run(test_agent_trigger())
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        print(traceback.format_exc())
