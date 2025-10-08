#!/usr/bin/env python3
"""
測試 Semantic Kernel API 與 OpenAI API 格式兼容性
"""

import requests
import json
import sys

def test_openai_compatibility():
    """測試與 OpenAI API 格式的兼容性"""
    base_url = "http://localhost:8081"
    
    print("🧪 測試 Semantic Kernel API 與 OpenAI 格式兼容性")
    print("=" * 60)
    
    try:
        # 測試模型列表端點
        print("📋 測試 /api/models 端點...")
        response = requests.get(f"{base_url}/api/models")
        
        if response.status_code == 200:
            data = response.json()
            
            # 檢查 OpenAI API 標準格式
            assert "object" in data, "缺少 'object' 欄位"
            assert data["object"] == "list", "object 欄位應該是 'list'"
            assert "data" in data, "缺少 'data' 欄位"
            assert isinstance(data["data"], list), "data 欄位應該是陣列"
            
            print(f"✅ 成功！找到 {len(data['data'])} 個模型")
            
            # 檢查每個模型的格式
            for i, model in enumerate(data["data"]):
                print(f"\n📝 檢查模型 {i+1}: {model.get('id', 'unknown')}")
                
                # 必要欄位檢查
                required_fields = ["id", "object", "created", "owned_by"]
                for field in required_fields:
                    assert field in model, f"模型缺少必要欄位: {field}"
                
                assert model["object"] == "model", "模型的 object 欄位應該是 'model'"
                
                print(f"  ✅ ID: {model['id']}")
                print(f"  ✅ Object: {model['object']}")
                print(f"  ✅ Created: {model['created']}")
                print(f"  ✅ Owned by: {model['owned_by']}")
                
                # 檢查權限格式（如果存在）
                if "permission" in model:
                    assert isinstance(model["permission"], list), "permission 應該是陣列"
                    print(f"  ✅ Permission: {len(model['permission'])} 項")
            
            print(f"\n🎉 所有 {len(data['data'])} 個模型都符合 OpenAI API 格式!")
            
        else:
            print(f"❌ 請求失敗: {response.status_code}")
            print(response.text)
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ 無法連接到 API 服務 (http://localhost:8081)")
        print("請確保 Semantic Kernel 服務正在運行")
        return False
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False
    
    return True

def test_health_endpoint():
    """測試健康檢查端點"""
    base_url = "http://localhost:8081"
    
    try:
        print("\n🏥 測試健康檢查端點...")
        response = requests.get(f"{base_url}/health")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康狀態: {data.get('status', 'unknown')}")
            print(f"✅ 模型數量: {data.get('models_count', 0)}")
            return True
        else:
            print(f"❌ 健康檢查失敗: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 健康檢查異常: {e}")
        return False

def show_sample_response():
    """顯示範例回應格式"""
    base_url = "http://localhost:8081"
    
    try:
        print("\n📄 範例回應格式:")
        print("-" * 40)
        
        response = requests.get(f"{base_url}/api/models")
        if response.status_code == 200:
            data = response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("無法取得範例回應")
            
    except Exception as e:
        print(f"顯示範例失敗: {e}")

if __name__ == "__main__":
    print("🚀 啟動 API 兼容性測試...")
    
    # 測試健康檢查
    if not test_health_endpoint():
        print("\n❌ 服務不健康，跳過其他測試")
        sys.exit(1)
    
    # 測試 OpenAI 兼容性
    if test_openai_compatibility():
        print("\n🎊 所有測試通過！API 與 OpenAI 格式完全兼容")
        show_sample_response()
        sys.exit(0)
    else:
        print("\n❌ 測試失敗")
        sys.exit(1)