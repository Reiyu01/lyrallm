#!/usr/bin/env python3
"""
測試配置驅動的 Plugin 系統
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.chat import Features
from lyrallm.config.plugin_manager import plugin_manager

def test_config_driven_plugins():
    """測試配置驅動的 Plugin 系統"""
    print("=== 配置驅動 Plugin 系統測試 ===")
    
    # 測試 1: 查看配置資訊
    print("\n--- Plugin 配置資訊 ---")
    info = plugin_manager.get_plugin_info()
    print(f"總共定義的 plugins: {info['total_plugins']}")
    print(f"可用的 plugins: {info['available_plugins']}")
    
    print("\n--- 所有 Plugin 定義 ---")
    for plugin in info['plugin_list']:
        status = "✅ 啟用" if plugin['enabled'] else "❌ 停用"
        config_req = "🔧 需要配置" if plugin['require_config'] else "⚡ 免配置"
        print(f"{status} {config_req} {plugin['id']}")
        print(f"   功能: {plugin['feature_name']}")
        print(f"   描述: {plugin['description']}")
        print()
    
    # 測試 2: 不同 Features 組合
    test_cases = [
        ("無功能", None),
        ("只開啟網路搜尋", Features(web_search=True)),
        ("只開啟圖像生成", Features(image_generation=True)),
        ("只開啟程式碼解釋", Features(code_interpreter=True)),
        ("開啟多個功能", Features(web_search=True, image_generation=True)),
        ("全部開啟", Features(web_search=True, image_generation=True, code_interpreter=True)),
    ]
    
    print("--- Features 與 Plugin 映射測試 ---")
    for test_name, features in test_cases:
        plugins = plugin_manager.get_plugins_for_features(features)
        plugin_names = [p['id'] for p in plugins]
        print(f"{test_name}: {plugin_names if plugin_names else '無 plugins'}")
    
    # 測試 3: 配置熱更新
    print(f"\n--- 配置熱更新測試 ---")
    print("重新載入配置前:")
    print(f"可用 plugins: {plugin_manager.get_plugin_info()['available_plugins']}")
    
    try:
        plugin_manager.reload_config()
        print("重新載入配置後:")
        print(f"可用 plugins: {plugin_manager.get_plugin_info()['available_plugins']}")
        print("✅ 配置熱更新成功")
    except Exception as e:
        print(f"❌ 配置熱更新失敗: {e}")

def demonstrate_config_flexibility():
    """展示配置的靈活性"""
    print("\n=== 配置靈活性展示 ===")
    
    # 展示如何通過修改配置文件來控制 plugins
    config_examples = [
        {
            "scenario": "添加新 Plugin",
            "description": "只需在 plugin_config.yaml 中添加新的 plugin 定義，無需修改程式碼",
            "example": """
  新功能_plugin:
    feature_name: "new_feature"
    plugin_class: "plugins.new_plugin.NewPlugin"
    kernel_name: "NewFeature"
    description: "新功能 Plugin"
            """
        },
        {
            "scenario": "停用 Plugin",
            "description": "只需設定 enabled: false，plugin 就不會被載入",
            "example": """
  web_search:
    enabled: false  # 停用網路搜尋功能
            """
        },
        {
            "scenario": "修改 Plugin 設定",
            "description": "可以修改 plugin 的 kernel 名稱、配置需求等",
            "example": """
  web_search:
    kernel_name: "WebSearchV2"  # 修改名稱
    require_config: false       # 移除配置需求
            """
        }
    ]
    
    for example in config_examples:
        print(f"\n--- {example['scenario']} ---")
        print(f"說明: {example['description']}")
        print(f"配置範例:{example['example']}")

if __name__ == "__main__":
    test_config_driven_plugins()
    demonstrate_config_flexibility()
    
    print("\n=== 使用指南 ===")
    print("1. 修改 config/plugin_config.yaml 來新增、停用或配置 plugins")
    print("2. 使用 POST /api/chat/plugins/reload 來熱更新配置")
    print("3. 使用 GET /api/chat/plugins 來查看目前的 plugin 狀態")
    print("4. 前端只需傳遞 features 參數，後端會自動根據配置載入對應的 plugins")