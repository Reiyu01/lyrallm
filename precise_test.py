"""精確時間戳測試 - 找出延遲來源"""
import time
import requests
from datetime import datetime

def test_with_timestamps():
    """測試並打印詳細時間戳"""
    print(f"客戶端開始時間: {datetime.now().isoformat()}")
    
    t1 = time.perf_counter()
    print(f"T1 - 開始請求: {(time.perf_counter()-t1)*1000:.1f}ms")
    
    t2 = time.perf_counter()
    resp = requests.post(
        "http://localhost:8081/api/chat/completions",
        json={
            "model": "gpt-oss:20b",
            "messages": [
                {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                {"role": "user", "content": "你好，請簡短回答"}
            ],
            "stream": False,
            "temperature": 0.7,
            "features": {
                "web_search": False,
                "rag_search": False,
                "image_generation": False,
                "code_interpreter": False
            }
        },
        timeout=60
    )
    t3 = time.perf_counter()
    
    print(f"T2 - 請求完成: {(t3-t2)*1000:.1f}ms")
    print(f"T3 - HTTP 狀態: {resp.status_code}")
    
    t4 = time.perf_counter()
    data = resp.json()
    t5 = time.perf_counter()
    
    print(f"T4 - JSON 解析: {(t5-t4)*1000:.1f}ms")
    print(f"總計時間: {(t5-t1)*1000:.1f}ms")
    print(f"客戶端結束時間: {datetime.now().isoformat()}")
    
    return (t3-t2)*1000


if __name__ == "__main__":
    print("=" * 60)
    print("精確時間戳測試")
    print("=" * 60)
    
    # 預熱
    print("\n🔥 預熱...")
    try:
        test_with_timestamps()
    except Exception as e:
        print(f"預熱失敗: {e}")
    
    time.sleep(1)
    
    # 測試 3 次
    print("\n" + "=" * 60)
    print("正式測試")
    print("=" * 60)
    
    times = []
    for i in range(3):
        print(f"\n--- 第 {i+1} 次 ---")
        try:
            t = test_with_timestamps()
            times.append(t)
        except Exception as e:
            print(f"失敗: {e}")
        time.sleep(0.5)
    
    if times:
        print(f"\n平均: {sum(times)/len(times):.1f}ms")
        print(f"範圍: {min(times):.1f} - {max(times):.1f}ms")
