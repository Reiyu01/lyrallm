#!/usr/bin/env python3
"""
測試分離配置檔案的載入
"""
import sys
import os

# Add project root to path
sys.path.insert(0, '/home/b225nkust/open_web_ui_nkust')

from lyrallm.config.config_manager import config_manager

def test_config_loading():
    """測試配置載入"""
    print("=" * 60)
    print("LyraLLM 配置載入測試")
    print("=" * 60)
    
    # 測試基本配置
    print("\n1. 基本配置測試:")
    print(f"   路由功能啟用: {config_manager.is_routing_enabled()}")
    print(f"   路由策略: {config_manager.get_routing_strategy()}")
    
    # 測試路由規則載入
    print("\n2. 路由規則載入測試:")
    routing_rules = config_manager.get_routing_rules()
    if routing_rules:
        print(f"   ✅ 路由規則已載入")
        print(f"   - 全域設定: {routing_rules.get('global', {}).get('default_timeout')}")
        print(f"   - 用戶分層數: {len(routing_rules.get('user_tiers', {}))}")
        print(f"   - 路由規則數: {len(routing_rules.get('routing_rules', []))}")
    else:
        print("   ❌ 路由規則載入失敗")
    
    # 測試價格資訊載入
    print("\n3. 價格資訊載入測試:")
    gpt4_pricing = config_manager.get_model_pricing("gpt-4o")
    if gpt4_pricing:
        print(f"   ✅ 價格資訊已載入")
        print(f"   - GPT-4o 輸入成本: {gpt4_pricing.get('input_cost_per_token')}")
        print(f"   - GPT-4o 輸出成本: {gpt4_pricing.get('output_cost_per_token')}")
        
        # 測試成本計算
        estimated_cost = config_manager.calculate_estimated_cost("gpt-4o", 1000, 500)
        print(f"   - 預估成本 (1000 input + 500 output tokens): ${estimated_cost:.6f}")
    else:
        print("   ❌ 價格資訊載入失敗")
    
    # 測試適用規則
    print("\n4. 路由規則匹配測試:")
    context = {"user_tier": "enterprise", "complexity_score": 8.5}
    applicable_rules = config_manager.get_applicable_rules(context)
    print(f"   適用規則數: {len(applicable_rules)}")
    
    if applicable_rules:
        for i, rule in enumerate(applicable_rules[:3]):  # 顯示前3個
            print(f"   - 規則 {i+1}: {rule.get('name')} (優先級: {rule.get('priority')})")
    
    # 測試用戶分層
    print("\n5. 用戶分層配置測試:")
    enterprise_config = config_manager.get_user_tier_config("enterprise")
    if enterprise_config:
        print(f"   企業用戶每日請求限制: {enterprise_config.get('max_requests_per_day')}")
        print(f"   允許的模型: {enterprise_config.get('allowed_models')}")
    
    print("\n✅ 配置測試完成!")

if __name__ == "__main__":
    test_config_loading()