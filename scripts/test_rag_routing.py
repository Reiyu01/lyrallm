#!/usr/bin/env python3
"""
測試 RAG 路由修復效果
"""
import asyncio
import sys
import os

# 添加父目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.practical_agent_orchestrator import create_practical_agent_orchestrator
from lyrallm.config.config_manager import config_manager

async def test_rag_routing():
    """測試 RAG 路由功能"""
    
    print("=== RAG 路由測試 ===")
    
    # 測試用例
    test_cases = [
        {
            "query": "請進行RAG查詢員工手冊",
            "features": None,
            "expected": "應該使用 RAG 搜尋"
        },
        {
            "query": "請進行RAG查詢員工手冊", 
            "features": {"web_search": True},
            "expected": "應該使用 RAG 搜尋，不是網路搜尋"
        },
        {
            "query": "公司的員工福利政策是什麼？",
            "features": None,
            "expected": "應該使用 RAG 搜尋內部文檔"
        },
        {
            "query": "技術規範中關於代碼風格的要求",
            "features": {"web_search": True},
            "expected": "應該使用 RAG 搜尋，不是網路搜尋"
        }
    ]
    
    try:
        # 創建 Agent 協調器
        orchestrator = await create_practical_agent_orchestrator()
        print("✅ Agent 協調器創建成功")
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n--- 測試案例 {i} ---")
            print(f"查詢: {test_case['query']}")
            print(f"功能: {test_case['features']}")
            print(f"預期: {test_case['expected']}")
            
            try:
                # 直接測試 Agent 協調器
                response = await orchestrator.process_request(
                    user_input=test_case['query'],
                    features=test_case['features']
                )
                
                print(f"回應: {response[:300]}...")  # 只顯示前300字符
                
                # 檢查是否包含 RAG 相關信息
                if "RAG" in response or "知識庫" in response or "員工手冊" in response:
                    print("✅ 似乎使用了 RAG 搜尋")
                else:
                    print("⚠️ 未明確顯示使用 RAG")
                
            except Exception as e:
                print(f"❌ 執行失敗: {e}")
                import traceback
                traceback.print_exc()
                
        print("\n=== 測試完成 ===")
        
    except Exception as e:
        print(f"❌ 測試設置失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_rag_routing())
