#!/usr/bin/env python3
"""
測試前端格式的請求
"""
import asyncio
import aiohttp
import json

BASE_URL = "http://localhost:8081"

async def test_frontend_format():
    """測試前端實際發送的格式"""
    print("🧪 測試前端實際格式的請求...")
    
    # 模擬前端實際發送的格式
    frontend_request = {
        "stream": True,
        "model": "gpt-4o", 
        "messages": [
            {"role": "user", "content": "查詢今年最新的AI應用"}
        ],
        "params": {},
        "background_tasks": {
            "title_generation": True,
            "tags_generation": True, 
            "follow_up_generation": True
        },
        "chat_id": "64e014a1-ebeb-480d-ae6c-1cc44094c737",
        "features": {
            "image_generation": False,
            "code_interpreter": False,
            "web_search": True
        },
        "id": "914a75b7-61c0-4da8-a675-d4620f5b3a93",
        "model_item": {
            "id": "gpt-4o",
            "name": "gpt-4o",
            "object": "model",
            "created": 1759860279,
            "owned_by": "openai"
        },
        "session_id": "ZYBNGajyVxGj76YaAAAH",
        "tool_servers": [],
        "variables": {
            "{{USER_NAME}}": "張竣霖",
            "{{USER_LOCATION}}": "Unknown",
            "{{CURRENT_DATETIME}}": "2025-10-08 02:05:26"
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            print("📤 發送前端格式請求...")
            async with session.post(
                f"{BASE_URL}/api/chat/completions",
                json=frontend_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                status = response.status
                print(f"📥 回應狀態碼: {status}")
                
                if status == 200:
                    # 因為是 stream，我們只讀取一部分
                    content = await response.text()
                    print(f"📄 回應內容（前200字符）: {content[:200]}...")
                else:
                    error_content = await response.text()
                    print(f"❌ 錯誤回應: {error_content}")
                    
        except Exception as e:
            print(f"❌ 請求失敗: {e}")

async def test_minimal_format():
    """測試最小化的請求格式"""
    print("\n🧪 測試最小化格式的請求...")
    
    minimal_request = {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "查詢今年最新的AI應用"}
        ],
        "features": {
            "web_search": True,
            "image_generation": False
        },
        "stream": False  # 不使用 stream 以便完整讀取回應
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            print("📤 發送最小化格式請求...")
            async with session.post(
                f"{BASE_URL}/api/chat/completions",
                json=minimal_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                status = response.status
                print(f"📥 回應狀態碼: {status}")
                
                if status == 200:
                    content = await response.json()
                    print(f"📄 回應成功，內容長度: {len(content.get('choices', [{}])[0].get('message', {}).get('content', ''))}")
                    print(f"📄 回應內容（前200字符）: {content.get('choices', [{}])[0].get('message', {}).get('content', '')[:200]}...")
                else:
                    error_content = await response.text()
                    print(f"❌ 錯誤回應: {error_content}")
                    
        except Exception as e:
            print(f"❌ 請求失敗: {e}")

async def main():
    """主函數"""
    print("🚀 前端格式請求測試")
    print("=" * 50)
    
    # 測試前端實際格式
    await test_frontend_format()
    
    # 測試最小化格式  
    await test_minimal_format()
    
    print("\n✨ 測試完成!")

if __name__ == "__main__":
    asyncio.run(main())