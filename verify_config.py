#!/usr/bin/env python3
"""
驗證 plugin 配置和參數模型
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lyrallm.config.plugin_manager import plugin_manager
import json

def verify_plugin_config():
    print("=== 驗證 Plugin 配置 ===")
    
    # 檢查配置載入
    plugin_configs = plugin_manager.get_plugin_configs()
    print(f"總計 Plugin 配置: {len(plugin_configs)}")
    
    for plugin_id, config in plugin_configs.items():
        print(f"\n📦 Plugin: {plugin_id}")
        print(f"  - 功能名稱: {config.get('feature_name')}")
        print(f"  - 描述: {config.get('description')}")
        print(f"  - 啟用: {config.get('enabled', True)}")
        
        if 'params_model' in config:
            print(f"  - 有參數模型: ✅")
            params_config = config['params_model']
            print(f"    - 類別名稱: {params_config.get('class_name')}")
            print(f"    - 欄位: {list(params_config.get('fields', {}).keys())}")
            
            # 詳細欄位資訊
            for field_name, field_config in params_config.get('fields', {}).items():
                print(f"      - {field_name}: {field_config.get('type')} (可選: {field_config.get('optional', True)})")
        else:
            print(f"  - 參數模型: ❌")
    
    print(f"\n=== 可用功能名稱 ===")
    features = plugin_manager.get_available_feature_names()
    for feature in features:
        print(f"  - {feature}")
    
    print(f"\n=== Plugin 資訊 ===")
    info = plugin_manager.get_plugin_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    verify_plugin_config()