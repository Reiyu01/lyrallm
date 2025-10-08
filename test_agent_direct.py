#!/usr/bin/env python3
"""
直接測試 Agent 功能
"""
import asyncio
import sys
import os

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_agent_directly():
    """直接測試 Agent 功能"""
    print("🧪 直接測試 Agent 功能")
    print("=" * 50)
    
    try:
        from agents.practical_agent_orchestrator import create_practical_agent_orchestrator
        
        print("1️⃣ 創建 Agent 協調器...")
        orchestrator = await create_practical_agent_orchestrator()
        
        if orchestrator:
            print("   ✅ Agent 協調器創建成功")
            
            # 測試方法是否存在
            print("2️⃣ 檢查方法...")
            if hasattr(orchestrator, 'get_conversation_history'):
                print("   ✅ get_conversation_history 方法存在")
            else:
                print("   ❌ get_conversation_history 方法不存在")
                
            if hasattr(orchestrator, 'get_conversation_log'):
                print("   ✅ get_conversation_log 方法存在")
            else:
                print("   ❌ get_conversation_log 方法不存在")
            
            print("3️⃣ 測試簡單請求...")
            try:
                result = await orchestrator.process_request("你好", features={"web_search": True})
                print(f"   ✅ 請求處理成功: {result[:100]}...")
                
                # 測試對話歷史
                print("4️⃣ 測試對話歷史...")
                try:
                    history = orchestrator.get_conversation_history()
                    print(f"   ✅ 對話歷史獲取成功: {len(history)} 條記錄")
                except Exception as e:
                    print(f"   ❌ 對話歷史獲取失敗: {e}")
                    
            except Exception as e:
                print(f"   ❌ 請求處理失敗: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("   ❌ Agent 協調器創建失敗")
            
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()

async def test_websearch_directly():
    """直接測試 WebSearch 插件"""
    print("\n🔍 直接測試 WebSearch 插件")
    print("=" * 50)
    
    try:
        from plugins.ollama_web_search_plugin import OllamaWebSearchPlugin
        from plugins.ollama_config import OllamaConfig
        
        print("1️⃣ 創建 WebSearch 插件...")
        config = OllamaConfig()
        plugin = OllamaWebSearchPlugin(config)
        
        print("2️⃣ 測試搜尋功能...")
        try:
            result = await plugin.search("台灣AI政策", max_results=2)
            print(f"   ✅ 搜尋成功: {result[:200]}...")
        except Exception as e:
            print(f"   ❌ 搜尋失敗: {e}")
            import traceback
            traceback.print_exc()
            
    except Exception as e:
        print(f"❌ WebSearch 測試失敗: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """主函數"""
    print("🚀 Agent 直接測試工具")
    
    # 測試 Agent
    await test_agent_directly()
    
    # 測試 WebSearch
    await test_websearch_directly()
    
    print("\n✨ 測試完成!")

if __name__ == "__main__":
    asyncio.run(main())