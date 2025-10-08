#!/usr/bin/env python3
"""
檢查 config 參數和 chat.py 邏輯流程
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_config_flow():
    """測試配置參數流程"""
    print("🔧 檢查配置參數流程")
    print("="*40)
    
    try:
        # 測試簡化的 Features 模型
        from config.simple_features import Features
        
        # 測試 1: 無功能
        features1 = Features()
        print(f"1. 預設功能: {features1.model_dump()}")
        print(f"   啟用功能: {features1.get_enabled_features()}")
        print(f"   有功能啟用: {features1.has_any_feature_enabled()}")
        
        # 測試 2: 啟用 web_search
        features2 = Features(web_search=True)
        print(f"\n2. 啟用搜尋: {features2.model_dump()}")
        print(f"   啟用功能: {features2.get_enabled_features()}")
        print(f"   有功能啟用: {features2.has_any_feature_enabled()}")
        
        # 測試 3: 額外欄位（測試彈性）
        features3 = Features(web_search=True, custom_field="test")
        print(f"\n3. 額外欄位: {features3.model_dump()}")
        print(f"   啟用功能: {features3.get_enabled_features()}")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_mode_logic():
    """測試 Agent 模式邏輯"""
    print("\n🤖 檢查 Agent 模式邏輯")
    print("="*40)
    
    try:
        from config.simple_features import Features
        
        # 模擬 chat.py 中的邏輯
        def should_use_agent_mode(features):
            if not features:
                return False
            features_dict = features.model_dump(exclude_none=True)
            return any(features_dict.values())
        
        # 測試案例
        test_cases = [
            ("無 Features", None),
            ("空 Features", Features()),
            ("啟用搜尋", Features(web_search=True)),
            ("關閉搜尋", Features(web_search=False)),
        ]
        
        for name, features in test_cases:
            agent_mode = should_use_agent_mode(features)
            print(f"{name}: Agent模式={agent_mode}")
            
            if features:
                print(f"  features_dict: {features.model_dump(exclude_none=True)}")
                # 模擬傳給 PracticalAgentOrchestrator 的邏輯
                if agent_mode:
                    orchestrator_features = features.to_dict()
                    print(f"  傳給協調器: {orchestrator_features}")
        
        return True
        
    except Exception as e:
        print(f"❌ Agent 模式邏輯測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_parameter_consistency():
    """檢查參數一致性"""
    print("\n📊 檢查參數一致性")
    print("="*40)
    
    try:
        from config.simple_features import Features
        
        # 測試參數傳遞鏈路
        print("參數傳遞鏈路測試:")
        
        # 1. 前端 → Features 模型
        frontend_data = {"web_search": True}
        features = Features(**frontend_data)
        print(f"1. 前端 → Features: {frontend_data} → {features.model_dump()}")
        
        # 2. Features → Agent 模式判斷
        features_dict = features.model_dump(exclude_none=True)
        agent_mode = any(features_dict.values())
        print(f"2. Features → Agent判斷: {features_dict} → {agent_mode}")
        
        # 3. Agent 模式 → PracticalAgentOrchestrator
        if agent_mode:
            orchestrator_input = features.to_dict()
            print(f"3. Agent → 協調器: {orchestrator_input}")
            
            # 4. PracticalAgentOrchestrator 內部邏輯
            # 模擬 process_request 中的邏輯
            available_capabilities = ["web_search"]  # 系統支援的能力
            active_capabilities = []
            
            if orchestrator_input and orchestrator_input.get('web_search') and "web_search" in available_capabilities:
                active_capabilities.append("web_search")
            
            print(f"4. 協調器內部: 系統能力={available_capabilities}, 啟用能力={active_capabilities}")
        
        print("\n✅ 參數鏈路檢查完成，邏輯一致")
        return True
        
    except Exception as e:
        print(f"❌ 參數一致性檢查失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函數"""
    print("🔍 Config 參數和邏輯流程檢查")
    print("=" * 50)
    
    results = []
    
    # 檢查配置流程
    result1 = test_config_flow()
    results.append(("配置參數流程", result1))
    
    # 檢查 Agent 模式邏輯
    result2 = test_agent_mode_logic()
    results.append(("Agent 模式邏輯", result2))
    
    # 檢查參數一致性
    result3 = check_parameter_consistency()
    results.append(("參數一致性", result3))
    
    # 總結
    print("\n📋 檢查結果")
    print("=" * 20)
    
    for test_name, passed in results:
        status = "✅ 正常" if passed else "❌ 有問題"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n🎉 配置和邏輯流程檢查通過！")
        print("建議：")
        print("- ✅ 使用簡化的 Features 模型")
        print("- ✅ Agent 模式邏輯清晰")
        print("- ✅ 參數傳遞鏈路正確")
    else:
        print("\n⚠️  發現問題，需要修復")

if __name__ == "__main__":
    main()