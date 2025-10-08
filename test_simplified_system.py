#!/usr/bin/env python3
"""
簡化系統測試 - 測試 web_search 功能
"""
import asyncio
import aiohttp
import json

BASE_URL = "http://localhost:8081"

async def test_web_search_agent():
    """測試 web_search Agent 功能"""
    print("🧪 測試 Web Search Agent 功能")
    print("=" * 50)
    
    # 測試請求
    test_request = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "搜尋台灣最新的AI政策"}
        ],
        "features": {
            "web_search": True,
            "image_generation": False,
            "code_interpreter": False
        },
        "stream": False
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            print("📤 發送 web_search 請求...")
            async with session.post(
                f"{BASE_URL}/api/chat/completions",
                json=test_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                status = response.status
                print(f"📥 回應狀態碼: {status}")
                
                if status == 200:
                    content = await response.json()
                    response_text = content.get('choices', [{}])[0].get('message', {}).get('content', '')
                    print(f"📄 回應成功，內容長度: {len(response_text)}")
                    print(f"📄 回應內容（前300字符）: {response_text[:300]}...")
                    
                    # 檢查是否包含搜尋結果
                    if "搜尋" in response_text or "AI政策" in response_text or "台灣" in response_text:
                        print("✅ 成功: 回應包含相關搜尋內容")
                    else:
                        print("⚠️ 警告: 回應可能未使用搜尋功能")
                else:
                    error_content = await response.text()
                    print(f"❌ 錯誤回應: {error_content}")
                    
        except Exception as e:
            print(f"❌ 請求失敗: {e}")

async def test_basic_chat():
    """測試基本聊天功能（不使用 features）"""
    print("\n🧪 測試基本聊天功能")
    print("=" * 50)
    
    basic_request = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "你好，介紹一下自己"}
        ],
        "stream": False
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            print("📤 發送基本聊天請求...")
            async with session.post(
                f"{BASE_URL}/api/chat/completions",
                json=basic_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                status = response.status
                print(f"📥 回應狀態碼: {status}")
                
                if status == 200:
                    content = await response.json()
                    response_text = content.get('choices', [{}])[0].get('message', {}).get('content', '')
                    print(f"📄 回應成功，內容長度: {len(response_text)}")
                    print(f"📄 回應內容（前200字符）: {response_text[:200]}...")
                else:
                    error_content = await response.text()
                    print(f"❌ 錯誤回應: {error_content}")
                    
        except Exception as e:
            print(f"❌ 請求失敗: {e}")

async def test_features_endpoint():
    """測試 features 端點"""
    print("\n🧪 測試 Features 端點")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        try:
            print("📤 取得可用功能列表...")
            async with session.get(f"{BASE_URL}/api/chat/features") as response:
                status = response.status
                print(f"📥 回應狀態碼: {status}")
                
                if status == 200:
                    content = await response.json()
                    features = content.get('data', {}).get('available_features', [])
                    print(f"✅ 可用功能: {features}")
                    
                    feature_details = content.get('data', {}).get('feature_details', [])
                    for detail in feature_details:
                        print(f"  - {detail.get('name')}: {detail.get('description')}")
                else:
                    error_content = await response.text()
                    print(f"❌ 錯誤回應: {error_content}")
                    
        except Exception as e:
            print(f"❌ 請求失敗: {e}")

async def main():
    """主函數"""
    print("🚀 簡化系統測試")
    print("🔍 確保虛擬環境已啟動：(sk)")
    
    # 測試 features 端點
    await test_features_endpoint()
    
    # 測試基本聊天
    await test_basic_chat()
    
    # 測試 web_search agent
    await test_web_search_agent()
    
    print("\n✨ 測試完成!")

if __name__ == "__main__":
    asyncio.run(main())