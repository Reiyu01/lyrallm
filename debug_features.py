#!/usr/bin/env python3
"""
調試 Features 模型
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.chat import Features

def debug_features():
    """調試 Features 模型"""
    print("=== Features 模型調試 ===")
    
    # 測試基本功能
    features = Features(web_search=True, image_generation=False, translation=True)
    
    print(f"Features 實例: {features}")
    print(f"Features type: {type(features)}")
    print(f"Features __dict__: {features.__dict__}")
    
    # 測試不同的屬性訪問方式
    print("\n--- 屬性訪問測試 ---")
    print(f"features.web_search: {features.web_search}")
    print(f"getattr(features, 'web_search'): {getattr(features, 'web_search')}")
    
    # 測試 Pydantic 的方法
    print("\n--- Pydantic 方法測試 ---")
    print(f"features.model_dump(): {features.model_dump()}")
    
    # 修正的 get_enabled_features 方法
    def get_enabled_features_v2(self):
        model_data = self.model_dump()
        return [name for name, value in model_data.items() if value is True]
    
    # 測試修正後的方法
    enabled = get_enabled_features_v2(features)
    print(f"啟用的功能: {enabled}")

if __name__ == "__main__":
    debug_features()